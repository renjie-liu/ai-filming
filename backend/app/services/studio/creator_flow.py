"""创作模式（Creator Mode）服务：自动确认候选、创作页聚合、作品列表概览。

为什么存在：
- 创作模式把「提取确认」自动化：提取出的角色 / 场景 / 道具 / 服装直接建档并关联到镜头，对白直接写入对白行，
  用户不再逐项点「关联 / 新建 / 忽略」。状态语义不变：确认完成后 `shot.status` 仍按原规则变为 ready。
- 创作页是单页五步流程，需要一次请求拿到章节下全部镜头、实体和最近任务状态。
"""

from __future__ import annotations

import re

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import (
    AssetQualityLevel,
    AssetViewAngle,
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
    ShotCandidateType,
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
from app.models.studio_file_usages import FileUsage
from app.models.task import GenerationTask
from app.models.task_links import GenerationTaskLink
from app.models.types import FileUsageKind
from app.schemas.studio.creator import (
    AutoConfirmResultRead,
    CreatorBoardRead,
    CreatorChapterRead,
    CreatorDialogueLineRead,
    CreatorEntityRead,
    CreatorEntityViewRead,
    CreatorImageCandidateRead,
    CreatorProjectRead,
    CreatorShotRead,
    CreatorSummaryRead,
    CreatorTaskRead,
    ProjectOverviewRead,
)
from app.schemas.studio.shots import ShotLinkedAssetItem
from app.services.common import entity_not_found
from app.services.studio.entity_crud import create_entity
from app.services.studio.entity_thumbnails import download_url
from app.services.worker.async_task_support import fail_stale_inline_tasks
from app.services.studio.file_usages import sync_usage_from_shot_context
from app.services.studio.generation.asset_image import (
    build_asset_image_context,
    build_character_image_base_draft,
    derive_asset_image_preview,
)
from app.services.studio.generation.frame import (
    build_frame_base_draft,
    build_frame_context,
    build_frame_submission_payload,
)
from app.services.studio.image_task_references import (
    resolve_reference_image_refs_by_file_ids,
)
from app.services.studio.image_task_runner import create_image_task_and_link
from app.services.studio.shot_assets_overview import get_shot_assets_overview
from app.services.studio.shot_extracted_candidates import (
    mark_linked,
    mark_linked_by_name,
    set_skip_extraction,
)
from app.services.studio.shot_extracted_dialogue_candidates import mark_accepted
from app.services.studio.shot_preparation_state import (
    link_existing_asset_for_preparation,
)
from app.services.studio.shot_status import recompute_shot_status
from app.services.studio.style_presets import style_label
from app.services.studio.shot_video_prompt_pack import (
    build_preview_grid_prompt,
    build_shot_video_prompt_pack,
)
from app.utils.project_links import upsert_project_link

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
            note=_task_note(task.result),
        )
    return out


def _task_note(result: object) -> str | None:
    """从任务结果里提炼给用户看的折中说明；目前只有「视频参考图被方舟人脸审核拒绝、已自动去掉」一种。"""
    if not isinstance(result, dict):
        return None
    dropped = result.get("dropped_references")
    if not isinstance(dropped, list) or not dropped:
        return None
    # 说明只留名称：去掉「：设定」和「（构图与起始状态）」这类补充，避免提示里括号套括号
    labels = [re.split(r"[：（(]", str(item.get("label") or ""), 1)[0].strip() for item in dropped if isinstance(item, dict)]
    labels = [label for label in labels if label]
    kinds = {str(item.get("kind") or "") for item in dropped if isinstance(item, dict)}
    if not labels and kinds & {"first_frame", "last_frame", "key_frame"}:
        labels = ["首帧图"]
    what = "、".join(labels[:3]) if labels else "部分参考图"
    return f"视频平台拒绝了含真人形象的参考图（{what}），已自动去掉后生成"


async def _task_files(db: AsyncSession, *, relation_type: str, entity_ids: list[str]) -> dict[str, list[tuple[str, str, str | None]]]:
    """每个 relation_entity_id 的历史生成文件（任务成功落盘的那些），新 → 旧：{entity_id: [(file_id, task_id, created_at)]}。

    为什么存在：每次图片生成的结果都保留在任务关联表里，这就是「多候选选一张 / 历史回退」的数据来源，不需要新表。
    """
    if not entity_ids:
        return {}
    stmt = (
        select(GenerationTaskLink.relation_entity_id, GenerationTaskLink.file_id, GenerationTask.id, GenerationTask.created_at)
        .join(GenerationTask, GenerationTask.id == GenerationTaskLink.task_id)
        .where(
            GenerationTaskLink.relation_type == relation_type,
            GenerationTaskLink.relation_entity_id.in_(entity_ids),
            GenerationTaskLink.file_id.is_not(None),
        )
        .order_by(GenerationTask.created_at.desc(), GenerationTaskLink.id.desc())
    )
    out: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
    for entity_id, file_id, task_id, created_at in (await db.execute(stmt)).all():
        out[entity_id].append((str(file_id), str(task_id), created_at.isoformat() if created_at else None))
    return out


