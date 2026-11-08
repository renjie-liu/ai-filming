"""函数被回收后遗留的 running inline 任务：超过阈值标记失败并给出可重试的中文原因。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import DeliveryMode
from app.models.task import GenerationTask, GenerationTaskStatus
from app.services.worker.async_task_support import STALE_INLINE_TASK_ERROR, fail_stale_inline_tasks


@pytest.mark.asyncio
async def test_fail_stale_inline_tasks_only_touches_old_unfinished_tasks(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'stale.db'}", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with session_local() as db:
        store = SqlAlchemyTaskStore(db)
        ids = {}
        for name in ("old_running", "fresh_running", "old_succeeded", "old_celery"):
            task = await store.create(payload={"task_kind": "video_generation"}, mode=DeliveryMode.async_polling, task_kind="video_generation")
            ids[name] = task.id
        await db.commit()
        rows = {name: await db.get(GenerationTask, tid) for name, tid in ids.items()}
        rows["old_running"].status = GenerationTaskStatus.running
        rows["old_running"].executor_type = "inline"
        rows["old_running"].started_at = now - timedelta(minutes=30)
        rows["fresh_running"].status = GenerationTaskStatus.running
        rows["fresh_running"].executor_type = "inline"
        rows["fresh_running"].started_at = now - timedelta(minutes=2)
        rows["old_succeeded"].status = GenerationTaskStatus.succeeded
        rows["old_succeeded"].executor_type = "inline"
        rows["old_succeeded"].started_at = now - timedelta(minutes=30)
        rows["old_celery"].status = GenerationTaskStatus.running
        rows["old_celery"].executor_type = "celery"
        rows["old_celery"].started_at = now - timedelta(minutes=30)
        await db.commit()

    async with session_local() as db:
        assert await fail_stale_inline_tasks(db) == 1
        assert await fail_stale_inline_tasks(db) == 0
        old = await db.get(GenerationTask, ids["old_running"])
        assert old is not None and old.status == GenerationTaskStatus.failed and old.error == STALE_INLINE_TASK_ERROR and old.finished_at is not None
        for name, expected in (("fresh_running", GenerationTaskStatus.running), ("old_succeeded", GenerationTaskStatus.succeeded), ("old_celery", GenerationTaskStatus.running)):
            row = await db.get(GenerationTask, ids[name])
            assert row is not None and row.status == expected, name
    await engine.dispose()
