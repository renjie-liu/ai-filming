"""开箱即用状态：汇总默认模型与部署托管的供应商，供前端引导使用。

为什么存在：部署时已通过环境变量提供方舟 API Key 并自动配置了默认模型，
前端需要据此告诉用户「无需在模型管理中填写 API Key」，并在缺少模型时给出明确提示。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import Model, ModelSettings, Provider
from app.schemas.system import SetupModelRead, SetupProviderRead, SetupStatusRead


async def _resolve_default(db: AsyncSession, model_id: str | None) -> tuple[SetupModelRead | None, Provider | None]:
    """读取默认模型及其供应商；任一缺失返回 (None, None)。"""
    if not model_id:
        return None, None
    model = await db.get(Model, model_id)
    if model is None:
        return None, None
    provider = await db.get(Provider, model.provider_id)
    return SetupModelRead(id=model.id, name=model.name, provider_id=model.provider_id), provider


async def get_setup_status(db: AsyncSession) -> SetupStatusRead:
    """计算开箱即用状态；不返回任何密钥。"""
    from app.deploy_bootstrap import ARK_PROVIDER_ID
    from app.services.ark_autoconfig import ARK_REGION_LABELS, configured_api_key, region_from_base_url

    settings_row = await db.get(ModelSettings, 1)
    defaults: dict[str, SetupModelRead | None] = {}
    missing: list[str] = []
    for category, field in (
        ("text", "default_text_model_id"),
        ("image", "default_image_model_id"),
        ("video", "default_video_model_id"),
    ):
        model_read, provider = await _resolve_default(db, getattr(settings_row, field, None) if settings_row else None)
        has_key = provider is not None and bool((provider.api_key or "").strip())
        defaults[category] = model_read if has_key else None
        if not has_key:
            missing.append(category)

    managed: SetupProviderRead | None = None
    provider = await db.get(Provider, ARK_PROVIDER_ID)
    if provider is not None:
        region = region_from_base_url(provider.base_url)
        managed = SetupProviderRead(
            id=provider.id,
            label=f"Seedance · {ARK_REGION_LABELS.get(region, 'Ark')}",
            region=region,
            managed_by_deployment=configured_api_key() is not None,
        )

    return SetupStatusRead(
        ready=not missing,
        managed_provider=managed,
        text_model=defaults["text"],
        image_model=defaults["image"],
        video_model=defaults["video"],
        missing=missing,
    )