MAX_IMAGE_CANDIDATES = 8


def _candidate_rows(
    current_file: str | None,
    history: list[tuple[str, str, str | None]],
    extra_files: list[str] | None = None,
) -> list[tuple[str, str | None, str | None, bool]]:
    """候选列表：当前用的那张排第一，其后按新 → 旧的历史（去重），再补上传图；最多 MAX_IMAGE_CANDIDATES 张。"""
    out: list[tuple[str, str | None, str | None, bool]] = []
    seen: set[str] = set()
    if current_file:
        hit = next(((t, c) for f, t, c in history if f == current_file), (None, None))
        out.append((current_file, hit[0], hit[1], True))
        seen.add(current_file)
    for file_id, task_id, created_at in history:
        if file_id in seen:
            continue
        seen.add(file_id)
        out.append((file_id, task_id, created_at, False))
    for file_id in extra_files or []:
        if file_id and file_id not in seen:
            seen.add(file_id)
            out.append((file_id, None, None, False))
    return out[:MAX_IMAGE_CANDIDATES]


def _candidate_reads(rows: list[tuple[str, str | None, str | None, bool]], urls: dict[str, str]) -> list[CreatorImageCandidateRead]:
    return [CreatorImageCandidateRead(file_id=f, url=urls.get(f, ""), task_id=t, created_at=c, is_current=cur) for f, t, c, cur in rows]


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
    # 实体范围 = 本章节镜头关联到的 + 项目级已建档的（其它集的角色 / 资产也列出，shot_count 为 0，可直接沿用到本集）
    project_characters = list((await db.execute(select(Character).where(Character.project_id == project.id))).scalars().all())
    linked_character_ids = {cid for ids in chars_by_shot.values() for cid in ids}
    extra_character_ids = sorted(linked_character_ids - {c.id for c in project_characters})
    if extra_character_ids:
        project_characters += list((await db.execute(select(Character).where(Character.id.in_(extra_character_ids)))).scalars().all())
    character_ids = [c.id for c in project_characters]
    for entity_type, (_model, link_model, _img, fk) in _ASSET_SPECS.items():
        for (eid,) in (await db.execute(select(getattr(link_model, fk)).where(link_model.project_id == project.id).distinct())).all():
            asset_ids[entity_type].add(eid)
    # 实体 → 本章节内出现的镜头（按镜头顺序）
    shot_ids_by_entity: dict[str, list[str]] = defaultdict(list)
    for shot in shots:
        for cid in chars_by_shot.get(shot.id, []):
            shot_ids_by_entity[cid].append(shot.id)
        for ids in asset_ids_by_shot.get(shot.id, {}).values():
            for eid in ids:
                if shot.id not in shot_ids_by_entity[eid]:
                    shot_ids_by_entity[eid].append(shot.id)

    # 首帧（关键帧）与 key 帧（预演四宫格）图片 / 任务 / 历史候选
    all_frames = (
        (await db.execute(select(ShotFrameImage).where(ShotFrameImage.shot_detail_id.in_(shot_ids), ShotFrameImage.frame_type.in_([ShotFrameType.first, ShotFrameType.key, ShotFrameType.last])))).scalars().all()
        if shot_ids
        else []
    )
    frames = [f for f in all_frames if f.frame_type == ShotFrameType.first]
    frame_by_shot = {f.shot_detail_id: f for f in frames}
    grid_by_shot = {f.shot_detail_id: f for f in all_frames if f.frame_type == ShotFrameType.key}
    # 尾帧：视频生成时由方舟 return_last_frame 回传并转存；下一镜「承接上一镜」用它做参考图
    last_frame_by_shot = {f.shot_detail_id: f.file_id for f in all_frames if f.frame_type == ShotFrameType.last and f.file_id}
    all_frames = [f for f in all_frames if f.frame_type != ShotFrameType.last]
    frame_image_tasks = await _latest_tasks(db, relation_type="shot_frame_image", entity_ids=[str(f.id) for f in all_frames])
    frame_history = await _task_files(db, relation_type="shot_frame_image", entity_ids=[str(f.id) for f in frames])
    keyframe_candidates = {f.shot_detail_id: _candidate_rows(f.file_id, frame_history.get(str(f.id), [])) for f in frames}
    prompt_tasks = await _latest_tasks(db, relation_type="shot_first_frame_prompt", entity_ids=shot_ids)
    await fail_stale_inline_tasks(db)  # 先修正函数被回收后遗留的 running 任务，再读各资源的最近任务
    video_tasks = await _latest_tasks(db, relation_type="video", entity_ids=shot_ids)

    # 配音 / 配乐参考：按镜头取最近一条 reference_audio 用途记录
    audio_by_shot: dict[str, str] = {}
    if shot_ids:
        audio_stmt = (
            select(FileUsage.shot_id, FileUsage.file_id)
            .where(FileUsage.shot_id.in_(shot_ids), FileUsage.usage_kind == FileUsageKind.reference_audio.value)
            .order_by(FileUsage.id.desc())
        )
        for shot_id_value, file_id_value in (await db.execute(audio_stmt)).all():
            audio_by_shot.setdefault(str(shot_id_value), str(file_id_value))

    file_ids = [f.file_id for f in all_frames if f.file_id] + [s.generated_video_file_id for s in shots if s.generated_video_file_id]
    file_ids += list(audio_by_shot.values())
    file_ids += [row[0] for rows in keyframe_candidates.values() for row in rows]

    # 实体与形象图
    entities: list[CreatorEntityRead] = []
    entity_image_tasks: dict[str, dict[str, CreatorTaskRead]] = {}
    characters = project_characters
    char_images: dict[str, list[CharacterImage]] = defaultdict(list)
    if character_ids:
        for img in (await db.execute(select(CharacterImage).where(CharacterImage.character_id.in_(character_ids)))).scalars().all():
            char_images[img.character_id].append(img)
    entity_image_tasks["character"] = await _latest_tasks(
        db, relation_type="character_image", entity_ids=[str(i.id) for imgs in char_images.values() for i in imgs]
    )
    char_task_by_entity = await _latest_tasks(db, relation_type="character", entity_ids=character_ids)
    # 历史候选：角色级任务 + 正面形象图行的任务；其它视角（侧面 / 背面）单独列为 views
    char_front_rows = {cid: [i for i in imgs if _enum_value(i.view_angle) == AssetViewAngle.front.value] for cid, imgs in char_images.items()}
    char_view_rows = {cid: [i for i in imgs if _enum_value(i.view_angle) != AssetViewAngle.front.value] for cid, imgs in char_images.items()}
    char_history_entity = await _task_files(db, relation_type="character", entity_ids=character_ids)
    char_history_images = await _task_files(db, relation_type="character_image", entity_ids=[str(i.id) for rows in char_front_rows.values() for i in rows])
    entity_candidates: dict[str, list[tuple[str, str | None, str | None, bool]]] = {}
    entity_views: dict[str, list[tuple[str, int, str | None]]] = {}
    shot_count_by_entity: dict[str, int] = {eid: len(ids) for eid, ids in shot_ids_by_entity.items()}
    char_names: dict[str, str] = {}
    # 本集用到的排前面，未用到的（沿用自其它集）排后面
    for ch in sorted(characters, key=lambda c: (shot_count_by_entity.get(c.id, 0) == 0, c.name)):
        char_names[ch.id] = ch.name
        best = _best_image(char_images.get(ch.id, []))
        if best is not None and best.file_id:
            file_ids.append(best.file_id)
        task = (entity_image_tasks["character"].get(str(best.id)) if best is not None else None) or char_task_by_entity.get(ch.id)
        history = list(char_history_entity.get(ch.id, []))
        for row in char_front_rows.get(ch.id, []):
            history += char_history_images.get(str(row.id), [])
        history.sort(key=lambda item: item[2] or "", reverse=True)
        entity_candidates[ch.id] = _candidate_rows(
            best.file_id if best is not None else None, history, [row.file_id for row in char_front_rows.get(ch.id, []) if row.file_id]
        )
        entity_views[ch.id] = [(_enum_value(row.view_angle), int(row.id), row.file_id) for row in sorted(char_view_rows.get(ch.id, []), key=lambda r: r.id)]
        file_ids += [row[0] for row in entity_candidates[ch.id]] + [fid for _a, _i, fid in entity_views[ch.id] if fid]
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
                shot_ids=shot_ids_by_entity.get(ch.id, []),
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
        asset_history = await _task_files(db, relation_type=f"{entity_type}_image", entity_ids=[str(i.id) for imgs in images.values() for i in imgs])
        for row in sorted(rows, key=lambda r: (shot_count_by_entity.get(r.id, 0) == 0, r.name)):
            best = _best_image(images.get(row.id, []))
            if best is not None and best.file_id:
                file_ids.append(best.file_id)
                asset_best_file[row.id] = best.file_id
            history: list[tuple[str, str, str | None]] = []
            for img in images.get(row.id, []):
                history += asset_history.get(str(img.id), [])
            history.sort(key=lambda item: item[2] or "", reverse=True)
            entity_candidates[row.id] = _candidate_rows(
                best.file_id if best is not None else None, history, [img.file_id for img in images.get(row.id, []) if img.file_id]
            )
            file_ids += [item[0] for item in entity_candidates[row.id]]
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
                    shot_ids=shot_ids_by_entity.get(row.id, []),
                )
            )

    file_ids += list(last_frame_by_shot.values())
    urls = await _file_urls(db, file_ids)
    for ent in entities:
        if ent.type == "character":
            best = _best_image(char_images.get(ent.id, []))
            if best is not None and best.file_id:
                ent.thumbnail = urls.get(best.file_id, "")
            ent.views = [
                CreatorEntityViewRead(
                    view_angle=angle, image_id=image_id, file_id=fid, url=urls.get(fid, "") if fid else "", task=entity_image_tasks["character"].get(str(image_id))
                )
                for angle, image_id, fid in entity_views.get(ent.id, [])
            ]
        else:
            fid = asset_best_file.get(ent.id)
            if fid:
                ent.thumbnail = urls.get(fid, "")
        ent.image_candidates = _candidate_reads(entity_candidates.get(ent.id, []), urls)

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
                id=int(line.id),
                speaker=char_names.get(getattr(line, "speaker_character_id", None) or "", getattr(line, "speaker_name", "") or ""),
                speaker_character_id=getattr(line, "speaker_character_id", None),
                text=line.text,
            )
            for line in lines_by_shot.get(shot.id, [])
        ]
        grid = grid_by_shot.get(shot.id)
        audio_file_id = audio_by_shot.get(shot.id)
        shot_reads.append(
            CreatorShotRead(
                id=shot.id,
                index=shot.index,
                title=shot.title,
                script_excerpt=shot.script_excerpt or "",
                status=_enum_value(shot.status),
                duration=duration,
                camera_shot=_enum_value(detail.camera_shot) if detail is not None and detail.camera_shot else "",
                angle=_enum_value(detail.angle) if detail is not None and detail.angle else "",
                movement=_enum_value(detail.movement) if detail is not None and detail.movement else "",
                action_beats=[str(item) for item in (detail.action_beats or []) if str(item).strip()] if detail is not None else [],
                description=(detail.first_frame_prompt if detail is not None else "") or "",
                dialogue=dialogue,
                character_ids=chars_by_shot.get(shot.id, []),
                scene_ids=asset_ids_by_shot[shot.id]["scene"] if shot.id in asset_ids_by_shot else [],
                prop_ids=asset_ids_by_shot[shot.id]["prop"] if shot.id in asset_ids_by_shot else [],
                keyframe_file_id=keyframe_file_id,
                keyframe_url=urls.get(keyframe_file_id) if keyframe_file_id else None,
                last_frame_file_id=last_frame_by_shot.get(shot.id),
                last_frame_url=urls.get(last_frame_by_shot[shot.id]) if shot.id in last_frame_by_shot else None,
                keyframe_prompt_task=prompt_tasks.get(shot.id),
                keyframe_image_task=frame_image_tasks.get(str(frame.id)) if frame is not None else None,
                keyframe_candidates=_candidate_reads(keyframe_candidates.get(shot.id, []), urls),
                preview_grid_url=urls.get(grid.file_id) if grid is not None and grid.file_id else None,
                preview_grid_task=frame_image_tasks.get(str(grid.id)) if grid is not None else None,
                audio_file_id=audio_file_id,
                audio_url=urls.get(audio_file_id) if audio_file_id else None,
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
            style_preset=project.style_preset,
            style_label=style_label(project),
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
# 创作页编辑：镜头 ↔ 实体关联、手动建档、上传图挂载
# ---------------------------------------------------------------------------

CREATOR_ENTITY_TYPES = ("character", "scene", "prop", "costume")


class CreatorInputError(ValueError):
    """输入不合法（实体类型不支持、实体不属于本作品等）；路由层映射为 400，其它 ValueError 为 404。"""


def _require_entity_type(entity_type: str) -> str:
    value = (entity_type or "").strip().lower()
    if value not in CREATOR_ENTITY_TYPES:
        raise CreatorInputError(f"unsupported entity_type: {entity_type}")
    return value


async def _load_shot_scope(db: AsyncSession, *, shot_id: str) -> tuple[Shot, Chapter, Project]:
    """镜头及其章节 / 作品；任一缺失抛 ValueError（not found）。"""
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise ValueError(entity_not_found("Shot"))
    chapter = await db.get(Chapter, shot.chapter_id)
    if chapter is None:
        raise ValueError(entity_not_found("Chapter"))
    project = await db.get(Project, chapter.project_id)
    if project is None:
        raise ValueError(entity_not_found("Project"))
    return shot, chapter, project


async def _load_chapter_scope(db: AsyncSession, *, chapter_id: str) -> tuple[Chapter, Project]:
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise ValueError(entity_not_found("Chapter"))
    project = await db.get(Project, chapter.project_id)
    if project is None:
        raise ValueError(entity_not_found("Project"))
    return chapter, project


async def _ignore_candidate_by_name(db: AsyncSession, *, shot_id: str, entity_type: str, name: str) -> None:
    """用户主动解除关联时，把镜头内同名提取候选标记为 ignored；否则下一次 auto-confirm 会按名字把它重新挂回。"""
    if not name:
        return
    stmt = (
        update(ShotExtractedCandidate)
        .where(
            ShotExtractedCandidate.shot_id == shot_id,
            ShotExtractedCandidate.candidate_type == ShotCandidateType(entity_type),
            ShotExtractedCandidate.candidate_name == name,
        )
        .values(candidate_status=ShotCandidateStatus.ignored)
    )
    await db.execute(stmt)


async def shot_entity_ids(db: AsyncSession, *, shot_id: str, entity_type: str) -> list[str]:
    """镜头当前关联的某类实体 ID（角色按画面内 index 排序，资产按关联顺序）。"""
    et = _require_entity_type(entity_type)
    if et == "character":
        stmt = select(ShotCharacterLink).where(ShotCharacterLink.shot_id == shot_id).order_by(ShotCharacterLink.index.asc(), ShotCharacterLink.id.asc())
        return [row.character_id for row in (await db.execute(stmt)).scalars().all()]
    _model, link_model, _img, fk = _ASSET_SPECS[et]
    rows = (await db.execute(select(link_model).where(link_model.shot_id == shot_id).order_by(link_model.id.asc()))).scalars().all()
    return list(dict.fromkeys(getattr(row, fk) for row in rows))


async def set_shot_entity_links(db: AsyncSession, *, shot_id: str, entity_type: str, entity_ids: list[str]) -> list[str]:
    """整体替换镜头某一类「画面里会用到」的实体（创作页分镜卡编辑）。

    - 新增：建立关联，并把镜头内同名提取候选标记为 linked；
    - 移除：删除关联，并把同名候选标记为 ignored（避免下次自动确认挂回）；
    - 角色按传入顺序重排 index（先删后建，避开 (shot_id, index) 唯一约束）。
    返回最终关联的实体 ID；调用方负责提交事务。
    """
    et = _require_entity_type(entity_type)
    _shot, chapter, project = await _load_shot_scope(db, shot_id=shot_id)
    wanted = list(dict.fromkeys(i for i in entity_ids if i))
    current = await shot_entity_ids(db, shot_id=shot_id, entity_type=et)
    added = [i for i in wanted if i not in current]
    removed = [i for i in current if i not in wanted]

    model = Character if et == "character" else _ASSET_SPECS[et][0]
    involved = sorted(set(current) | set(wanted))
    names = {obj.id: obj.name for obj in (await db.execute(select(model).where(model.id.in_(involved)))).scalars().all()} if involved else {}
    for eid in wanted:
        if eid not in names:
            raise ValueError(entity_not_found(model.__name__))

    if et == "character":
        for cid in wanted:
            character = await db.get(Character, cid)
            if character is not None and character.project_id != project.id:
                raise CreatorInputError("Character does not belong to the same project")
        if wanted != current:
            for row in (await db.execute(select(ShotCharacterLink).where(ShotCharacterLink.shot_id == shot_id))).scalars().all():
                await db.delete(row)
            await db.flush()
            for idx, cid in enumerate(wanted):
                db.add(ShotCharacterLink(shot_id=shot_id, character_id=cid, index=idx, note=""))
            await db.flush()
    else:
        _model, link_model, _img, fk = _ASSET_SPECS[et]
        if removed:
            for row in (await db.execute(select(link_model).where(link_model.shot_id == shot_id, getattr(link_model, fk).in_(removed)))).scalars().all():
                await db.delete(row)
            await db.flush()
        for eid in added:
            await upsert_project_link(
                db, model=link_model, asset_field=fk, asset_id=eid, project_id=project.id, chapter_id=chapter.id, shot_id=shot_id  # type: ignore[arg-type]
            )

    for eid in added:
        await mark_linked_by_name(db, shot_id=shot_id, candidate_type=et, candidate_name=names[eid], linked_entity_id=eid)
    for eid in removed:
        await _ignore_candidate_by_name(db, shot_id=shot_id, entity_type=et, name=names.get(eid, ""))
    return wanted


async def set_entity_shots(db: AsyncSession, *, chapter_id: str, entity_type: str, entity_id: str, shot_ids: list[str]) -> list[str]:
    """设置实体在本章节内出现的镜头集合（创作页角色场景卡编辑）。

    不在列表里的本章节镜头会解除关联；一个镜头都不选时实体仍保留在作品里（资产保留项目级关联）。
    返回最终关联的镜头 ID（按镜头顺序）。
    """
    et = _require_entity_type(entity_type)
    chapter, project = await _load_chapter_scope(db, chapter_id=chapter_id)
    model = Character if et == "character" else _ASSET_SPECS[et][0]
    entity = await db.get(model, entity_id)
    if entity is None:
        raise ValueError(entity_not_found(model.__name__))
    if et == "character" and entity.project_id != project.id:
        raise CreatorInputError("Character does not belong to the same project")

    wanted = set(shot_ids)
    result: list[str] = []
    shots = (await db.execute(select(Shot).where(Shot.chapter_id == chapter_id).order_by(Shot.index.asc()))).scalars().all()
    for shot in shots:
        current = await shot_entity_ids(db, shot_id=shot.id, entity_type=et)
        present = entity_id in current
        if shot.id in wanted:
            result.append(shot.id)
            if not present:
                await set_shot_entity_links(db, shot_id=shot.id, entity_type=et, entity_ids=[*current, entity_id])
        elif present:
            await set_shot_entity_links(db, shot_id=shot.id, entity_type=et, entity_ids=[i for i in current if i != entity_id])

    if et != "character":
        _model, link_model, _img, fk = _ASSET_SPECS[et]
        exists = (await db.execute(select(link_model.id).where(getattr(link_model, fk) == entity_id, link_model.project_id == project.id).limit(1))).first()
        if exists is None:
            await upsert_project_link(db, model=link_model, asset_field=fk, asset_id=entity_id, project_id=project.id, chapter_id=chapter.id, shot_id=None)  # type: ignore[arg-type]
    return result


async def create_chapter_entity(
    db: AsyncSession, *, chapter_id: str, entity_type: str, name: str, description: str, shot_ids: list[str]
) -> tuple[str, bool]:
    """创作页手动新增角色 / 场景 / 道具 / 服装（沿用作品的题材 / 画面风格），并挂到指定镜头。

    名称唯一规则与自动确认一致：角色按作品唯一，场景 / 道具 / 服装全局唯一（表上有 uq_*_name）。
    同名已存在时沿用它（补空描述、关联到本作品与镜头），而不是报错。返回 (实体 ID, 是否沿用)。
    """
    et = _require_entity_type(entity_type)
    chapter, project = await _load_chapter_scope(db, chapter_id=chapter_id)
    clean_name = (name or "").strip()
    if not clean_name:
        raise CreatorInputError("name is required")
    existing = (
        await _find_character(db, project_id=project.id, name=clean_name)
        if et == "character"
        else (await _find_asset(db, entity_type=et, project_id=project.id, name=clean_name))[0]
    )
    if existing is not None:
        entity_id = str(existing.id)
        if description and not (existing.description or "").strip():
            existing.description = description
            await db.flush()
    else:
        payload = await create_entity(
            db,
            entity_type=et,
            body={
                "id": uuid.uuid4().hex,
                "name": clean_name,
                "description": description or "",
                "style": _enum_value(project.style),
                "visual_style": _enum_value(project.visual_style),
                "project_id": project.id,
                "chapter_id": chapter.id,
            },
        )
        entity_id = str(payload["id"])
    await set_entity_shots(db, chapter_id=chapter_id, entity_type=et, entity_id=entity_id, shot_ids=list(shot_ids))
    return entity_id, existing is not None


def _file_format(file: FileItem) -> str:
    """从文件名推断图片格式，写入图片行的 format 字段。"""
    name = (file.name or "").lower()
    for ext, fmt in ((".jpg", "jpeg"), (".jpeg", "jpeg"), (".png", "png"), (".webp", "webp"), (".gif", "gif")):
        if name.endswith(ext):
            return fmt
    return "png"


async def attach_entity_image(db: AsyncSession, *, entity_type: str, entity_id: str, file_id: str) -> int:
    """把已上传的文件设为实体的形象 / 参考图，并成为卡片展示与关键帧 / 视频参考用的「最佳图」。

    所有图片表都按 (实体, 精度, 角度) 唯一，所以不会为同一角度新插一行：
    - 角色：已有同一文件的正面行则直接设为主图（「采用」历史候选）；否则把文件写进当前展示的正面行并设为主图；
      没有正面行时才新建。其它视角（侧面 / 背面）的行不动。历史文件仍在任务关联表里，候选列表不受覆盖影响。
    - 场景 / 道具 / 服装：直接把文件写进当前展示的那一行（无行时新建正面图）。
    返回图片行 ID。
    """
    et = _require_entity_type(entity_type)
    file = await db.get(FileItem, file_id)
    if file is None:
        raise ValueError(entity_not_found("FileItem"))
    fmt = _file_format(file)
    if et == "character":
        if await db.get(Character, entity_id) is None:
            raise ValueError(entity_not_found("Character"))
        rows = list((await db.execute(select(CharacterImage).where(CharacterImage.character_id == entity_id))).scalars().all())
        for img in rows:
            if img.is_primary:
                img.is_primary = False
        front_rows = [r for r in rows if _enum_value(r.view_angle) == AssetViewAngle.front.value]
        existing = next((r for r in front_rows if r.file_id == file_id), None) or _best_image(front_rows)
        if existing is not None:
            if existing.file_id != file_id:
                existing.file_id = file_id
                existing.format = fmt
            existing.is_primary = True
            await db.flush()
            return int(existing.id)
        image: Any = CharacterImage(
            character_id=entity_id, file_id=file_id, quality_level=AssetQualityLevel.low, view_angle=AssetViewAngle.front, format=fmt, is_primary=True
        )
    else:
        model, _link, image_model, fk = _ASSET_SPECS[et]
        if await db.get(model, entity_id) is None:
            raise ValueError(entity_not_found(model.__name__))
        rows = list((await db.execute(select(image_model).where(getattr(image_model, fk) == entity_id).order_by(image_model.id.asc()))).scalars().all())
        current = _best_image(rows)
        if current is not None:
            current.file_id = file_id
            current.format = fmt
            await db.flush()
            await db.refresh(current)
            return int(current.id)
        image = image_model(**{fk: entity_id, "file_id": file_id, "quality_level": AssetQualityLevel.low, "view_angle": AssetViewAngle.front, "format": fmt})
    db.add(image)
    await db.flush()
    await db.refresh(image)
    return int(image.id)


async def attach_shot_keyframe(db: AsyncSession, *, shot_id: str, file_id: str) -> int:
    """把已上传的文件设为镜头首帧（关键帧）：有槽位则覆盖，否则新建。返回 ShotFrameImage.id。"""
    if await db.get(ShotDetail, shot_id) is None:
        raise ValueError(entity_not_found("ShotDetail"))
    file = await db.get(FileItem, file_id)
    if file is None:
        raise ValueError(entity_not_found("FileItem"))
    stmt = select(ShotFrameImage).where(ShotFrameImage.shot_detail_id == shot_id, ShotFrameImage.frame_type == ShotFrameType.first).limit(1)
    frame = (await db.execute(stmt)).scalars().first()
    if frame is None:
        frame = ShotFrameImage(shot_detail_id=shot_id, frame_type=ShotFrameType.first, file_id=file_id, format=_file_format(file))
        db.add(frame)
    else:
        frame.file_id = file_id
        frame.format = _file_format(file)
    await db.flush()
    await db.refresh(frame)
    return int(frame.id)


async def attach_shot_video(db: AsyncSession, *, shot_id: str, file_id: str) -> str:
    """把上传的视频设为镜头成片（替换 AI 生成结果；成片页照常连播）。返回文件 ID。"""
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise ValueError(entity_not_found("Shot"))
    file = await db.get(FileItem, file_id)
    if file is None:
        raise ValueError(entity_not_found("FileItem"))
    if _enum_value(file.type) != "video":
        raise CreatorInputError("file is not a video")
    shot.generated_video_file_id = file_id
    await sync_usage_from_shot_context(
        db, file_id=file_id, shot_id=shot_id, usage_kind=FileUsageKind.generated_video, source_ref=f"shot:{shot_id}:uploaded_video"
    )
    await db.flush()
    return file_id


CHARACTER_VIEW_PROMPTS: dict[str, tuple[AssetViewAngle, str]] = {
    "left": (AssetViewAngle.left, "侧面 90 度视角，人物面向画面左侧，全身"),
    "right": (AssetViewAngle.right, "侧面 90 度视角，人物面向画面右侧，全身"),
    "back": (AssetViewAngle.back, "正后方背面视角，全身，看得到发型与服装背面"),
    "three_quarter": (AssetViewAngle.three_quarter, "四分之三侧面视角，微微转向画面右侧，全身"),
}


async def generate_character_views(db: AsyncSession, *, character_id: str, views: list[str]) -> list[str]:
    """以当前正面形象为参考，派生其它视角的形象图（每个视角一个图片任务，写入对应 view_angle 的 CharacterImage 行）。

    为什么存在：多视图参考能让视频模型在转身、侧脸镜头里也认出同一个人（LibTV「角色三视图」、即梦多形态资产的做法）。
    返回任务 ID 列表；任务创建即已提交并入队。
    """
    character = await db.get(Character, character_id)
    if character is None:
        raise ValueError(entity_not_found("Character"))
    rows = list((await db.execute(select(CharacterImage).where(CharacterImage.character_id == character_id))).scalars().all())
    primary = _best_image([r for r in rows if _enum_value(r.view_angle) == AssetViewAngle.front.value])
    if primary is None or not primary.file_id:
        raise CreatorInputError("Character has no front portrait yet; generate or upload one first")
    base = await build_character_image_base_draft(db, character_id=character_id, image_id=None)
    base_prompt = derive_asset_image_preview(base=base, context=build_asset_image_context(base=base)).prompt.strip()
    refs = await resolve_reference_image_refs_by_file_ids(db, file_ids=[primary.file_id])
    task_ids: list[str] = []
    for view in views:
        if view not in CHARACTER_VIEW_PROMPTS:
            raise CreatorInputError(f"unsupported view: {view}")
        angle, instruction = CHARACTER_VIEW_PROMPTS[view]
        row = next((r for r in rows if _enum_value(r.view_angle) == angle.value), None)
        if row is None:
            row = CharacterImage(character_id=character_id, file_id=None, quality_level=AssetQualityLevel.low, view_angle=angle, format="png", is_primary=False)
            db.add(row)
            await db.flush()
            await db.refresh(row)
            rows.append(row)
        prompt = f"{base_prompt}\n\n视角要求：{instruction}。与参考图是同一个人：脸型、发型、肤色、服装、体型完全一致；纯色干净背景，无文字。"
        task_ids.append(
            await create_image_task_and_link(
                db=db,
                model_id=None,
                relation_type="character_image",
                relation_entity_id=str(row.id),
                prompt=prompt,
                images=refs or None,
                purpose="character_view",
            )
        )
    return task_ids


async def generate_preview_grid(db: AsyncSession, *, shot_id: str, ratio: str | None = None) -> str:
    """生成镜头的「预演四宫格」：一张 2×2 图按时间顺序演四个节拍，落到 ShotFrameImage(key)。返回任务 ID。

    为什么存在：生视频前先用一次图片费用检查节奏、构图与人物连续性（LibTV 剧情推演四宫格 / 即梦白模预演的廉价版）。
    """
    detail = await db.get(ShotDetail, shot_id)
    if detail is None:
        raise ValueError(entity_not_found("ShotDetail"))
    pack = await build_shot_video_prompt_pack(db, shot_id=shot_id)
    overview = await get_shot_assets_overview(db, shot_id=shot_id)
    items = [
        ShotLinkedAssetItem(type=item.type, id=str(item.linked_entity_id), image_id=None, file_id=item.file_id, name=item.name, thumbnail=item.thumbnail or "")
        for item in overview.items
        if getattr(item, "is_linked", False) and item.file_id and item.linked_entity_id
    ]
    grid_stmt = select(ShotFrameImage).where(ShotFrameImage.shot_detail_id == shot_id, ShotFrameImage.frame_type == ShotFrameType.key).limit(1)
    row = (await db.execute(grid_stmt)).scalars().first()
    if row is None:
        row = ShotFrameImage(shot_detail_id=shot_id, frame_type=ShotFrameType.key, file_id=None, format="png")
        db.add(row)
        await db.flush()
        await db.refresh(row)
    base = build_frame_base_draft(shot_id=shot_id, frame_type=ShotFrameType.key, prompt=build_preview_grid_prompt(pack))
    context = build_frame_context(shot_id=shot_id, frame_type=ShotFrameType.key, items=items)
    submission = build_frame_submission_payload(base=base, context=context)
    refs = await resolve_reference_image_refs_by_file_ids(db, file_ids=submission.images)
    return await create_image_task_and_link(
        db=db,
        model_id=None,
        relation_type="shot_frame_image",
        relation_entity_id=str(row.id),
        prompt=submission.prompt,
        images=refs or None,
        target_ratio=ratio or "1:1",
        resolution_profile="standard",
        purpose="storyboard_preview",
        render_context=dict(submission.extra or {}).get("render_context"),
    )


async def reorder_chapter_shots(db: AsyncSession, *, chapter_id: str, shot_ids: list[str]) -> list[str]:
    """按给定顺序重排章节镜头的序号（index 从 1 开始）。

    为什么存在：分镜板拖拽排序 / 上移下移。序号在章节内唯一（`uq_shots_chapter_index`），
    所以分两步写：先全部改成负数占位，再按新顺序写正数，避免中途撞唯一约束。
    shot_ids 必须恰好包含本章节的全部镜头各一次。
    """
    if await db.get(Chapter, chapter_id) is None:
        raise ValueError(entity_not_found("Chapter"))
    shots = list((await db.execute(select(Shot).where(Shot.chapter_id == chapter_id))).scalars().all())
    by_id = {s.id: s for s in shots}
    wanted = [str(item).strip() for item in shot_ids]
    if len(wanted) != len(set(wanted)) or set(wanted) != set(by_id):
        raise CreatorInputError("shot_ids must contain every shot of the chapter exactly once")
    for position, shot_id in enumerate(wanted, start=1):
        by_id[shot_id].index = -position
    await db.flush()
    for position, shot_id in enumerate(wanted, start=1):
        by_id[shot_id].index = position
    await db.flush()
    return wanted


async def attach_shot_audio(db: AsyncSession, *, shot_id: str, file_id: str | None) -> str | None:
    """设置 / 清除镜头的配音或配乐参考：记录为 reference_audio 用途（镜头本身没有音频字段，用途表即是关联）。"""
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise ValueError(entity_not_found("Shot"))
    existing = (await db.execute(select(FileUsage).where(FileUsage.shot_id == shot_id, FileUsage.usage_kind == FileUsageKind.reference_audio.value))).scalars().all()
    for usage in existing:
        await db.delete(usage)
    await db.flush()
    if not file_id:
        return None
    file = await db.get(FileItem, file_id)
    if file is None:
        raise ValueError(entity_not_found("FileItem"))
    if _enum_value(file.type) != "audio":
        raise CreatorInputError("file is not audio")
    await sync_usage_from_shot_context(db, file_id=file_id, shot_id=shot_id, usage_kind=FileUsageKind.reference_audio, source_ref=f"shot:{shot_id}:reference_audio")
    await db.flush()
    return file_id


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
                style_preset=p.style_preset,
                style_label=style_label(p),
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
