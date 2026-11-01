"""部署自检：验证「API → Celery broker（Vercel Queues）→ worker 函数 → 数据库」整条异步链路。

为什么存在：
- 图片/视频生成都依赖 Celery worker；在 Vercel 上 worker 是由 Vercel Queues 推送触发的独立函数，
  仅靠 HTTP 接口无法确认它能被调度、能连上数据库；
- 默认自检任务不调用任何模型供应商，不产生费用：worker 只把执行时间与运行环境写入
  `jellyfish_bootstrap_meta` 表，API 侧轮询读取即可判定链路是否通畅；
- `llm=True` 时额外用默认文本模型发送一句极短的请求（约十几个 token），验证供应商 Key 在任务执行环境中可用。
- 分派方式与业务任务一致（`settings.task_execution_mode`：inline / celery）。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.deploy_bootstrap import bootstrap_meta_table

_KEY_PREFIX = "selftest:"


def _meta_key(token: str) -> str:
    return f"{_KEY_PREFIX}{token}"


def enqueue_selftest(*, llm: bool = False) -> dict[str, str]:
    """按业务任务相同的执行方式分派一个自检任务；返回 token 供后续查询。

    参数：llm —— 是否在任务中调用默认文本模型（极小成本）。
    返回：{"token": 自检 token, "mode": inline/celery, "celery_task_id": 仅 celery 模式}
    """
    from app.config import settings

    token = uuid.uuid4().hex[:16]
    enqueued_at = datetime.now(timezone.utc).isoformat()
    mode = (settings.task_execution_mode or "").strip().lower() or "celery"
    if mode == "inline":
        from app.core.background import run_sync_in_background

        run_sync_in_background(record_selftest_sync, token, enqueued_at, llm)
        return {"token": token, "mode": mode}

    from app.tasks.deploy_selftest import run_deploy_selftest

    result = run_deploy_selftest.delay(token, enqueued_at, llm)
    return {"token": token, "mode": mode, "celery_task_id": str(result.id)}


def _probe_default_text_llm() -> str:
    """用默认文本模型发送一句极短请求，返回回复前若干字符或错误摘要。"""
    from app.core.db_sync import sync_session_maker
    from app.services.llm.runtime import build_default_text_llm_sync

    try:
        with sync_session_maker() as db:
            llm = build_default_text_llm_sync(db, thinking=False)
        reply = llm.invoke("Reply with exactly the two letters: OK")
        return f"ok: {str(getattr(reply, 'content', reply))[:40]}"
    except Exception as exc:  # noqa: BLE001
        detail = getattr(exc, "detail", None) or str(exc)
        return f"error: {type(exc).__name__}: {detail}"[:150]


def record_selftest_sync(token: str, enqueued_at: str, llm: bool = False) -> None:
    """任务侧：把执行信息写入元数据表（同步引擎，与业务任务相同的数据库通道）。"""
    from app.core.db_sync import engine_sync

    record: dict[str, object] = {
        "enqueued_at": enqueued_at,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "region": os.environ.get("VERCEL_REGION") or "",
    }
    if llm:
        record["llm"] = _probe_default_text_llm()
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(record, ensure_ascii=False)[:255]
    with engine_sync.begin() as conn:
        conn.execute(bootstrap_meta_table.delete().where(bootstrap_meta_table.c.key == _meta_key(token)))
        conn.execute(bootstrap_meta_table.insert().values(key=_meta_key(token), value=payload))


async def read_selftest(token: str) -> dict | None:
    """API 侧：读取自检结果；worker 尚未执行时返回 None。"""
    from app.core.db import engine

    async with engine.connect() as conn:
        row = (
            await conn.execute(select(bootstrap_meta_table.c.value).where(bootstrap_meta_table.c.key == _meta_key(token)))
        ).first()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return {"raw": row[0]}
