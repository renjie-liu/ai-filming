"""进程内后台协程调度。

为什么存在：
- 部分轻量任务（如剧本合并、变体分析）直接在 API 进程里 `asyncio.create_task` 执行；
- 在 Vercel Functions 上，响应返回后函数实例可能被冻结，裸 `create_task` 的协程会被中断；
- 这里在 Vercel 运行时优先使用 `vercel.functions.wait_until` 延长请求生命周期
  （受函数 maxDuration 限制），其余环境保持原有 `asyncio.create_task` 行为。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from app.config import is_vercel_runtime

logger = logging.getLogger(__name__)

# 持有任务引用，避免被 GC 提前回收（asyncio 官方建议）。
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def spawn_background(coro: Coroutine[Any, Any, Any]) -> None:
    """调度一个后台协程；在 Vercel 上注册 wait_until 以保证其执行完成。"""
    task = asyncio.ensure_future(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    if not is_vercel_runtime():
        return
    try:
        from vercel.functions import wait_until

        wait_until(task)
    except Exception:  # noqa: BLE001 - 无请求上下文或 SDK 不可用时退化为普通后台任务
        logger.warning("wait_until unavailable; background task may be cut short", exc_info=True)


def run_sync_in_background(fn: Callable[..., Any], *args: Any) -> None:
    """在后台线程执行同步函数（如任务执行器的 `run(task_id)`）。

    - 有运行中的事件循环（API 请求内）：`asyncio.to_thread` + `spawn_background`，
      在 Vercel 上会注册 wait_until，响应返回后函数继续执行直到任务结束；
    - 无事件循环（脚本 / 同步上下文）：直接起守护线程。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        threading.Thread(target=fn, args=args, daemon=True, name="jellyfish-inline-task").start()
        return
    spawn_background(asyncio.to_thread(fn, *args))
