"""火山方舟视频：content 与 ratio。

Seedance 2.x（如 dreamina-seedance-2-5-260628）与 1.x 的请求约束差异
（依据 BytePlus「Dreamina Seedance 2.5 tutorial」并已在 ModelArk 上实测）：
- 首帧 / 首尾帧任务的 `ratio` 只能为 `adaptive`（输出比例跟随首帧图片），传具体比例会被拒绝
  （InvalidParameter.TaskTypeConstraint）；纯文本生成不受限制，仍传业务比例；
- 图片角色不支持 `key_frame`，参考图应使用 `reference_image`；
- 时长区间：Seedance 2.5 及以上为 [4, 30] 秒，2.0 系列为 [4, 15] 秒，超出时收敛到区间内。
"""

from __future__ import annotations

import re
from typing import Any

from app.core.contracts.video_generation import (
    VideoGenerationInput,
    _strip_optional_b64,
)
from app.core.integrations.openai.video_payload import to_image_data_url
from app.core.integrations.video_capabilities import resolve_effective_ratio
from app.core.integrations.volcengine.video_capabilities import (
    validate_volcengine_video_options,
)

_SEEDANCE_VERSION_RE = re.compile(r"seedance-(\d+)-(\d+)")
_SEEDANCE_20_DURATION_RANGE = (4, 15)
_SEEDANCE_25_DURATION_RANGE = (4, 30)
# Seedance 2.x 首帧 / 首尾帧任务唯一允许的比例取值。
_SEEDANCE_V2_FRAME_RATIO = "adaptive"


def _seedance_version(model: str | None) -> tuple[int, int] | None:
    """从模型 ID 中解析 Seedance 主 / 次版本号；非 Seedance 模型返回 None。"""
    match = _SEEDANCE_VERSION_RE.search((model or "").lower())
    return (int(match.group(1)), int(match.group(2))) if match else None


def supports_last_frame(model: str | None) -> bool:
    """模型是否支持 `return_last_frame`（官方：Seedance 2.5、2.0 系列、1.5 pro、1.0 pro / pro fast）。"""
    name = (model or "").lower()
    return is_seedance_v2_plus(model) or bool(re.search(r"seedance-1-[05]-pro", name))


def is_seedance_v2_plus(model: str | None) -> bool:
    """模型是否为 Seedance 2.x 及以上（按模型 ID 中的版本号判断）。"""
    version = _seedance_version(model)
    return version is not None and version[0] >= 2


def seedance_v2_duration_range(model: str | None) -> tuple[int, int]:
    """Seedance 2.x 的时长区间（秒）：2.5 及以上 [4, 30]，2.0 系列 [4, 15]。"""
    version = _seedance_version(model) or (2, 0)
    return _SEEDANCE_25_DURATION_RANGE if version >= (2, 5) else _SEEDANCE_20_DURATION_RANGE


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
    # 全能参考：角色 / 场景 / 道具形象图按顺序对应提示词里的 [Image n]；公网 URL 直接透传，避免 base64 撑爆请求体。
    for ref in input_.reference_images:
        value = _strip_optional_b64(ref)
        if not value:
            continue
        items.append({"type": "image_url", "role": "reference_image", "image_url": {"url": to_image_url_value(value)}})
    audio = _strip_optional_b64(input_.reference_audio)
    if audio:
        # 音频参考只接受公网 URL / data URL（方舟按 URL 拉取；2.0 需同时带图片或视频，2.5 可单独驱动）
        items.append({"type": "audio_url", "role": "reference_audio", "audio_url": {"url": audio}})
    return items


def to_image_url_value(value: str) -> str:
    """参考图取值：http(s) 公网地址原样传给方舟，其它视为 base64 / data URL。"""
    v = value.strip()
    if v.startswith("http://") or v.startswith("https://"):
        return v
    return to_image_data_url(v)


def build_create_task_body(input_: VideoGenerationInput) -> dict[str, Any]:
    validate_volcengine_video_options(input_)
    content = build_content(input_)
    if not content:
        raise RuntimeError("Volcengine video requires non-empty content (prompt and/or reference frames)")

    effective_ratio = resolve_effective_ratio(input_)
    v2_plus = is_seedance_v2_plus(input_.model)
    has_frame_image = bool(_strip_optional_b64(input_.first_frame_base64) or _strip_optional_b64(input_.last_frame_base64))
    body: dict[str, Any] = {"content": content}
    # Seedance 2.x 首帧 / 首尾帧模式下比例由首帧图片决定，按官方要求固定传 adaptive。
    body["ratio"] = _SEEDANCE_V2_FRAME_RATIO if (v2_plus and has_frame_image) else effective_ratio
    if input_.model:
        body["model"] = input_.model
    if input_.seconds is not None:
        seconds = int(input_.seconds)
        if v2_plus:
            low, high = seedance_v2_duration_range(input_.model)
            seconds = min(max(seconds, low), high)
        body["duration"] = seconds
    if input_.seed is not None:
        body["seed"] = int(input_.seed)
    if input_.watermark is not None:
        body["watermark"] = bool(input_.watermark)
    if supports_last_frame(input_.model):
        # 尾帧图（无水印、与视频同尺寸）用于「承接上一镜」：它是方舟受信产物，下一镜可直接作参考图而不被人脸审核拦下
        body["return_last_frame"] = True
    return body
