"""Async worker 任务的通用辅助函数。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.task_manager import SqlAlchemyTaskStore
from app.models.task import GenerationTask, GenerationTaskStatus

# inline 执行器（Vercel 函数内后台协程）能活多久由函数 maxDuration 决定（Hobby 300 s）；
# 超过这个时长仍是 running 的任务，执行它的函数实例早已被回收，不会再有人更新它。
STALE_INLINE_TASK_SECONDS = 600
STALE_INLINE_TASK_ERROR = "任务执行超时：服务端函数在生成完成前被回收（单次最多约 5 分钟），请重试；多个镜头同时生成时建议分批"


async def cancel_if_requested_async(
    *,
    store: SqlAlchemyTaskStore,
    task_id: str,
    session: AsyncSession,
) -> bool:
    """在 async service 阶段边界执行协作式取消检查。"""

    if not await store.is_cancel_requested(task_id):
        return False
    await store.mark_cancelled(task_id)
    await session.commit()
    return True


async def fail_stale_inline_tasks(session: AsyncSession, *, max_age_seconds: int = STALE_INLINE_TASK_SECONDS) -> int:
    """把早已没人执行的 inline 任务标记为失败，返回修正的条数。

    为什么存在：Vercel 上任务在 API 函数内后台执行，函数到达 maxDuration 被回收时任务行还停在
    running / pending，前端会永远显示「生成中」、按钮也不可用。这里按「开始（或创建）时间早于阈值」
    一次性修正，并给出可操作的中文原因；在任务列表与创作板读取前调用，开销是一条 UPDATE。
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=max_age_seconds)
    started = func.coalesce(GenerationTask.started_at, GenerationTask.created_at)
    stmt = (
        update(GenerationTask)
        .where(
            GenerationTask.status.in_([GenerationTaskStatus.pending.value, GenerationTaskStatus.running.value, GenerationTaskStatus.streaming.value]),
            or_(GenerationTask.executor_type == "inline", GenerationTask.executor_type.is_(None)),
            started < cutoff,
        )
        .values(status=GenerationTaskStatus.failed.value, error=STALE_INLINE_TASK_ERROR, finished_at=datetime.now(timezone.utc).replace(tzinfo=None))
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    count = int(result.rowcount or 0)
    if count:
        await session.commit()
    return count
