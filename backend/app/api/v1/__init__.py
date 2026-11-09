"""API v1 路由聚合。

鉴权边界在这里：健康检查、部署状态与 /auth 公开；其余业务路由都要求登录（`require_user`），
模型管理（/llm）只允许管理员。各路由内部再按作品归属做细粒度检查（见 services.auth.ensure_*_access）。
"""

from fastapi import APIRouter, Depends

from app.api.v1.routes import auth, deploy_status, film, health, llm, script_processing, studio, system
from app.dependencies import require_admin, require_user

router = APIRouter()

_LOGIN_REQUIRED = [Depends(require_user)]
_ADMIN_REQUIRED = [Depends(require_admin)]

router.include_router(health.router, tags=["health"])
router.include_router(deploy_status.router, tags=["deploy"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(system.router, prefix="/system", tags=["system"], dependencies=_LOGIN_REQUIRED)
router.include_router(film.router, prefix="/film", tags=["film"], dependencies=_LOGIN_REQUIRED)
router.include_router(llm.router, prefix="/llm", tags=["llm"], dependencies=_ADMIN_REQUIRED)
router.include_router(studio.router, prefix="/studio", dependencies=_LOGIN_REQUIRED)
router.include_router(script_processing.router, dependencies=_LOGIN_REQUIRED)
