"""创作模式服务：自动确认候选 → 镜头 ready；创作页聚合；作品概览。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import (
    Chapter,
    Character,
    Project,
    ProjectSceneLink,
    ProjectStyle,
    ProjectVisualStyle,
    Scene,
    Shot,
    ShotCharacterLink,
    ShotDialogLine,
    ShotStatus,
)
from app.services.studio.creator_flow import (
    auto_confirm_chapter,
    build_creator_board,
    build_projects_overview,
)
from app.services.studio.shot_detail_defaults import build_default_shot_detail
from app.services.studio.shot_extracted_candidates import (
    replace_for_shot as replace_candidates,
)
from app.services.studio.shot_extracted_dialogue_candidates import (
    replace_for_shot as replace_dialogue_candidates,
)


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed(db: AsyncSession) -> tuple[Shot, Shot]:
    """两个镜头：同一个角色出现两次、同一个场景出现两次，各带一条对白。"""
    db.add_all(
        [
            Project(id="p1", name="大厂的神", description="", style=ProjectStyle.real_people_city, visual_style=ProjectVisualStyle.live_action),
            Chapter(id="c1", project_id="p1", index=1, title="第1集", raw_text="..."),
        ]
    )
    await db.flush()
    s1, s2 = Shot(id="s1", chapter_id="c1", index=1, title="办公区全景"), Shot(id="s2", chapter_id="c1", index=2, title="雷霆自我介绍")
    db.add_all([s1, s2])
    await db.flush()
    db.add_all([build_default_shot_detail("s1"), build_default_shot_detail("s2")])
    await db.flush()
    for shot in (s1, s2):
        await replace_candidates(
            db,
            shot_id=shot.id,
            candidates=[
                {"candidate_type": "character", "candidate_name": "雷霆总监", "payload": {"description": "40岁，西装外套套在T恤外"}},
                {"candidate_type": "scene", "candidate_name": "开放式办公区", "payload": {"description": "清晨"}},
            ],
        )
        await replace_dialogue_candidates(db, shot_id=shot.id, candidates=[{"index": 1, "text": "各位，先自我介绍一下。", "speaker_name": "雷霆总监"}])
    return s1, s2


@pytest.mark.asyncio
async def test_auto_confirm_creates_entities_once_and_marks_shots_ready() -> None:
    db, engine = await _build_session()
    async with db:
        s1, s2 = await _seed(db)
        assert s1.status == ShotStatus.pending

        result = await auto_confirm_chapter(db, chapter_id="c1")

        assert result.shot_count == 2
        assert result.linked_candidates == 4
        assert result.accepted_dialogues == 2
        assert result.created_entities == 2  # 同名角色 / 场景只建一次
        assert result.ready_shots == 2
        assert s1.status == ShotStatus.ready and s2.status == ShotStatus.ready

        characters = (await db.execute(select(Character))).scalars().all()
        assert [c.name for c in characters] == ["雷霆总监"]
        assert characters[0].description == "40岁，西装外套套在T恤外"
        assert len((await db.execute(select(ShotCharacterLink))).scalars().all()) == 2
        scenes = (await db.execute(select(Scene))).scalars().all()
        assert [s.name for s in scenes] == ["开放式办公区"]
        scene_links = (await db.execute(select(ProjectSceneLink))).scalars().all()
        assert sorted(link.shot_id for link in scene_links) == ["s1", "s2"]
        assert len((await db.execute(select(ShotDialogLine))).scalars().all()) == 2

        # 幂等：再次执行不新建、不重复关联
        again = await auto_confirm_chapter(db, chapter_id="c1")
        assert again.created_entities == 0 and again.linked_candidates == 0 and again.ready_shots == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_auto_confirm_marks_never_extracted_shot_as_skip() -> None:
    db, engine = await _build_session()
    async with db:
        db.add_all(
            [
                Project(id="p1", name="x", description="", style=ProjectStyle.real_people_city, visual_style=ProjectVisualStyle.live_action),
                Chapter(id="c1", project_id="p1", index=1, title="第1集"),
            ]
        )
        await db.flush()
        db.add(Shot(id="s1", chapter_id="c1", index=1, title="手动镜头"))
        await db.flush()
        db.add(build_default_shot_detail("s1"))
        await db.flush()
        result = await auto_confirm_chapter(db, chapter_id="c1")
        assert result.skipped_shots == 1 and result.ready_shots == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_creator_board_and_overview_aggregate() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")

        board = await build_creator_board(db, chapter_id="c1")
        assert board.project.name == "大厂的神" and board.chapter.index == 1
        assert [s.index for s in board.shots] == [1, 2]
        assert board.shots[0].duration == 4 and board.shots[0].status == "ready"
        assert board.shots[0].dialogue[0].text == "各位，先自我介绍一下。"
        assert board.shots[0].character_ids and board.shots[0].scene_ids
        assert {e.type for e in board.entities} == {"character", "scene"}
        assert next(e for e in board.entities if e.type == "character").shot_count == 2
        assert board.summary.shot_count == 2 and board.summary.ready_shot_count == 2 and board.summary.total_seconds == 8
        assert board.summary.keyframe_count == 0 and board.summary.video_done_count == 0

        overview = await build_projects_overview(db)
        assert len(overview) == 1
        assert overview[0].chapter_count == 1 and overview[0].shot_count == 2 and overview[0].latest_chapter_id == "c1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_creator_edit_links_manual_entities_and_uploads() -> None:
    """创作页编辑：改镜头关联（移除后不被自动确认挂回）、手动建档、按实体设置镜头、上传图挂为形象 / 关键帧。"""
    from app.models.studio import (
        CharacterImage,
        FileItem,
        FileType,
        Prop,
        ShotCandidateStatus,
        ShotExtractedCandidate,
        ShotFrameImage,
    )
    from app.services.studio.creator_flow import (
        CreatorInputError,
        attach_entity_image,
        attach_shot_keyframe,
        create_chapter_entity,
        set_entity_shots,
        set_shot_entity_links,
    )

    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        assert character.shot_ids == ["s1", "s2"] and character.shot_count == 2
        assert board.shots[0].dialogue[0].id > 0 and board.shots[0].camera_shot

        # 从镜头 2 移除角色：关联删除、候选 ignored，再次自动确认不会挂回
        assert await set_shot_entity_links(db, shot_id="s2", entity_type="character", entity_ids=[]) == []
        cand = (await db.execute(select(ShotExtractedCandidate).where(ShotExtractedCandidate.shot_id == "s2", ShotExtractedCandidate.candidate_name == "雷霆总监"))).scalars().one()
        assert cand.candidate_status == ShotCandidateStatus.ignored
        await auto_confirm_chapter(db, chapter_id="c1")
        board = await build_creator_board(db, chapter_id="c1")
        assert board.shots[1].character_ids == []
        assert next(e for e in board.entities if e.type == "character").shot_count == 1

        # 重新挂回并保持顺序
        await set_shot_entity_links(db, shot_id="s2", entity_type="character", entity_ids=[character.id])
        board = await build_creator_board(db, chapter_id="c1")
        assert board.shots[1].character_ids == [character.id]

        # 手动新增道具挂到两个镜头 → 按实体改为只在镜头 2 → 一个都不选仍留在作品里
        prop_id, reused = await create_chapter_entity(db, chapter_id="c1", entity_type="prop", name="闪电马克杯", description="闪电造型", shot_ids=["s1", "s2"])
        assert reused is False
        board = await build_creator_board(db, chapter_id="c1")
        prop = next(e for e in board.entities if e.type == "prop")
        assert prop.id == prop_id and prop.shot_ids == ["s1", "s2"] and board.shots[0].prop_ids == [prop_id]
        assert await set_entity_shots(db, chapter_id="c1", entity_type="prop", entity_id=prop_id, shot_ids=["s2"]) == ["s2"]
        board = await build_creator_board(db, chapter_id="c1")
        assert next(e for e in board.entities if e.type == "prop").shot_ids == ["s2"] and board.shots[0].prop_ids == []
        await set_entity_shots(db, chapter_id="c1", entity_type="prop", entity_id=prop_id, shot_ids=[])
        board = await build_creator_board(db, chapter_id="c1")
        assert next(e for e in board.entities if e.type == "prop").shot_count == 0
        assert (await db.get(Prop, prop_id)) is not None

        # 其它集建档的角色也出现在本集（shot_count 0，排在后面）
        await create_chapter_entity(db, chapter_id="c1", entity_type="character", name="海洋", description="运维", shot_ids=[])
        # 同名场景全局唯一：再次"新增"沿用已有实体并挂到镜头，不报错
        scene_id, reused = await create_chapter_entity(db, chapter_id="c1", entity_type="scene", name="开放式办公区", description="", shot_ids=["s1", "s2"])
        assert reused is True and scene_id == next(e.id for e in board.entities if e.type == "scene")
        _dup_char, reused_char = await create_chapter_entity(db, chapter_id="c1", entity_type="character", name="海洋", description="穿拖鞋", shot_ids=[])
        assert reused_char is True
        board = await build_creator_board(db, chapter_id="c1")
        names = [e.name for e in board.entities if e.type == "character"]
        assert names == ["雷霆总监", "海洋"]

        # 上传图：角色主图切换、场景参考图、镜头关键帧
        db.add_all(
            [
                FileItem(id="f1", type=FileType.image, name="face.jpg", thumbnail="https://blob/face.jpg", tags=[], storage_key="files/a/face.jpg"),
                FileItem(id="f2", type=FileType.image, name="office.png", thumbnail="https://blob/office.png", tags=[], storage_key="files/b/office.png"),
            ]
        )
        await db.flush()
        image_id = await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f1")
        images = (await db.execute(select(CharacterImage).where(CharacterImage.character_id == character.id))).scalars().all()
        assert [i.id for i in images if i.is_primary] == [image_id] and images[-1].format == "jpeg"
        scene = next(e for e in board.entities if e.type == "scene")
        await attach_entity_image(db, entity_type="scene", entity_id=scene.id, file_id="f2")
        frame_id = await attach_shot_keyframe(db, shot_id="s1", file_id="f2")
        assert await attach_shot_keyframe(db, shot_id="s1", file_id="f1") == frame_id  # 覆盖同一槽位
        board = await build_creator_board(db, chapter_id="c1")
        assert next(e for e in board.entities if e.type == "character").thumbnail == "https://blob/face.jpg"
        assert next(e for e in board.entities if e.type == "scene").thumbnail == "https://blob/office.png"
        assert board.shots[0].keyframe_file_id == "f1" and board.summary.keyframe_count == 1
        frames = (await db.execute(select(ShotFrameImage).where(ShotFrameImage.shot_detail_id == "s1"))).scalars().all()
        assert len(frames) == 1

        with pytest.raises(CreatorInputError):
            await set_shot_entity_links(db, shot_id="s1", entity_type="actor", entity_ids=[])
        with pytest.raises(ValueError):
            await attach_shot_keyframe(db, shot_id="missing", file_id="f1")
    await engine.dispose()
