"""用户账号。

为什么存在：创作页与作品需要归属到人；邮箱 + 密码是最低限度的账号形态。
`is_admin` 由第一个注册的用户获得，用于管理注册设置与模型配置。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    """用户表：邮箱唯一（统一小写存储），密码只存 scrypt 哈希。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户 ID（uuid hex）")
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True, comment="登录邮箱（小写）")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="scrypt 密码哈希（自描述格式）")
    display_name: Mapped[str] = mapped_column(String(80), nullable=False, default="", comment="显示名")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否管理员（首个注册用户）")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否可登录")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="最近登录时间")
