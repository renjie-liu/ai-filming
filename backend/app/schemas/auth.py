"""注册 / 登录 / 会话相关的请求响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RegistrationMode = Literal["first_admin", "open", "invite", "closed"]


class UserRead(BaseModel):
    """对外的用户信息（不含密码哈希）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str = ""
    is_admin: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class AuthStatusRead(BaseModel):
    """登录页需要的公开状态：有没有用户、现在能否注册、注册要不要邀请码。"""

    has_users: bool = Field(..., description="是否已有任何用户；没有时第一个注册者成为管理员")
    registration: RegistrationMode = Field(..., description="first_admin=等待首个管理员注册；open=开放注册；invite=需邀请码；closed=关闭注册")


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="邮箱")
    password: str = Field(..., min_length=8, max_length=128, description="密码（至少 8 位）")
    display_name: str = Field("", max_length=80, description="显示名，可空")
    invite_code: str | None = Field(None, max_length=64, description="邀请码；注册模式为 invite 时必填")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128, description="当前密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码（至少 8 位）")


class RegistrationSettingsRead(BaseModel):
    """管理员可见的注册设置。"""

    enabled: bool = Field(..., description="是否允许新用户注册")
    invite_code: str | None = Field(None, description="邀请码；为空表示开放注册（在 enabled 为真时）")
    user_count: int = Field(0, description="当前用户数")


class RegistrationSettingsUpdate(BaseModel):
    enabled: bool | None = Field(None, description="允许 / 关闭注册")
    invite_code: str | None = Field(None, max_length=64, description="设置邀请码；传空串表示清除（开放注册）")
    regenerate_invite_code: bool = Field(False, description="为真时随机生成一个新邀请码（忽略 invite_code）")
