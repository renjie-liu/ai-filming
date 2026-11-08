"""部署诊断：汇总数据库、存储、任务执行方式与方舟（Seedance）接入状态。

为什么存在：托管环境（Vercel）下无法登录机器排障，需要一个只读接口快速判断各依赖是否就绪。
安全约束：只返回配置是否存在、方言/区域、HTTP 状态码与模型 ID 等非敏感信息，绝不返回密钥或连接串。
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select, text

from app.config import is_vercel_runtime, settings
from app.services.ark_autoconfig import ARK_BASE_URLS, probe_models, rank_seedance_models, resolve_ark_plan


async def _probe_ark_endpoint(base_url: str, api_key: str) -> dict[str, Any]:
    """只读探测某个区域：列出视频任务 + 列出模型目录（均不产生生成费用）。"""
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
                out["models"] = [i for i in ids if any(k in i.lower() for k in ("seed", "doubao", "skylark"))][:200]
                out["models_total"] = len(ids)
            else:
                out["models_error"] = r.text[:300]
        except Exception as exc:  # noqa: BLE001
            out["models_error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


async def build_deploy_status(*, probe_ark: bool = False, probe_model_availability: bool = False) -> dict[str, Any]:
    """生成部署状态报告。

    参数：
    - probe_ark：对所有已知区域做只读连通性探测；
    - probe_model_availability：对当前区域候选模型做零成本可用性探测；
      两者同时开启时，也对 Key 被认可的其它区域做同样的探测（结果在 model_availability_other_regions）。
    """
    from app.core import storage
    from app.core.db import async_session_maker, engine
    from app.deploy_runtime import bootstrap_state, ensure_bootstrapped
    from app.models.llm import Model, ModelSettings, Provider
    from app.models.studio import PromptTemplate

    await ensure_bootstrapped()

    db_info: dict[str, Any] = {"dialect": engine.dialect.name}
    plan: dict[str, Any] | None = None
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
            db_info["providers"] = (await session.execute(select(func.count()).select_from(Provider))).scalar_one()
            db_info["models"] = (await session.execute(select(func.count()).select_from(Model))).scalar_one()
            db_info["prompt_templates"] = (await session.execute(select(func.count()).select_from(PromptTemplate))).scalar_one()
            row = await session.get(ModelSettings, 1)
            db_info["default_models"] = (
                {"text": row.default_text_model_id, "image": row.default_image_model_id, "video": row.default_video_model_id}
                if row
                else None
            )
            plan = await resolve_ark_plan(session, allow_discovery=False)
        db_info["ok"] = True
    except Exception as exc:  # noqa: BLE001
        db_info["ok"] = False
        db_info["error"] = f"{type(exc).__name__}: {exc}"[:500]

    ark: dict[str, Any] = {"configured": plan is not None}
    if plan is not None:
        ark.update({k: plan.get(k) for k in ("region", "base_url", "text", "image", "video", "detected")})
        if probe_ark:
            ark["probes"] = [{"region": r, **await _probe_ark_endpoint(base, plan["api_key"])} for r, base in ARK_BASE_URLS.items()]
        if probe_model_availability:
            ark["model_availability"] = await probe_models(plan["base_url"], plan["api_key"], region=plan.get("region"))
        if probe_ark and probe_model_availability:
            # Key / 开通 / 计费状态按区域隔离：对 Key 被认可的其它区域也做零成本探测，便于判断能否换区。
            by_region: dict[str, Any] = {}
            for probe in ark["probes"]:
                region = probe["region"]
                if region == plan.get("region") or 200 not in (probe.get("models_status"), probe.get("video_tasks_status")):
                    continue
                extra = {"video": rank_seedance_models(probe.get("models") or [])}
                by_region[region] = await probe_models(ARK_BASE_URLS[region], plan["api_key"], region=region, extra=extra)
            ark["model_availability_other_regions"] = by_region

    # 存储：配置摘要 + 一次轻量只读探测（S3/R2 HeadBucket；Blob head 一个不存在的路径，能看出「已暂停」）
    from app.services.studio.direct_upload import direct_upload_backend

    storage_info = storage.describe_storage()
    storage_info["direct_upload"] = direct_upload_backend()
    storage_info.update(await storage.probe_storage())

    broker = settings.celery_broker_url or ""
    return {
        "vercel": is_vercel_runtime(),
        "task_execution_mode": settings.task_execution_mode,
        "bootstrap": bootstrap_state(),
        "database": db_info,
        "storage_backend": storage_info["backend"],
        "storage": storage_info,
        "celery_broker": broker.split("://", 1)[0] + "://" if "://" in broker else broker,
        "ark": ark,
    }

