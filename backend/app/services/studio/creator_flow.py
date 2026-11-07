"""创作模式（Creator Mode）服务：自动确认候选、创作页聚合、作品列表概览。

为什么存在：
- 创作模式把「提取确认」自动化：提取出的角色 / 场景 / 道具 / 服装直接建档并关联到镜头，对白直接写入对白行，
  用户不再逐项点「关联 / 新建 / 忽略」。状态语义不变：确认完成后 `shot.status` 仍按原规则变为 ready。
- 创作页是单页五步流程，需要一次请求拿到章节下全部镜头、实体和最近任务状态。
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import (
    Chapter,
    Character,
    CharacterImage,
    Costume,
    CostumeImage,
    FileItem,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    Prop,
    PropImage,
    Scene,
    SceneImage,
    Shot,
    ShotCandidateStatus,
    ShotCharacterLink,
    ShotDetail,
    ShotDialogLine,
    ShotDialogueCandidateStatus,
    ShotExtractedCandidate,
    ShotExtractedDialogueCandidate,
    ShotFrameImage,
    ShotFrameType,
    ShotStatus,
)
from app.models.task import GenerationTask
from app.models.task_links import GenerationTaskLink
from app.schemas.studio.creator import (
    AutoConfirmResultRead,
    CreatorBoardRead,
    CreatorChapterRead,
    CreatorDialogueLineRead,
    CreatorEntityRead,
    CreatorProjectRead,
    CreatorShotRead,
    CreatorSummaryRead,
    CreatorTaskRead,
    ProjectOverviewRead,
)
from app.services.common import entity_not_found
from app.services.studio.entity_crud import create_entity
from app.services.studio.entity_thumbnails import download_url
from app.services.studio.shot_extracted_candidates import mark_linked, set_skip_extraction
from app.services.studio.shot_extracted_dialogue_candidates import mark_accepted
from app.services.studio.shot_preparation_state import link_existing_asset_for_preparation
from app.services.studio.shot_status import recompute_shot_status

# 候选类型 → 实体模型 / 项目关联模型 / 图片模型 / 图片表上的外键字段
_ASSET_SPECS: dict[str, tuple[type, type, type, str]] = {
    "scene": (Scene, ProjectSceneLink, SceneImage, "scene_id"),
    "prop": (Prop, ProjectPropLink, PropImage, "prop_id"),
    "costume": (Costume, ProjectCostumeLink, CostumeImage, "costume_id"),
}

_ACTIVE_OR_DONE_ORDER = ("pending", "running", "streaming", "succeeded", "failed", "cancelled")


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


# ---------------------------------------------------------------------------
# 自动确认
# ---------------------------------------------------------------------------


async def _find_character(db: AsyncSession, *, project_id: str, name: str) -> Character | None:
    stmt = select(Character).where(Character.project_id == project_id, Character.name == name).limit(1)
    return (await db.execute(stmt)).scalars().first()


async def _find_asset(db: AsyncSession, *, entity_type: str, project_id: str, name: str) -> tuple[Any | None, bool]:
    """按名称查找场景 / 道具 / 服装：优先本项目已关联的，其次全局同名。返回 (实体, 是否已关联到项目)。"""
    model, link_model, _img, fk = _ASSET_SPECS[entity_type]
    linked_stmt = (
        select(model)
        .join(link_model, getattr(link_model, fk) == model.id)
        .where(link_model.project_id == project_id, model.name == name)
        .limit(1)
    )
    linked = (await db.execute(linked_stmt)).scalars().first()
    if linked is not None:
        return linked, True
    any_stmt = select(model).where(model.name == name).order_by(model.created_at.asc()).limit(1)
    return (await db.execute(any_stmt)).scalars().first(), False


async def auto_confirm_chapter(db: AsyncSession, *, chapter_id: str) -> AutoConfirmResultRead:
    """把章节内全部待确认候选自动确认，使镜头达到信息确认完成（ready）。

    规则：
    - 资产候选：同名实体已在项目中 → 关联；全局存在同名 → 关联到项目并关联镜头；都没有 → 新建并关联；
    - 对白候选：全部接受，写入镜头对白行；
    - 从未跑过提取的镜头：标记为无需提取，避免卡在 pending。
    调用方负责提交事务。
    """
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise ValueError(entity_not_found("Chapter"))
    project = await db.get(Project, chapter.project_id)
    if project is None:
        raise ValueError(entity_not_found("Project"))

    shots = list((await db.execute(select(Shot).where(Shot.chapter_id == chapter_id).order_by(Shot.index.asc()))).scalars().all())
    result = AutoConfirmResultRead(shot_count=len(shots))
    # (type, name) → entity_id，避免同章节内重复查询 / 重复创建
    resolved: dict[tuple[str, str], str] = {}

    for shot in shots:
        cand_stmt = (
            select(ShotExtractedCandidate)
            .where(ShotExtractedCandidate.shot_id == shot.id, ShotExtractedCandidate.candidate_status == ShotCandidateStatus.pending)
            .order_by(ShotExtractedCandidate.id.asc())
        )
        for cand in (await db.execute(cand_stmt)).scalars().all():
            entity_type = _enum_value(cand.candidate_type)
            name = (cand.candidate_name or "").strip()
            if not name:
                continue
            key = (entity_type, name.lower())
            description = str((cand.payload or {}).get("description") or "")
            entity_id = resolved.get(key)
            if entity_id is not None:
                # 已在本章节其它镜头解析过：只需关联到当前镜头
                await link_existing_asset_for_preparation(
                    db, project_id=project.id, chapter_id=chapter_id, shot_id=shot.id, entity_type=entity_type, linked_entity_id=entity_id
                )
            elif entity_type == "character":
                existing = await _find_character(db, project_id=project.id, name=name)
                if existing is None:
                    payload = await create_entity(
                        db,
                        entity_type="character",
                        body={
                            "id": uuid.uuid4().hex,
                            "project_id": project.id,
                            "name": name,
                            "description": description,
                            "style": _enum_value(project.style),
                            "visual_style": _enum_value(project.visual_style),
                            "chapter_id": chapter_id,
                            "shot_id": shot.id,
                        },
                    )
                    entity_id = str(payload["id"])
                    result.created_entities += 1
                else:
                    entity_id = existing.id
                    await link_existing_asset_for_preparation(
                        db, project_id=project.id, chapter_id=chapter_id, shot_id=shot.id, entity_type="character", linked_entity_id=entity_id
                    )
            else:
                if entity_type not in _ASSET_SPECS:
                    continue
                existing, _linked = await _find_asset(db, entity_type=entity_type, project_id=project.id, name=name)
                if existing is None:
                    payload = await create_entity(
                        db,
                        entity_type=entity_type,
                        body={
                            "id": uuid.uuid4().hex,
                            "name": name,
                            "description": description,
                            "style": _enum_value(project.style),
                            "visual_style": _enum_value(project.visual_style),
                            "project_id": project.id,
                            "chapter_id": chapter_id,
                            "shot_id": shot.id,
                        },
                    )
                    entity_id = str(payload["id"])
                    result.created_entities += 1
                else:
                    entity_id = existing.id
                    await link_existing_asset_for_preparation(
                        db, project_id=project.id, chapter_id=chapter_id, shot_id=shot.id, entity_type=entity_type, linked_entity_id=entity_id
                    )
            resolved[key] = entity_id
            await mark_linked(db, candidate_id=cand.id, linked_entity_id=entity_id)
            result.linked_candidates += 1

        dlg_stmt = (
            select(ShotExtractedDialogueCandidate.id)
            .where(
                ShotExtractedDialogueCandidate.shot_id == shot.id,
                ShotExtractedDialogueCandidate.candidate_status == ShotDialogueCandidateStatus.pending,
            )
            .order_by(ShotExtractedDialogueCandidate.index.asc(), ShotExtractedDialogueCandidate.id.asc())
        )
        for (cand_id,) in (await db.execute(dlg_stmt)).all():
            await mark_accepted(db, candidate_id=int(cand_id))
            result.accepted_dialogues += 1

        if shot.last_extracted_at is None and not shot.skip_extraction:
            await set_skip_extraction(db, shot_id=shot.id, skip=True)
            result.skipped_shots += 1
        status = await recompute_shot_status(db, shot_id=shot.id)
        if status == ShotStatus.ready:
            result.ready_shots += 1
    return result


# ---------------------------------------------------------------------------
# 创作页聚合
# ---------------------------------------------------------------------------


async def _latest_tasks(db: AsyncSession, *, relation_type: str, entity_ids: list[str]) -> dict[str, CreatorTaskRead]:
    """每个 relation_entity_id 最近一次任务（按任务创建时间倒序取第一条）。"""
    if not entity_ids:
        return {}
    stmt = (
        select(GenerationTaskLink.relation_entity_id, GenerationTask)
        .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
        .where(GenerationTaskLink.relation_type == relation_type, GenerationTaskLink.relation_entity_id.in_(entity_ids))
        .order_by(GenerationTask.created_at.desc(), GenerationTaskLink.id.desc())
    )
    out: dict[str, CreatorTaskRead] = {}
    for entity_id, task in (await db.execute(stmt)).all():
        if entity_id in out:
            continue
        out[entity_id] = CreatorTaskRead(
            task_id=task.id,
            status=_enum_value(task.status),
            progress=int(task.progress or 0),
            error=(task.error or None),
        )
    return out


async def _file_urls(db: AsyncSession, file_ids: list[str]) -> dict[str, str]:
    """文件 ID → 可直接访问的地址：优先对象存储公网地址（thumbnail），否则走下载接口。"""
    ids = [f for f in set(file_ids) if f]
    if not ids:
        return {}
    rows = (await db.execute(select(FileItem.id, FileItem.thumbnail).where(FileItem.id.in_(ids)))).all()
    urls = {fid: (thumb if (thumb or "").startswith("http") else download_url(fid)) for fid, thumb in rows}
    for fid in ids:
        urls.setdefault(fid, download_url(fid))
    return urls


def _best_image(rows: list[Any]) -> Any | None:
    """实体图片里挑一张展示：优先 is_primary，其次有文件的最新一张。"""
    with_file = [r for r in rows if getattr(r, "file_id", None)]
    if not with_file:
        return rows[0] if rows else None
    with_file.sort(key=lambda r: (1 if getattr(r, "is_primary", False) else 0, r.id), reverse=True)
    return with_file[0]


async def build_creator_board(db: AsyncSession, *, chapter_id: str) -> CreatorBoardRead:
    """聚合创作页所需的全部数据（只读）。"""
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise ValueError(entity_not_found("Chapter"))
    project = await db.get(Project, chapter.project_id)
    if project is None:
        raise ValueError(entity_not_found("Project"))

    shots = list((await db.execute(select(Shot).where(Shot.chapter_id == chapter_id).order_by(Shot.index.asc()))).scalars().all())
    shot_ids = [s.id for s in shots]
    details = {d.id: d for d in (await db.execute(select(ShotDetail).where(ShotDetail.id.in_(shot_ids)))).scalars().all()} if shot_ids else {}

    # 对白行
    lines_by_shot: dict[str, list[ShotDialogLine]] = defaultdict(list)
    if shot_ids:
        for line in (await db.execute(select(ShotDialogLine).where(ShotDialogLine.shot_detail_id.in_(shot_ids)).order_by(ShotDialogLine.index.asc(), ShotDialogLine.id.asc()))).scalars().all():
            lines_by_shot[line.shot_detail_id].append(line)

    # 关联实体
    char_links = (await db.execute(select(ShotCharacterLink).where(ShotCharacterLink.shot_id.in_(shot_ids)).order_by(ShotCharacterLink.index.asc()))).scalars().all() if shot_ids else []
    chars_by_shot: dict[str, list[str]] = defaultdict(list)
    for link in char_links:
        chars_by_shot[link.shot_id].append(link.character_id)
    asset_ids_by_shot: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    asset_ids: dict[str, set[str]] = {"scene": set(), "prop": set(), "costume": set()}
    for entity_type, (_model, link_model, _img, fk) in _ASSET_SPECS.items():
        if not shot_ids:
            continue
        link_rows = (await db.execute(select(link_model).where(link_model.shot_id.in_(shot_ids)))).scalars().all()
        for row in link_rows:
            eid = getattr(row, fk)
            asset_ids_by_shot[row.shot_id][entity_type].append(eid)
            asset_ids[entity_type].add(eid)
    character_ids = sorted({cid for ids in chars_by_shot.values() for cid in ids})

    # 首帧图片 / 任务
    frames = (await db.execute(select(ShotFrameImage).where(ShotFrameImage.shot_detail_id.in_(shot_ids), ShotFrameImage.frame_type == ShotFrameType.first))).scalars().all() if shot_ids else []
    frame_by_shot = {f.shot_detail_id: f for f in frames}
    frame_image_tasks = await _latest_tasks(db, relation_type="shot_frame_image", entity_ids=[str(f.id) for f in frames])
    prompt_tasks = await _latest_tasks(db, relation_type="shot_first_frame_prompt", entity_ids=shot_ids)
    video_tasks = await _latest_tasks(db, relation_type="video", entity_ids=shot_ids)

    file_ids = [f.file_id for f in frames if f.file_id] + [s.generated_video_file_id for s in shots if s.generated_video_file_id]

    # 实体与形象图
    entities: list[CreatorEntityRead] = []
    entity_image_tasks: dict[str, dict[str, CreatorTaskRead]] = {}
    characters = (await db.execute(select(Character).where(Character.id.in_(character_ids)))).scalars().all() if character_ids else []
    char_images: dict[str, list[CharacterImage]] = defaultdict(list)
    if character_ids:
        for img in (await db.execute(select(CharacterImage).where(CharacterImage.character_id.in_(character_ids)))).scalars().all():
            char_images[img.character_id].append(img)
    entity_image_tasks["character"] = await _latest_tasks(
        db, relation_type="character_image", entity_ids=[str(i.id) for imgs in char_images.values() for i in imgs]
    )
    char_task_by_entity = await _latest_tasks(db, relation_type="character", entity_ids=character_ids)
    shot_count_by_entity: dict[str, int] = defaultdict(int)
    for ids in chars_by_shot.values():
        for cid in ids:
            shot_count_by_entity[cid] += 1
    for per_shot in asset_ids_by_shot.values():
        for ids in per_shot.values():
            for eid in ids:
                shot_count_by_entity[eid] += 1
    char_names: dict[str, str] = {}
    for ch in sorted(characters, key=lambda c: c.name):
        char_names[ch.id] = ch.name
        best = _best_image(char_images.get(ch.id, []))
        if best is not None and best.file_id:
            file_ids.append(best.file_id)
        task = (entity_image_tasks["character"].get(str(best.id)) if best is not None else None) or char_task_by_entity.get(ch.id)
        entities.append(
            CreatorEntityRead(
                type="character",
                id=ch.id,
                name=ch.name,
                description=ch.description or "",
                thumbnail="",
                image_id=best.id if best is not None else None,
                image_file_id=best.file_id if best is not None else None,
                image_task=task,
                shot_count=shot_count_by_entity.get(ch.id, 0),
            )
        )
    asset_best_file: dict[str, str] = {}
    for entity_type, (model, _link, image_model, fk) in _ASSET_SPECS.items():
        ids = sorted(asset_ids[entity_type])
        if not ids:
            continue
        rows = (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()
        images: dict[str, list[Any]] = defaultdict(list)
        for img in (await db.execute(select(image_model).where(getattr(image_model, fk).in_(ids)))).scalars().all():
            images[getattr(img, fk)].append(img)
        tasks = await _latest_tasks(db, relation_type=f"{entity_type}_image", entity_ids=[str(i.id) for imgs in images.values() for i in imgs])
        for row in sorted(rows, key=lambda r: r.name):
            best = _best_image(images.get(row.id, []))
            if best is not None and best.file_id:
                file_ids.append(best.file_id)
                asset_best_file[row.id] = best.file_id
            entities.append(
                CreatorEntityRead(
                    type=entity_type,  # type: ignore[arg-type]
                    id=row.id,
                    name=row.name,
                    description=row.description or "",
                    thumbnail="",
                    image_id=best.id if best is not None else None,
                    image_file_id=best.file_id if best is not None else None,
                    image_task=tasks.get(str(best.id)) if best is not None else None,
                    shot_count=shot_count_by_entity.get(row.id, 0),
                )
            )

    urls = await _file_urls(db, file_ids)
    for ent in entities:
        if ent.type == "character":
            best = _best_image(char_images.get(ent.id, []))
            if best is not None and best.file_id:
                ent.thumbnail = urls.get(best.file_id, "")
        else:
            fid = asset_best_file.get(ent.id)
            if fid:
                ent.thumbnail = urls.get(fid, "")

    shot_reads: list[CreatorShotRead] = []
    keyframe_count = video_done = total_seconds = ready_count = 0
    for shot in shots:
        detail = details.get(shot.id)
        frame = frame_by_shot.get(shot.id)
        keyframe_file_id = frame.file_id if frame is not None else None
        if keyframe_file_id:
            keyframe_count += 1
        if shot.generated_video_file_id:
            video_done += 1
        duration = int(detail.duration or 0) if detail is not None else 0
        total_seconds += duration
        if _enum_value(shot.status) == ShotStatus.ready.value:
            ready_count += 1
        dialogue = [
            CreatorDialogueLineRead(
                speaker=char_names.get(getattr(line, "speaker_character_id", None) or "", getattr(line, "speaker_name", "") or ""),
                text=line.text,
            )
            for line in lines_by_shot.get(shot.id, [])
        ]
        shot_reads.append(
            CreatorShotRead(
                id=shot.id,
                index=shot.index,
                title=shot.title,
                script_excerpt=shot.script_excerpt or "",
                status=_enum_value(shot.status),
                duration=duration,
                description=(detail.first_frame_prompt if detail is not None else "") or "",
                dialogue=dialogue,
                character_ids=chars_by_shot.get(shot.id, []),
                scene_ids=asset_ids_by_shot[shot.id]["scene"] if shot.id in asset_ids_by_shot else [],
                prop_ids=asset_ids_by_shot[shot.id]["prop"] if shot.id in asset_ids_by_shot else [],
                keyframe_file_id=keyframe_file_id,
                keyframe_url=urls.get(keyframe_file_id) if keyframe_file_id else None,
                keyframe_prompt_task=prompt_tasks.get(shot.id),
                keyframe_image_task=frame_image_tasks.get(str(frame.id)) if frame is not None else None,
                video_file_id=shot.generated_video_file_id,
                video_url=urls.get(shot.generated_video_file_id) if shot.generated_video_file_id else None,
                video_task=video_tasks.get(shot.id),
            )
        )

    chapter_tasks_divide = await _latest_tasks(db, relation_type="chapter_division", entity_ids=[chapter_id])
    chapter_tasks_extract = await _latest_tasks(db, relation_type="script_extraction", entity_ids=[chapter_id])
    return CreatorBoardRead(
        project=CreatorProjectRead(
            id=project.id,
            name=project.name,
            style=_enum_value(project.style),
            visual_style=_enum_value(project.visual_style),
            default_video_ratio=project.default_video_ratio,
        ),
        chapter=CreatorChapterRead(id=chapter.id, index=chapter.index, title=chapter.title, raw_text=chapter.raw_text or "", status=_enum_value(chapter.status)),
        shots=shot_reads,
        entities=entities,
        summary=CreatorSummaryRead(
            shot_count=len(shots),
            ready_shot_count=ready_count,
            keyframe_count=keyframe_count,
            video_done_count=video_done,
            total_seconds=total_seconds,
        ),
        divide_task=chapter_tasks_divide.get(chapter_id),
        extract_task=chapter_tasks_extract.get(chapter_id),
    )


# ---------------------------------------------------------------------------
# 作品列表
# ---------------------------------------------------------------------------


async def build_projects_overview(db: AsyncSession) -> list[ProjectOverviewRead]:
    """作品卡片：章节 / 镜头 / 关键帧 / 视频计数、封面与最近章节。"""
    projects = list((await db.execute(select(Project).order_by(Project.updated_at.desc()))).scalars().all())
    if not projects:
        return []
    chapters = list((await db.execute(select(Chapter).order_by(Chapter.updated_at.desc()))).scalars().all())
    chapters_by_project: dict[str, list[Chapter]] = defaultdict(list)
    for ch in chapters:
        chapters_by_project[ch.project_id].append(ch)
    chapter_ids = [ch.id for ch in chapters]
    shots = list((await db.execute(select(Shot).where(Shot.chapter_id.in_(chapter_ids)).order_by(Shot.index.asc()))).scalars().all()) if chapter_ids else []
    shots_by_chapter: dict[str, list[Shot]] = defaultdict(list)
    for s in shots:
        shots_by_chapter[s.chapter_id].append(s)
    shot_ids = [s.id for s in shots]
    frames = (await db.execute(select(ShotFrameImage).where(ShotFrameImage.shot_detail_id.in_(shot_ids), ShotFrameImage.frame_type == ShotFrameType.first, ShotFrameImage.file_id.is_not(None)))).scalars().all() if shot_ids else []
    frame_file_by_shot = {f.shot_detail_id: f.file_id for f in frames}
    urls = await _file_urls(db, [f for f in frame_file_by_shot.values() if f])

    out: list[ProjectOverviewRead] = []
    for p in projects:
        p_chapters = chapters_by_project.get(p.id, [])
        p_shots = [s for ch in p_chapters for s in shots_by_chapter.get(ch.id, [])]
        cover = next((urls.get(frame_file_by_shot[s.id]) for s in p_shots if s.id in frame_file_by_shot), None)
        out.append(
            ProjectOverviewRead(
                id=p.id,
                name=p.name,
                description=p.description or "",
                style=_enum_value(p.style),
                visual_style=_enum_value(p.visual_style),
                default_video_ratio=p.default_video_ratio,
                chapter_count=len(p_chapters),
                shot_count=len(p_shots),
                keyframe_count=sum(1 for s in p_shots if s.id in frame_file_by_shot),
                video_count=sum(1 for s in p_shots if s.generated_video_file_id),
                cover_url=cover,
                latest_chapter_id=p_chapters[0].id if p_chapters else None,
                updated_at=p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
            )
        )
    return out
