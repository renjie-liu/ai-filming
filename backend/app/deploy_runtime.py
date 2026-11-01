"""启动引导的运行时包装：确保每个进程只执行一次，并记录结果供状态接口查询。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_state: dict[str, Any] = {"done": False, "summary": None, "error": None, "elapsed_ms": None}


def bootstrap_state() -> dict[str, Any]:
    return dict(_state)


async def ensure_bootstrapped() -> None:
    """若开启 auto_init_db，则在本进程首次调用时运行部署引导；失败不抛出（记录在状态中）。"""
    if not settings.auto_init_db or _state["done"]:
        return
    async with _lock:
        if _state["done"]:
            return
        from app.deploy_bootstrap import run_deploy_bootstrap

        t0 = time.perf_counter()
        try:
            _state["summary"] = await run_deploy_bootstrap()
            _state["error"] = None
        except Exception as exc:  # noqa: BLE001
            logger.exception("deploy bootstrap failed")
            _state["error"] = f"{type(exc).__name__}: {exc}"[:1000]
        finally:
            _state["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
            # 失败也标记 done，避免每个请求都重试拖慢响应；重新部署/冷启动会再次尝试。
            _state["done"] = True
