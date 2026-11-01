"""系统级只读接口（开箱即用配置状态）。业务逻辑见 app.services.setup_status。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.common import ApiResponse, success_response
from app.schemas.system import SetupStatusRead
from app.services.setup_status import get_setup_status

router = APIRouter()


@router.get("/setup-status", response_model=ApiResponse[SetupStatusRead], summary="开箱即用配置状态")
async def setup_status(db: AsyncSession = Depends(get_db)) -> ApiResponse[SetupStatusRead]:
    """返回默认模型是否就绪、以及由部署自动配置的供应商（不含密钥）。"""
    return success_response(await get_setup_status(db))
