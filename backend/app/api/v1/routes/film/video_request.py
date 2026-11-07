from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from app.core.contracts.video_generation import VideoRatio

class VideoGenerationTaskRequest(BaseModel):
    """视频生成任务请求。"""

    shot_id: str = Field(..., description="镜头 ID")
    reference_mode: Literal["first", "last", "key", "first_last", "first_last_key", "reference", "text_only"] = Field(
        ...,
        description=(
            "参考模式：first | last | key | first_last | first_last_key | reference（全能参考：角色 / 场景形象图 + 可选关键帧，"
            "1–9 张，提示词按 [Image n] 点名）| text_only"
        ),
    )
    # 文本模式必填；非文本模式可选作为补充描述
    prompt: str | None = Field(None, description="视频提示词（text_only 必填）")
    images: list[str] = Field(
        default_factory=list,
        description="参考图 file_id 列表；帧模式数量需与 reference_mode 严格匹配，reference 模式 1–9 张（为空时按镜头关联实体自动收集）",
    )
    reference_labels: list[str] | None = Field(
        None,
        description="reference 模式下与 images 一一对应的素材说明（如「角色「雷霆总监」：40岁…」），写进提示词的 [Image n] 行；为空时自动生成",
    )

    ratio: VideoRatio = Field(..., description="视频画幅比例，如 16:9 / 9:16")
    # seconds 由 ShotDetail.duration 自动确定；请求体不再接收覆盖值。
