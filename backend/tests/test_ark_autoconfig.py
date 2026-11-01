"""方舟零配置接入：区域探测、零成本模型探测与按 Key 指纹缓存。"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import ark_autoconfig


def _fake_ark(
    enabled: set[str],
    *,
    valid_region: str = "byteplus",
    calls: list[str] | None = None,
    catalogue: list[str] | None = None,
) -> httpx.MockTransport:
    """模拟方舟：只有 valid_region 认可 Key；enabled 中的模型返回 400（参数错误），其余 404；/models 返回 catalogue。"""
    region_host = {"byteplus": "bytepluses.com", "volcengine": "volces.com"}[valid_region]

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(f"{request.method} {request.url.path}")
        if region_host not in request.url.host:
            return httpx.Response(401, json={"error": {"code": "AuthenticationError"}})
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in (catalogue or [])]})
        if request.method == "GET":
            return httpx.Response(200, json={"items": [], "total": 0})
        model = json.loads(request.content or b"{}").get("model")
        if model in enabled:
            return httpx.Response(400, json={"error": {"code": "InvalidParameter"}})
        return httpx.Response(404, json={"error": {"code": "InvalidEndpointOrModel.NotFound"}})

    return httpx.MockTransport(handler)


@pytest.fixture
def mock_httpx(monkeypatch: pytest.MonkeyPatch):
    """把 ark_autoconfig 内部创建的 httpx.AsyncClient 指向给定的 MockTransport。"""
    holder: dict[str, Any] = {}
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = holder["transport"]
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return holder


def test_classify_probe_response() -> None:
    assert ark_autoconfig.classify_probe_response(400, '{"error":{"code":"InvalidParameter"}}') == "available"
    assert ark_autoconfig.classify_probe_response(404, '{"error":{"code":"InvalidEndpointOrModel.NotFound"}}') == "unavailable"
    assert ark_autoconfig.classify_probe_response(404, '{"error":{"code":"ModelNotOpen"}}') == "unavailable"
    assert ark_autoconfig.classify_probe_response(401, "") == "denied"
    assert ark_autoconfig.classify_probe_response(500, "") == "unknown"


async def test_discover_picks_region_and_first_enabled_model(mock_httpx) -> None:
    # 首选文本模型未开通，第二候选开通；图片/视频首选均开通。
    mock_httpx["transport"] = _fake_ark({"seed-1-8-251228", "seedream-4-0-250828", "seedance-1-0-pro-250528"})
    plan = await ark_autoconfig.discover_ark_config("ark-test-key")
    assert plan["detected"] is True
    assert plan["region"] == "byteplus"
    assert plan["base_url"] == ark_autoconfig.ARK_BASE_URLS["byteplus"]
    assert plan["text"] == "seed-1-8-251228"
    assert plan["image"] == "seedream-4-0-250828"
    assert plan["video"] == "seedance-1-0-pro-250528"


async def test_discover_volcengine_key(mock_httpx) -> None:
    mock_httpx["transport"] = _fake_ark({"doubao-seed-1-6-250615"}, valid_region="volcengine")
    plan = await ark_autoconfig.discover_ark_config("ark-test-key")
    assert plan["region"] == "volcengine"
    assert plan["text"] == "doubao-seed-1-6-250615"
    # 未开通任何候选时保留首选（由用户在模型管理中调整）。
    assert plan["video"] == ark_autoconfig.ARK_MODEL_CANDIDATES["volcengine"]["video"][0]


async def test_resolve_plan_caches_by_key_fingerprint(mock_httpx, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.deploy_bootstrap import _meta

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(ark_autoconfig.settings, "ark_api_key", "ark-test-key")
    monkeypatch.setattr(ark_autoconfig.settings, "ark_base_url", None)
    monkeypatch.setattr(ark_autoconfig.settings, "ark_text_model", None)
    monkeypatch.setattr(ark_autoconfig.settings, "ark_image_model", None)
    monkeypatch.setattr(ark_autoconfig.settings, "ark_video_model", "my-video-override")

    calls: list[str] = []
    mock_httpx["transport"] = _fake_ark({"seed-2-0-lite-260428", "seedream-4-0-250828"}, calls=calls)
    async with maker() as session:
        first = await ark_autoconfig.resolve_ark_plan(session)
        await session.commit()
    assert first is not None and first["text"] == "seed-2-0-lite-260428"
    assert first["video"] == "my-video-override"  # 环境变量覆盖优先
    assert first["api_key"] == "ark-test-key"
    network_calls = len(calls)
    assert network_calls > 0

    async with maker() as session:
        second = await ark_autoconfig.resolve_ark_plan(session)
    assert second is not None and second["text"] == "seed-2-0-lite-260428"
    assert len(calls) == network_calls, "cached plan must not hit the network again"

    # Key 变化 → 重新探测。
    monkeypatch.setattr(ark_autoconfig.settings, "ark_api_key", "ark-another-key")
    async with maker() as session:
        await ark_autoconfig.resolve_ark_plan(session)
    assert len(calls) > network_calls
    await engine.dispose()


def test_rank_seedance_models_latest_flagship_first() -> None:
    ids = [
        "seedance-1-0-pro-250528",
        "dreamina-seedance-2-0-fast-260128",
        "dreamina-seedance-2-5-260628",
        "seedance-1-5-pro-251215",
        "dreamina-seedance-2-0-260128",
        "seedance-1-0-lite-t2v-250428",
        "seedream-4-0-250828",
    ]
    ranked = ark_autoconfig.rank_seedance_models(ids)
    assert ranked[:3] == ["dreamina-seedance-2-5-260628", "dreamina-seedance-2-0-260128", "dreamina-seedance-2-0-fast-260128"]
    assert "seedream-4-0-250828" not in ranked
    assert ranked[-1] == "seedance-1-0-lite-t2v-250428"


async def test_discover_defaults_to_latest_enabled_seedance(mock_httpx) -> None:
    # 目录里出现了比静态候选更新的 3.0；但账号只开通了 2.5 与 1.0 → 选 2.5。
    catalogue = ["dreamina-seedance-3-0-270101", "dreamina-seedance-2-5-260628", "seedance-1-0-pro-250528", "seed-2-0-lite-260428"]
    mock_httpx["transport"] = _fake_ark(
        {"dreamina-seedance-2-5-260628", "seedance-1-0-pro-250528", "seed-2-0-lite-260428", "seedream-4-0-250828"},
        catalogue=catalogue,
    )
    plan = await ark_autoconfig.discover_ark_config("ark-test-key")
    assert plan["video"] == "dreamina-seedance-2-5-260628"

    # 3.0 也开通后，自动选择最新的 3.0。
    mock_httpx["transport"] = _fake_ark({"dreamina-seedance-3-0-270101", "dreamina-seedance-2-5-260628"}, catalogue=catalogue)
    plan = await ark_autoconfig.discover_ark_config("ark-test-key")
    assert plan["video"] == "dreamina-seedance-3-0-270101"


def test_classify_probe_response_overdue_and_eu_region() -> None:
    """欠费在参数校验前返回，探测可零成本识别；欧洲区 Base URL 能被识别为独立区域。"""
    body = '{"error":{"code":"AccountOverdueError","message":"your account has an overdue balance"}}'
    assert ark_autoconfig.classify_probe_response(403, body) == "overdue"
    assert ark_autoconfig.classify_probe_response(403, '{"error":{"code":"Forbidden"}}') == "denied"
    assert ark_autoconfig.region_from_base_url("https://ark.eu-west.bytepluses.com/api/v3") == "byteplus-eu"
    assert ark_autoconfig.region_from_base_url("https://ark.ap-southeast.bytepluses.com/api/v3") == "byteplus"
    assert set(ark_autoconfig.ARK_MODEL_CANDIDATES["byteplus-eu"]) == {"text", "image", "video"}
