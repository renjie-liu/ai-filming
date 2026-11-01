"""部署诊断：汇总数据库、存储、任务执行方式与方舟（Seedance）接入状态。

为什么存在：托管环境（Vercel）下无法登录机器排障，需要一个只读接口快速判断各依赖是否就绪。
安全约束：只返回配置是否存在、方言/区域、HTTP 状态码与模型 ID 等非敏感信息，绝不返回密钥或连接串。
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import func, select, text

from app.config import is_vercel_runtime, settings
from app.services.ark_autoconfig import ARK_BASE_URLS, probe_models, resolve_ark_plan


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
    - probe_ark：对两个区域做只读连通性探测；
    - probe_model_availability：对当前区域候选模型做零成本可用性探测。
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
            ark["probes"] = [await _probe_ark_endpoint(base, plan["api_key"]) for base in ARK_BASE_URLS.values()]
        if probe_model_availability:
            ark["model_availability"] = await probe_models(plan["base_url"], plan["api_key"], region=plan.get("region"))

    broker = settings.celery_broker_url or ""
    return {
        "vercel": is_vercel_runtime(),
        "task_execution_mode": settings.task_execution_mode,
        "bootstrap": bootstrap_state(),
        "database": db_info,
        "storage_backend": storage.storage_backend(),
        "celery_broker": broker.split("://", 1)[0] + "://" if "://" in broker else broker,
        "ark": ark,
    }


def _solid_png_data_url(width: int = 640, height: int = 640) -> str:
    """生成一张纯色 PNG（data URL），用于视频接口兼容性探测的参考帧（无需 Pillow）。"""
    import base64
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    row = b"\x00" + bytes((90, 120, 160)) * width
    raw = zlib.compress(row * height, 9)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


async def probe_video_payload_compat(model: str) -> dict[str, Any]:
    """视频模型请求格式兼容性探测（零成本设计）。

    用 Jellyfish 实际的请求构造器（volcengine.video_payload.build_create_task_body）生成各参考模式的请求体，
    再把一个字段改成非法值（duration=-1 / 不支持的 ratio / 超大 duration），观察方舟返回哪个字段报错：
    - 报 duration/ratio 错误 ⇒ 其余字段（content 结构、图片角色等）已被接受；
    - 报 role / content / image 错误 ⇒ 该参考模式与模型不兼容。
    安全兜底：若意外创建了任务（2xx 且返回 id），立即调用取消接口删除。
    """
    import httpx

    from app.core.contracts.video_generation import VideoGenerationInput
    from app.core.db import async_session_maker
    from app.core.integrations.volcengine.video_payload import build_create_task_body

    async with async_session_maker() as session:
        plan = await resolve_ark_plan(session, allow_discovery=False)
    if plan is None:
        return {"error": "ark not configured"}
    base_url, api_key = plan["base_url"], plan["api_key"]
    image = _solid_png_data_url()
    shapes: dict[str, dict[str, Any]] = {
        "text_only": {},
        "first": {"first_frame_base64": image},
        "first_last": {"first_frame_base64": image, "last_frame_base64": image},
        "key": {"key_frame_base64": image},
        "first_last_key": {"first_frame_base64": image, "last_frame_base64": image, "key_frame_base64": image},
    }
    cases: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        (f"{name}/duration=-1", extra, {"duration": -1}) for name, extra in shapes.items()
    ]
    cases += [
        ("text_only/ratio=7:3", {}, {"ratio": "7:3", "duration": -1}),
        ("text_only/duration=999", {}, {"duration": 999}),
    ]

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for label, extra, overrides in cases:
            inp = VideoGenerationInput(prompt="a calm lake at sunrise", model=model, ratio="16:9", seconds=5, **extra)
            body = build_create_task_body(inp)
            body.update(overrides)
            row: dict[str, Any] = {"case": label, "roles": [c.get("role") for c in body["content"] if c.get("type") == "image_url"]}
            try:
                resp = await client.post(f"{base_url}/contents/generations/tasks", headers=headers, json=body)
                row["http"] = resp.status_code
                try:
                    payload = resp.json() or {}
                except Exception:  # noqa: BLE001
                    payload = {}
                err = payload.get("error") or {}
                row["code"] = err.get("code")
                row["message"] = str(err.get("message") or "")[:220]
                task_id = payload.get("id")
                if resp.status_code < 300 and task_id:
                    cancel = await client.delete(f"{base_url}/contents/generations/tasks/{task_id}", headers=headers)
                    row["created_then_cancelled"] = cancel.status_code
            except Exception as exc:  # noqa: BLE001
                row["error"] = f"{type(exc).__name__}: {exc}"[:200]
            results.append(row)
    return {"model": model, "base_url": base_url, "results": results}
