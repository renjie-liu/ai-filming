"""注册 / 登录 / 会话接口。

api 层只做三件事：收参、把业务错误转成状态码、在响应上设置或清除会话 cookie；规则全部在 `services.auth`。
cookie 为 HttpOnly + SameSite=Lax，https 下带 Secure；同源 SPA 直接复用，无需前端保存令牌。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_admin, require_user
from app.models.users import User
from app.schemas.auth import (
    AuthStatusRead,
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    RegistrationSettingsRead,
    RegistrationSettingsUpdate,
    UserRead,
)
from app.schemas.common import (
    ApiResponse,
    created_response,
    empty_response,
    success_response,
)
from app.services import auth as auth_service

router = APIRouter()


def _is_https(request: Request) -> bool:
    """Vercel 等反向代理后面 `request.url.scheme` 可能是 http，以 X-Forwarded-Proto 为准。"""
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_days * 86400,
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        path="/",
    )


def _raise(exc: auth_service.AuthError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/status", response_model=ApiResponse[AuthStatusRead], summary="登录页公开状态：是否有用户、能否注册")
async def auth_status(db: AsyncSession = Depends(get_db)) -> ApiResponse[AuthStatusRead]:
    mode = await auth_service.registration_mode(db)
    return success_response(AuthStatusRead(has_users=mode != "first_admin", registration=mode))


@router.post("/register", response_model=ApiResponse[UserRead], status_code=201, summary="注册并登录")
async def register(body: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> ApiResponse[UserRead]:
    try:
        user = await auth_service.register_user(
            db, email=body.email, password=body.password, display_name=body.display_name, invite_code=body.invite_code
        )
    except auth_service.AuthError as exc:
        _raise(exc)
    _set_session_cookie(response, request, await auth_service.issue_session_token(db, user))
    return created_response(UserRead.model_validate(user))


@router.post("/login", response_model=ApiResponse[UserRead], summary="邮箱密码登录")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> ApiResponse[UserRead]:
    try:
        user = await auth_service.authenticate(db, email=body.email, password=body.password)
    except auth_service.AuthError as exc:
        _raise(exc)
    _set_session_cookie(response, request, await auth_service.issue_session_token(db, user))
    return success_response(UserRead.model_validate(user))


@router.post("/logout", response_model=ApiResponse[None], summary="退出登录（清除会话 cookie）")
async def logout(response: Response) -> ApiResponse[None]:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return empty_response()


@router.get("/me", response_model=ApiResponse[UserRead], summary="当前登录用户")
async def me(user: User = Depends(require_user)) -> ApiResponse[UserRead]:
    return success_response(UserRead.model_validate(user))


@router.post("/password", response_model=ApiResponse[None], summary="修改当前用户的密码")
async def change_password(body: PasswordChangeRequest, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)) -> ApiResponse[None]:
    try:
        await auth_service.change_password(db, user=user, current_password=body.current_password, new_password=body.new_password)
    except auth_service.AuthError as exc:
        _raise(exc)
    return empty_response()


@router.get("/settings", response_model=ApiResponse[RegistrationSettingsRead], summary="注册设置（管理员）")
async def get_registration_settings(
    _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> ApiResponse[RegistrationSettingsRead]:
    return success_response(await auth_service.get_registration_settings(db))


@router.put("/settings", response_model=ApiResponse[RegistrationSettingsRead], summary="修改注册设置（管理员）")
async def update_registration_settings(
    body: RegistrationSettingsUpdate, _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> ApiResponse[RegistrationSettingsRead]:
    return success_response(await auth_service.update_registration_settings(db, body))


@router.get("/users", response_model=ApiResponse[list[UserRead]], summary="用户列表（管理员）")
async def list_users(_admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> ApiResponse[list[UserRead]]:
    return success_response([UserRead.model_validate(u) for u in await auth_service.list_users(db)])
