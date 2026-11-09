"""账号与会话：注册、登录、会话令牌、注册设置、作品归属。

为什么存在：api 层只负责收参与发 / 清 cookie，这里集中所有规则：
- 第一个注册的用户成为管理员，接管此前没有归属的作品（升级到有账号之前创建的数据），并自动生成邀请码，
  之后的注册默认需要邀请码；管理员可以改为开放注册或关闭注册。
- 密码用 scrypt 哈希；会话令牌用 HMAC 签名、默认 30 天；签名密钥优先取环境变量 `AUTH_SECRET`，
  否则在启动时生成一把存进启动元数据表（`jellyfish_bootstrap_meta`），零配置即可用。
- 作品归属：`Project.owner_id`；访问检查「所有者或管理员」，没有归属的老作品任何登录用户都可见。
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import (
    hash_password,
    new_invite_code,
    new_secret,
    read_token,
    sign_token,
    verify_password,
)
from app.deploy_bootstrap import bootstrap_meta_table
from app.models.studio import Chapter, Project, Shot
from app.models.users import User
from app.schemas.auth import (
    RegistrationMode,
    RegistrationSettingsRead,
    RegistrationSettingsUpdate,
)
from app.services.common import entity_not_found

logger = logging.getLogger(__name__)

META_SECRET = "auth_secret"
META_REGISTRATION_ENABLED = "auth_registration_enabled"
META_INVITE_CODE = "auth_invite_code"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_secret_cache: str | None = None
_meta_table_ready = False


class AuthError(Exception):
    """业务层的认证 / 注册错误；api 层转成对应状态码。"""

    def __init__(self, message: str, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# 启动元数据表里的键值（签名密钥、注册设置）
# ---------------------------------------------------------------------------


async def _ensure_meta_table(db: AsyncSession) -> None:
    """本地开发可能只跑过 `init_db` 而没有部署引导；按需把元数据表建出来（每个进程只检查一次）。"""
    global _meta_table_ready
    if _meta_table_ready:
        return
    await db.run_sync(lambda sync: bootstrap_meta_table.create(sync.connection(), checkfirst=True))
    _meta_table_ready = True


async def read_meta(db: AsyncSession, key: str) -> str | None:
    await _ensure_meta_table(db)
    return (await db.execute(select(bootstrap_meta_table.c.value).where(bootstrap_meta_table.c.key == key))).scalar_one_or_none()


async def write_meta(db: AsyncSession, key: str, value: str) -> None:
    await _ensure_meta_table(db)
    await db.execute(delete(bootstrap_meta_table).where(bootstrap_meta_table.c.key == key))
    await db.execute(insert(bootstrap_meta_table).values(key=key, value=value))
    await db.flush()


async def get_auth_secret(db: AsyncSession) -> str:
    """会话签名密钥：环境变量 > 元数据表；都没有就生成一把写进表里（部署引导也会提前做这件事）。"""
    global _secret_cache
    if settings.auth_secret:
        return settings.auth_secret
    if _secret_cache:
        return _secret_cache
    value = await read_meta(db, META_SECRET)
    if not value:
        value = new_secret()
        await write_meta(db, META_SECRET, value)
        logger.info("auth: generated a new session signing secret")
    _secret_cache = value
    return value


# ---------------------------------------------------------------------------
# 注册 / 登录
# ---------------------------------------------------------------------------


def normalize_email(raw: str) -> str:
    """去空格、转小写；格式不对抛 AuthError。"""
    email = (raw or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 255:
        raise AuthError("邮箱格式不正确")
    return email


async def count_users(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(User))).scalar_one() or 0)


async def registration_mode(db: AsyncSession) -> RegistrationMode:
    """当前注册模式：没有用户 → 等首个管理员；关闭 → closed；有邀请码 → invite；否则 open。"""
    if await count_users(db) == 0:
        return "first_admin"
    if (await read_meta(db, META_REGISTRATION_ENABLED) or "1") == "0":
        return "closed"
    return "invite" if (await read_meta(db, META_INVITE_CODE) or "").strip() else "open"


async def adopt_ownerless_projects(db: AsyncSession, *, owner_id: str) -> int:
    """把没有归属的作品（有账号系统之前创建的）划给某个用户，返回数量。"""
    result = await db.execute(update(Project).where(Project.owner_id.is_(None)).values(owner_id=owner_id))
    return int(result.rowcount or 0)


async def register_user(db: AsyncSession, *, email: str, password: str, display_name: str = "", invite_code: str | None = None) -> User:
    """注册：校验邮箱 / 密码 / 注册模式与邀请码，首个用户成为管理员并接管老作品、生成邀请码。"""
    normalized = normalize_email(email)
    if len(password or "") < 8:
        raise AuthError("密码至少 8 位")
    mode = await registration_mode(db)
    if mode == "closed":
        raise AuthError("当前未开放注册，请联系管理员获取账号", status_code=status.HTTP_403_FORBIDDEN)
    if mode == "invite":
        expected = (await read_meta(db, META_INVITE_CODE) or "").strip().upper()
        if not invite_code or invite_code.strip().upper() != expected:
            raise AuthError("邀请码不正确", status_code=status.HTTP_403_FORBIDDEN)
    if await db.scalar(select(User.id).where(User.email == normalized)):
        raise AuthError("该邮箱已注册，请直接登录", status_code=status.HTTP_409_CONFLICT)
    user = User(
        id=uuid.uuid4().hex,
        email=normalized,
        password_hash=hash_password(password),
        display_name=(display_name or "").strip()[:80],
        is_admin=mode == "first_admin",
        is_active=True,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.flush()
    if mode == "first_admin":
        adopted = await adopt_ownerless_projects(db, owner_id=user.id)
        await write_meta(db, META_INVITE_CODE, new_invite_code())
        await write_meta(db, META_REGISTRATION_ENABLED, "1")
        logger.info("auth: first user registered as admin, adopted %d legacy projects", adopted)
    return user


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    """邮箱 + 密码登录；任何失败都返回同一句话，不区分「邮箱不存在」与「密码错」。"""
    try:
        normalized = normalize_email(email)
    except AuthError:
        raise AuthError("邮箱或密码不正确", status_code=status.HTTP_401_UNAUTHORIZED) from None
    user = await db.scalar(select(User).where(User.email == normalized))
    if user is None or not user.is_active or not verify_password(password or "", user.password_hash):
        raise AuthError("邮箱或密码不正确", status_code=status.HTTP_401_UNAUTHORIZED)
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user


async def issue_session_token(db: AsyncSession, user: User) -> str:
    """签发会话令牌（放进 HttpOnly cookie）。"""
    now = int(time.time())
    return sign_token({"sub": user.id, "iat": now, "exp": now + settings.auth_session_days * 86400}, await get_auth_secret(db))


async def resolve_user_from_token(db: AsyncSession, token: str) -> User | None:
    """从令牌取用户；令牌无效 / 过期 / 用户被停用都返回 None。"""
    payload = read_token(token, await get_auth_secret(db))
    if not payload or not isinstance(payload.get("sub"), str):
        return None
    user = await db.get(User, payload["sub"])
    return user if user is not None and user.is_active else None


# ---------------------------------------------------------------------------
# 管理员：注册设置与用户列表
# ---------------------------------------------------------------------------


async def list_users(db: AsyncSession) -> list[User]:
    return list((await db.execute(select(User).order_by(User.created_at.asc(), User.email.asc()))).scalars().all())


async def get_registration_settings(db: AsyncSession) -> RegistrationSettingsRead:
    enabled = (await read_meta(db, META_REGISTRATION_ENABLED) or "1") != "0"
    code = (await read_meta(db, META_INVITE_CODE) or "").strip() or None
    return RegistrationSettingsRead(enabled=enabled, invite_code=code, user_count=await count_users(db))


async def update_registration_settings(db: AsyncSession, body: RegistrationSettingsUpdate) -> RegistrationSettingsRead:
    """改注册开关 / 邀请码；`regenerate_invite_code` 优先于 `invite_code`；邀请码传空串即清除（开放注册）。"""
    if body.enabled is not None:
        await write_meta(db, META_REGISTRATION_ENABLED, "1" if body.enabled else "0")
    if body.regenerate_invite_code:
        await write_meta(db, META_INVITE_CODE, new_invite_code())
    elif body.invite_code is not None:
        await write_meta(db, META_INVITE_CODE, body.invite_code.strip().upper())
    return await get_registration_settings(db)


# ---------------------------------------------------------------------------
# 作品归属检查（api 层在收参后调用）
# ---------------------------------------------------------------------------


def can_access_project(user: User, project: Project) -> bool:
    """所有者或管理员可访问；没有归属的老作品任何登录用户都可访问。"""
    return project.owner_id is None or project.owner_id == user.id or bool(user.is_admin)


def visible_projects_clause(user: User):
    """作品列表的可见范围：管理员看全部（返回 None 表示不过滤）；普通用户看自己的 + 没有归属的老作品。"""
    if user.is_admin:
        return None
    return or_(Project.owner_id == user.id, Project.owner_id.is_(None))


async def ensure_project_access(db: AsyncSession, *, user: User, project_id: str) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Project"))
    if not can_access_project(user, project):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该作品")
    return project


async def ensure_chapter_access(db: AsyncSession, *, user: User, chapter_id: str) -> Chapter:
    chapter = await db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Chapter"))
    await ensure_project_access(db, user=user, project_id=chapter.project_id)
    return chapter


async def ensure_shot_access(db: AsyncSession, *, user: User, shot_id: str) -> Shot:
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Shot"))
    await ensure_chapter_access(db, user=user, chapter_id=shot.chapter_id)
    return shot
