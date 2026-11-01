"""方舟视频请求体：Seedance 2.x 与 1.x 的差异化构造（基于 BytePlus ModelArk 实测约束）。"""

from __future__ import annotations

from app.core.contracts.video_generation import VideoGenerationInput
from app.core.integrations.volcengine.video_payload import build_create_task_body, is_seedance_v2_plus

_IMG = "data:image/png;base64,iVBORw0KGgo="


def _roles(body: dict) -> list[str]:
    return [c["role"] for c in body["content"] if c.get("type") == "image_url"]


def test_is_seedance_v2_plus() -> None:
    assert is_seedance_v2_plus("dreamina-seedance-2-5-260628")
    assert is_seedance_v2_plus("doubao-seedance-2-0-260128")
    assert not is_seedance_v2_plus("seedance-1-0-pro-250528")
    assert not is_seedance_v2_plus("seedance-1-5-pro-251215")
    assert not is_seedance_v2_plus(None)


def test_v2_first_frame_omits_ratio() -> None:
    inp = VideoGenerationInput(prompt="p", model="dreamina-seedance-2-5-260628", ratio="16:9", seconds=5, first_frame_base64=_IMG)
    body = build_create_task_body(inp)
    assert "ratio" not in body
    assert _roles(body) == ["first_frame"]
    assert body["duration"] == 5


def test_v2_text_only_keeps_ratio_and_clamps_duration() -> None:
    inp = VideoGenerationInput(prompt="p", model="dreamina-seedance-2-5-260628", ratio="9:16", seconds=2)
    body = build_create_task_body(inp)
    assert body["ratio"] == "9:16"
    assert body["duration"] == 4
    inp = VideoGenerationInput(prompt="p", model="dreamina-seedance-2-5-260628", ratio="9:16", seconds=30)
    assert build_create_task_body(inp)["duration"] == 15


def test_v2_key_frame_becomes_reference_image() -> None:
    inp = VideoGenerationInput(prompt="p", model="dreamina-seedance-2-5-260628", ratio="16:9", seconds=5, key_frame_base64=_IMG)
    body = build_create_task_body(inp)
    assert _roles(body) == ["reference_image"]
    assert body["ratio"] == "16:9"


def test_v1_payload_unchanged() -> None:
    inp = VideoGenerationInput(prompt="p", model="seedance-1-0-pro-250528", ratio="16:9", seconds=3, first_frame_base64=_IMG)
    body = build_create_task_body(inp)
    assert body["ratio"] == "16:9"
    assert body["duration"] == 3
    assert _roles(body) == ["first_frame"]


def test_ark_error_keeps_provider_code_and_message() -> None:
    import httpx
    import pytest

    from app.core.integrations.volcengine.errors import ArkApiError, raise_for_ark_status

    ok = httpx.Response(200, json={"id": "x"})
    raise_for_ark_status(ok)  # no exception
    resp = httpx.Response(403, json={"error": {"code": "AccountOverdueError", "message": "account has an overdue balance"}})
    with pytest.raises(ArkApiError) as exc:
        raise_for_ark_status(resp)
    assert "AccountOverdueError" in str(exc.value)
    assert "overdue balance" in str(exc.value)
