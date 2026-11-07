"""镜头细节默认值：手动新建镜头会同时创建 ShotDetail；存量缺失可被幂等补齐。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.studio import Chapter, Project, ProjectStyle, ProjectVisualStyle, Shot, ShotDetail
from app.schemas.studio.shots import ShotCreate
from app.services.studio.shot_detail_defaults import (
    DEFAULT_SHOT_DURATION_SECONDS,
    backfill_missing_shot_details,
    build_default_shot_detail,
)
from app.services.studio.shots import create as create_shot


async def _build_session() -> tuple[AsyncSession, object]:
    """内存 SQLite 会话（含全部表）。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_chapter(db: AsyncSession) -> None:
    """写入项目与章节，供镜头挂载。"""
    db.add_all(
        [
            Project(
                id="p1",
                name="项目",
                description="",
                style=ProjectStyle.real_people_city,
                visual_style=ProjectVisualStyle.live_action,
            ),
            Chapter(id="c1", project_id="p1", index=1, title="第一章"),
        ]
    )
    await db.flush()


@pytest.mark.asyncio
async def test_create_shot_also_creates_default_detail() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_chapter(db)
        shot = await create_shot(db, body=ShotCreate(id="s1", chapter_id="c1", index=1, title="介绍"))
        detail = await db.get(ShotDetail, shot.id)
        assert detail is not None
        assert detail.duration == DEFAULT_SHOT_DURATION_SECONDS
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_missing_shot_details_is_idempotent() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_chapter(db)
        # 模拟旧版本手动新建、没有 ShotDetail 的镜头。
        db.add_all([Shot(id="old-1", chapter_id="c1", index=1, title="旧镜头一"), Shot(id="old-2", chapter_id="c1", index=2, title="旧镜头二")])
        await db.flush()
        existing = build_default_shot_detail("old-2")
        existing.duration = 9
        db.add(existing)
        await db.flush()

        assert await backfill_missing_shot_details(db) == 1
        assert (await db.get(ShotDetail, "old-1")).duration == DEFAULT_SHOT_DURATION_SECONDS
        assert (await db.get(ShotDetail, "old-2")).duration == 9  # 已有细节不被覆盖
        assert await backfill_missing_shot_details(db) == 0
    await engine.dispose()
