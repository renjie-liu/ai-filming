"""系统级只读信息的响应结构（开箱即用的配置状态等）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SetupModelRead(BaseModel):
    """某一类别当前生效的默认模型。"""

    id: str = Field(..., description="模型 ID")
    name: str = Field(..., description="模型名称（供应商侧模型 ID）")
    provider_id: str = Field(..., description="所属供应商 ID")


class SetupProviderRead(BaseModel):
    """由部署环境自动配置的供应商（API Key 来自环境变量，无需在界面填写）。"""

    id: str = Field(..., description="供应商 ID")
    label: str = Field(..., description="展示名称，例如 Seedance · BytePlus ModelArk")
    region: str | None = Field(None, description="区域：byteplus / volcengine")
    managed_by_deployment: bool = Field(..., description="API Key 是否由部署环境变量提供并在启动时同步")


class SetupStatusRead(BaseModel):
    """开箱即用状态：前端据此决定是否提示「无需配置」或引导去模型管理。"""

    ready: bool = Field(..., description="文本 / 图片 / 视频默认模型均已就绪且供应商已有 API Key")
    managed_provider: SetupProviderRead | None = Field(None, description="部署自动配置的供应商（如有）")
    text_model: SetupModelRead | None = Field(None, description="默认文本模型")
    image_model: SetupModelRead | None = Field(None, description="默认图片模型")
    video_model: SetupModelRead | None = Field(None, description="默认视频模型")
    missing: list[str] = Field(default_factory=list, description="缺少可用默认模型的类别：text / image / video")
