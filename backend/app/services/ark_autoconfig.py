"""方舟（BytePlus ModelArk / 火山方舟）零配置接入：只需一个 API Key。

为什么存在：
- 部署者只想填一个 Seedance Key，不应关心区域 Base URL、模型 ID 是否已在账号中开通；
- 方舟 `/models` 返回的是模型目录，并不代表账号已开通，直接写死模型 ID 会出现
  `InvalidEndpointOrModel.NotFound`；
- 这里在首次启动（或 Key 变化）时自动完成：
  1. 区域探测：用只读的「列出视频任务」接口判断 Key 属于 BytePlus 国际站还是火山方舟国内站；
  2. 模型探测：对候选模型发送故意缺少必填字段的请求，400 = 已开通、404/ModelNotOpen = 未开通，
     全程不触发任何生成计费；视频默认选用账号已开通的「最新版」Seedance（按目录中的版本号排序）；
  3. 结果按 Key 指纹缓存到 `jellyfish_bootstrap_meta`，之后冷启动不再发起网络请求。

环境变量 ARK_BASE_URL / ARK_TEXT_MODEL / ARK_IMAGE_MODEL / ARK_VIDEO_MODEL 仍可选地覆盖探测结果。
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

ARK_BASE_URLS: dict[str, str] = {
    "byteplus": "https://ark.ap-southeast.bytepluses.com/api/v3",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
}

ARK_REGION_LABELS: dict[str, str] = {
    "byteplus": "BytePlus ModelArk",
    "volcengine": "火山方舟",
}

# 候选模型按优先级排列：优先选择与 Jellyfish 现有请求格式（Seedream 4.x 尺寸档位、Seedance 1.x content 结构）
# 兼容且性价比高的模型；探测时取第一个已开通的。
ARK_MODEL_CANDIDATES: dict[str, dict[str, list[str]]] = {
    "byteplus": {
        "text": [
            "seed-2-0-lite-260428",
            "seed-1-8-251228",
            "seed-2-0-pro-260328",
            "seed-2-0-mini-260428",
            "seed-1-6-250915",
            "seed-1-6-flash-250715",
        ],
        "image": [
            "seedream-4-0-250828",
            "seedream-4-5-251128",
            "seedream-5-0-260128",
        ],
        # 视频：默认选用账号已开通的「最新版」Seedance；实际顺序以 /models 目录动态排序为准（见 rank_seedance_models）。
        "video": [
            "dreamina-seedance-2-5-260628",
            "dreamina-seedance-2-0-260128",
            "seedance-1-5-pro-251215",
            "seedance-1-0-pro-250528",
            "seedance-1-0-pro-fast-251015",
        ],
    },
    "volcengine": {
        "text": [
            "doubao-seed-1-6-250615",
            "doubao-seed-1-8-251228",
            "doubao-seed-1-6-flash-250715",
        ],
        "image": [
            "doubao-seedream-4-0-250828",
            "doubao-seedream-4-5-251128",
        ],
        "video": [
            "doubao-seedance-2-0-260128",
            "doubao-seedance-1-5-pro-251215",
            "doubao-seedance-1-0-pro-250528",
            "doubao-seedance-1-0-pro-fast-251015",
        ],
    },
}

# 每个类别的「零成本探测」请求：故意缺少必填字段，已开通的模型会返回参数校验错误而不会生成内容。
_PROBE_REQUESTS: dict[str, tuple[str, Any]] = {
    "text": ("/chat/completions", lambda model: {"model": model, "messages": []}),
    "image": ("/images/generations", lambda model: {"model": model}),
    "video": ("/contents/generations/tasks", lambda model: {"model": model, "content": []}),
}

_CATEGORIES = ("text", "image", "video")
_CACHE_PREFIX = "ark_autoconfig:"
# 选型策略版本：策略变化（如改为「最新 Seedance」）时递增，使已缓存的探测结果失效并重新探测。
_AUTOCONFIG_STRATEGY_VERSION = "2"

_SEEDANCE_ID_RE = re.compile(r"seedance-(\d+)-(\d+)(?:-([a-z0-9-]+?))?-(\d{6,8})$")


def _seedance_rank(model_id: str) -> tuple[int, int, int, int] | None:
    """Seedance 模型排序键（越小越优先）：版本号降序 → 旗舰优先（pro/无后缀 > fast > mini/lite > t2v/i2v）→ 日期降序。"""
    match = _SEEDANCE_ID_RE.search(model_id.lower())
    if not match:
        return None
    major, minor, variant, date = match.group(1), match.group(2), match.group(3) or "", match.group(4)
    if any(tag in variant for tag in ("t2v", "i2v")):
        tier = 3
    elif any(tag in variant for tag in ("mini", "lite")):
        tier = 2
    elif "fast" in variant:
        tier = 1
    else:
        tier = 0
    return (-int(major), -int(minor), tier, -int(date))


def rank_seedance_models(model_ids: list[str]) -> list[str]:
    """把 Seedance 模型 ID 按「最新、旗舰优先」排序；非 Seedance ID 被忽略。"""
    ranked = [(rank, mid) for mid in model_ids if (rank := _seedance_rank(mid)) is not None]
    return [mid for _, mid in sorted(ranked)]


async def _list_catalogue(client: Any, *, base_url: str, api_key: str) -> list[str]:
    """读取方舟模型目录（只读）；失败时返回空列表。"""
    try:
        resp = await client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code >= 400:
            return []
        data = (resp.json() or {}).get("data") or []
        return [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
    except Exception:  # noqa: BLE001
        return []


def api_key_fingerprint(api_key: str) -> str:
    """API Key 指纹（仅用于判断 Key 是否变化，不可逆）。"""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def region_from_base_url(base_url: str | None) -> str:
    """根据 Base URL 推断区域；无法判断时按 BytePlus 处理。"""
    value = (base_url or "").lower()
    if "volces.com" in value or "volcengine" in value:
        return "volcengine"
    return "byteplus"


def classify_probe_response(status_code: int, body: str) -> str:
    """把探测响应归类：available / unavailable / denied / unknown。"""
    lowered = body.lower()
    if status_code == 404 or "notfound" in lowered or "modelnotopen" in lowered or "not activated" in lowered:
        return "unavailable"
    if status_code in (401, 403):
        return "denied"
    if status_code in (400, 422) or status_code < 300:
        return "available"
    return "unknown"


async def probe_model(client: Any, *, base_url: str, api_key: str, category: str, model: str) -> dict[str, Any]:
    """对单个模型做零成本可用性探测，返回 {model, result, http, code}。"""
    path, body_fn = _PROBE_REQUESTS[category]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = await client.post(f"{base_url}{path}", headers=headers, json=body_fn(model))
    except Exception as exc:  # noqa: BLE001
        return {"model": model, "result": "unknown", "error": type(exc).__name__}
    code = ""
    try:
        code = str(((resp.json() or {}).get("error") or {}).get("code") or "")
    except Exception:  # noqa: BLE001
        code = ""
    return {"model": model, "result": classify_probe_response(resp.status_code, resp.text), "http": resp.status_code, "code": code}


async def probe_models(base_url: str, api_key: str, *, region: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """对某区域全部候选模型逐个探测（供状态页诊断使用）。"""
    import httpx

    candidates = ARK_MODEL_CANDIDATES[region or region_from_base_url(base_url)]
    out: dict[str, list[dict[str, Any]]] = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for category in _CATEGORIES:
            out[category] = [
                await probe_model(client, base_url=base_url, api_key=api_key, category=category, model=model)
                for model in candidates[category]
            ]
    return out


async def _detect_region(client: Any, api_key: str) -> str | None:
    """用只读接口判断 Key 所属区域；两个区域都不认可时返回 None。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    for region, base_url in ARK_BASE_URLS.items():
        try:
            resp = await client.get(
                f"{base_url}/contents/generations/tasks",
                params={"page_num": 1, "page_size": 1},
                headers=headers,
            )
        except Exception:  # noqa: BLE001
            continue
        if resp.status_code == 200:
            return region
    return None


