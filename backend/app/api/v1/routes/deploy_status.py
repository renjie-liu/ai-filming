"""部署状态接口：用于在 Vercel 等托管环境中自检数据库、存储、队列与方舟（Seedance）连通性。

安全约束：只返回配置是否存在、方言/区域、HTTP 状态码与模型 ID 等非敏感信息，绝不返回任何密钥或连接串。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.config import is_vercel_runtime, settings
from app.schemas.common import ApiResponse, success_response

router = APIRouter()

_ARK_BASES = {
    "byteplus": "https://ark.ap-southeast.bytepluses.com/api/v3",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}


async def _probe_ark(base_url: str, api_key: str) -> dict[str, Any]:
    """只读探测：列出模型 + 列出视频任务（不会产生生成费用）。"""
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"}
    out: dict[str, Any] = {"base_url": base_url}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            t0 = time.perf_counter()
            r = await client.get(f"{base_url}/contents/generations/tasks", params={"page_num": 1, "page_size": 1}, headers=headers)
            out["video_tasks_status"] = r.status_code
            out["video_tasks_ms"] = int((time.perf_counter() - t0) * 1000)
            if r.status_code >= 400:
                out["video_tasks_error"] = r.text[:300]
        except Exception as exc:  # noqa: BLE001
            out["video_tasks_error"] = f"{type(exc).__name__}: {exc}"[:300]
        try:
            r = await client.get(f"{base_url}/models", headers=headers)
            out["models_status"] = r.status_code
            if r.status_code < 400:
                data = r.json().get("data") or []
                ids = sorted({str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id")})
                interesting = [i for i in ids if any(k in i.lower() for k in ("seed", "doubao", "skylark"))]
                out["models"] = interesting[:200]
                out["models_total"] = len(ids)
            else:
                out["models_error"] = r.text[:300]
        except Exception as exc:  # noqa: BLE001
            out["models_error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


@router.get("/_deploy/status", response_model=ApiResponse[dict])
async def deploy_status(probe_ark: bool = Query(False, description="是否对方舟 API 做只读连通性探测")) -> ApiResponse[dict]:
    from app.core import storage
    from app.core.db import async_session_maker, engine
    from app.deploy_bootstrap import ark_seed_plan
    from app.deploy_runtime import bootstrap_state, ensure_bootstrapped

    await ensure_bootstrapped()

    db_info: dict[str, Any] = {"dialect": engine.dialect.name}
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            from app.models.llm import Model, ModelSettings, Provider
            from app.models.studio import PromptTemplate
            from sqlalchemy import func, select

            db_info["providers"] = (await session.execute(select(func.count()).select_from(Provider))).scalar_one()
            db_info["models"] = (await session.execute(select(func.count()).select_from(Model))).scalar_one()
            db_info["prompt_templates"] = (await session.execute(select(func.count()).select_from(PromptTemplate))).scalar_one()
            row = await session.get(ModelSettings, 1)
            db_info["default_models"] = (
                {
                    "text": row.default_text_model_id,
                    "image": row.default_image_model_id,
                    "video": row.default_video_model_id,
                }
                if row
                else None
            )
        db_info["ok"] = True
    except Exception as exc:  # noqa: BLE001
        db_info["ok"] = False
        db_info["error"] = f"{type(exc).__name__}: {exc}"[:500]

    plan = ark_seed_plan()
    ark: dict[str, Any] = {"configured": plan is not None}
    if plan is not None:
        ark.update({k: plan[k] for k in ("region", "base_url", "text", "image", "video")})
        if probe_ark:
            ark["probes"] = [await _probe_ark(base, plan["api_key"]) for base in _ARK_BASES.values()]

    broker = settings.celery_broker_url or ""
    data = {
        "vercel": is_vercel_runtime(),
        "bootstrap": bootstrap_state(),
        "database": db_info,
        "storage_backend": storage.storage_backend(),
        "celery_broker": broker.split("://", 1)[0] + "://" if "://" in broker else broker,
        "ark": ark,
    }
    return success_response(data=data)


@router.get("/_deploy/selftest", response_model=ApiResponse[dict])
async def deploy_selftest_start() -> ApiResponse[dict]:
    """投递一个无费用的自检任务，验证 Celery broker → worker → 数据库链路；返回 token。

    使用 GET 便于在浏览器中直接打开（接口受部署保护，且不调用任何模型供应商）。
    """
    from app.services.deploy_selftest import enqueue_selftest

    return success_response(data=enqueue_selftest())


@router.get("/_deploy/selftest/{token}", response_model=ApiResponse[dict])
async def deploy_selftest_result(token: str) -> ApiResponse[dict]:
    """查询自检结果：`done=false` 表示 worker 尚未执行（或队列未投递）。"""
    from app.services.deploy_selftest import read_selftest

    result = await read_selftest(token)
    return success_response(data={"token": token, "done": result is not None, "result": result})
