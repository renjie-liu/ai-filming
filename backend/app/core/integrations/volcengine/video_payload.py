"""火山方舟视频：content 与 ratio。

Seedance 2.x（如 dreamina-seedance-2-5-260628）与 1.x 的请求约束差异（已在 BytePlus ModelArk 上实测）：
- 带首帧 / 首尾帧时输出比例跟随首帧图片，传 `ratio` 会被拒绝（InvalidParameter.TaskTypeConstraint），需省略；
- 图片角色不支持 `key_frame`，参考图应使用 `reference_image`；
- 时长按 2.x 支持区间收敛到 [4, 15] 秒。
"""

from __future__ import annotations

import re
from typing import Any

from app.core.integrations.openai.video_payload import to_image_data_url
from app.core.integrations.video_capabilities import resolve_effective_ratio
from app.core.integrations.volcengine.video_capabilities import validate_volcengine_video_options
from app.core.contracts.video_generation import VideoGenerationInput, _strip_optional_b64


_SEEDANCE_VERSION_RE = re.compile(r"seedance-(\d+)-(\d+)")
_SEEDANCE_2X_DURATION_RANGE = (4, 15)


def is_seedance_v2_plus(model: str | None) -> bool:
    """模型是否为 Seedance 2.x 及以上（按模型 ID 中的版本号判断）。"""
    match = _SEEDANCE_VERSION_RE.search((model or "").lower())
    return bool(match) and int(match.group(1)) >= 2


def build_content(input_: VideoGenerationInput) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    prompt = (input_.prompt or "").strip()
    if prompt:
        items.append({"type": "text", "text": prompt})

    ff = _strip_optional_b64(input_.first_frame_base64)
    if ff:
        items.append(
            {
                "type": "image_url",
                "role": "first_frame",
                "image_url": {"url": to_image_data_url(ff)},
            }
        )
    lf = _strip_optional_b64(input_.last_frame_base64)
    if lf:
        items.append(
            {
                "type": "image_url",
                "role": "last_frame",
                "image_url": {"url": to_image_data_url(lf)},
            }
        )
    kf = _strip_optional_b64(input_.key_frame_base64)
    if kf:
        items.append(
            {
                "type": "image_url",
                # Seedance 2.x 不接受 key_frame 角色，关键帧作为参考图（reference_image）传入。
                "role": "reference_image" if is_seedance_v2_plus(input_.model) else "key_frame",
                "image_url": {"url": to_image_data_url(kf)},
            }
        )
    return items


def build_create_task_body(input_: VideoGenerationInput) -> dict[str, Any]:
    validate_volcengine_video_options(input_)
    content = build_content(input_)
    if not content:
        raise RuntimeError("Volcengine video requires non-empty content (prompt and/or reference frames)")

    effective_ratio = resolve_effective_ratio(input_)
    v2_plus = is_seedance_v2_plus(input_.model)
    has_frame_image = bool(_strip_optional_b64(input_.first_frame_base64) or _strip_optional_b64(input_.last_frame_base64))
    body: dict[str, Any] = {"content": content}
    if not (v2_plus and has_frame_image):
        # Seedance 2.x 首帧 / 首尾帧模式下比例由首帧图片决定，不能再传 ratio。
        body["ratio"] = effective_ratio
    if input_.model:
        body["model"] = input_.model
    if input_.seconds is not None:
        seconds = int(input_.seconds)
        if v2_plus:
            low, high = _SEEDANCE_2X_DURATION_RANGE
            seconds = min(max(seconds, low), high)
        body["duration"] = seconds
    if input_.seed is not None:
        body["seed"] = int(input_.seed)
    if input_.watermark is not None:
        body["watermark"] = bool(input_.watermark)
    return body