async def discover_ark_config(api_key: str, *, base_url_override: str | None = None) -> dict[str, Any]:
    """联网探测区域与每个类别第一个已开通的模型。

    返回：{region, base_url, text, image, video, detected: bool}
    - detected=False 表示网络 / 鉴权异常，结果为静态默认值，调用方不应缓存。
    """
    import httpx

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=15) as client:
        if base_url_override:
            region = region_from_base_url(base_url_override)
            base_url = base_url_override.rstrip("/")
            detected_region: str | None = region
        else:
            detected_region = await _detect_region(client, api_key)
            region = detected_region or "byteplus"
            base_url = ARK_BASE_URLS[region]

        plan: dict[str, Any] = {"region": region, "base_url": base_url, "detected": detected_region is not None}
        catalogue = await _list_catalogue(client, base_url=base_url, api_key=api_key) if detected_region else []
        for category in _CATEGORIES:
            candidates = list(ARK_MODEL_CANDIDATES[region][category])
            if category == "video":
                # 优先目录中的最新 Seedance（新版本发布后无需改代码），再兜底静态候选。
                ranked = rank_seedance_models(catalogue)
                candidates = ranked + [m for m in rank_seedance_models(candidates) if m not in ranked]
            chosen = candidates[0]
            if detected_region is not None:
                for model in candidates:
                    row = await probe_model(client, base_url=base_url, api_key=api_key, category=category, model=model)
                    if row["result"] == "available":
                        chosen = model
                        break
                    if row["result"] == "unknown":
                        # 网络异常：不确定可用性，保守沿用首选并标记为未完成探测。
                        plan["detected"] = False
                        break
            plan[category] = chosen

    logger.info(
        "ark autoconfig: region=%s detected=%s models=%s/%s/%s in %dms",
        plan["region"],
        plan["detected"],
        plan["text"],
        plan["image"],
        plan["video"],
        int((time.perf_counter() - started) * 1000),
    )
    return plan


