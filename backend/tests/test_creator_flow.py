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
from app.services.studio.creator_flow import auto_confirm_chapter, build_creator_board, build_projects_overview
from app.services.studio.shot_detail_defaults import build_default_shot_detail
from app.services.studio.shot_extracted_candidates import replace_for_shot as replace_candidates
from app.services.studio.shot_extracted_dialogue_candidates import replace_for_shot as replace_dialogue_candidates


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
