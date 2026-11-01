"""部署自检：验证「API → Celery broker（Vercel Queues）→ worker 函数 → 数据库」整条异步链路。

为什么存在：
- 图片/视频生成都依赖 Celery worker；在 Vercel 上 worker 是由 Vercel Queues 推送触发的独立函数，
  仅靠 HTTP 接口无法确认它能被调度、能连上数据库；
- 自检任务不调用任何模型供应商，不产生费用：worker 只把执行时间与运行环境写入
  `jellyfish_bootstrap_meta` 表，API 侧轮询读取即可判定链路是否通畅。
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


def enqueue_selftest() -> dict[str, str]:
    """投递一个自检任务；返回 token 供后续查询。

    返回：{"token": 自检 token, "celery_task_id": broker 返回的消息 id}
    """
    from app.tasks.deploy_selftest import run_deploy_selftest

    token = uuid.uuid4().hex[:16]
    result = run_deploy_selftest.delay(token, datetime.now(timezone.utc).isoformat())
    return {"token": token, "celery_task_id": str(result.id)}


def record_selftest_sync(token: str, enqueued_at: str) -> None:
    """worker 侧：把执行信息写入元数据表（同步引擎，与业务 worker 相同的数据库通道）。"""
    from app.core.db_sync import engine_sync

    payload = json.dumps(
        {
            "enqueued_at": enqueued_at,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "region": os.environ.get("VERCEL_REGION") or "",
            "pid": os.getpid(),
        },
        ensure_ascii=False,
    )[:255]
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