async def _read_cache(session: AsyncSession) -> dict[str, str]:
    from app.deploy_bootstrap import bootstrap_meta_table as meta

    rows = (await session.execute(select(meta.c.key, meta.c.value).where(meta.c.key.like(f"{_CACHE_PREFIX}%")))).all()
    return {key.removeprefix(_CACHE_PREFIX): value for key, value in rows}


async def _write_cache(session: AsyncSession, values: dict[str, str]) -> None:
    from app.deploy_bootstrap import bootstrap_meta_table as meta

    keys = [f"{_CACHE_PREFIX}{k}" for k in values]
    await session.execute(meta.delete().where(meta.c.key.in_(keys)))
    await session.execute(
        meta.insert(),
        [{"key": f"{_CACHE_PREFIX}{k}", "value": str(v)[:255]} for k, v in values.items()],
    )


def configured_api_key() -> str | None:
    """部署环境中提供的方舟 API Key（多个常见变量名任取其一）。"""
    return (settings.ark_api_key or "").strip() or None


async def resolve_ark_plan(session: AsyncSession, *, allow_discovery: bool = True) -> dict[str, Any] | None:
    """返回当前生效的方舟接入方案（含 api_key）；未配置 Key 时返回 None。

    优先级：环境变量覆盖 > 已缓存的探测结果（Key 指纹一致）> 本次联网探测 > 静态默认值。
    - allow_discovery=False 时不发起网络请求（供状态展示等只读场景）。
    """
    api_key = configured_api_key()
    if api_key is None:
        return None

    fingerprint = api_key_fingerprint(api_key)
    override_base = (settings.ark_base_url or "").strip().rstrip("/")
    cache = await _read_cache(session)
    cache_valid = (
        cache.get("key_fp") == fingerprint
        and cache.get("base_override", "") == override_base
        and cache.get("strategy", "") == _AUTOCONFIG_STRATEGY_VERSION
    )

    if cache_valid:
        base = {k: cache[k] for k in ("region", "base_url", *_CATEGORIES) if k in cache}
        base["detected"] = True
    elif allow_discovery:
        base = await discover_ark_config(api_key, base_url_override=override_base or None)
        if base.get("detected"):
            await _write_cache(
                session,
                {
                    "key_fp": fingerprint,
                    "base_override": override_base,
                    "strategy": _AUTOCONFIG_STRATEGY_VERSION,
                    **{k: base[k] for k in ("region", "base_url", *_CATEGORIES)},
                },
            )
    else:
        region = region_from_base_url(override_base) if override_base else "byteplus"
        base = {
            "region": region,
            "base_url": override_base or ARK_BASE_URLS[region],
            **{c: ARK_MODEL_CANDIDATES[region][c][0] for c in _CATEGORIES},
            "detected": False,
        }

    plan: dict[str, Any] = dict(base)
    plan["api_key"] = api_key
    for category, override in (
        ("text", settings.ark_text_model),
        ("image", settings.ark_image_model),
        ("video", settings.ark_video_model),
    ):
        if (override or "").strip():
            plan[category] = override.strip()
    return plan
