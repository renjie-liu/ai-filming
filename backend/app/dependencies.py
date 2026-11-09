"""FastAPI 依赖注入。"""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.db import async_session_maker
from app.models.users import User
from app.services.llm.resolver import build_default_text_llm


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供异步数据库会话。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    """从会话 cookie（或 `Authorization: Bearer`，便于脚本调用）解析当前用户；没有或无效返回 None。"""
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        header = request.headers.get("authorization") or ""
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    if not token:
        return None
    from app.services.auth import resolve_user_from_token

    return await resolve_user_from_token(db, token)


async def require_user(user: User | None = Depends(get_current_user_optional)) -> User:
    """需要登录的接口依赖；未登录返回 401，前端据此跳转登录页。"""
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    """管理员专用（注册设置、模型配置）。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def get_llm(db: AsyncSession = Depends(get_db)) -> BaseChatModel:
    """提供默认文本 LLM（ChatOpenAI）。"""
    return await build_default_text_llm(db, thinking=True)

async def get_nothinking_llm(db: AsyncSession = Depends(get_db)) -> BaseChatModel:
    """提供默认文本 LLM（ChatOpenAI，禁用 thinking）。"""
    return await build_default_text_llm(db, thinking=False)


class _ImageHttpRunnable:
    """最小图片生成 runnable：从环境变量读取配置，通过 HTTP 调用外部图片生成服务。"""

    def __init__(self, *, base_url: str, api_key: str, timeout_s: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def invoke(self, payload: dict) -> dict:  # noqa: ANN001
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise HTTPException(status_code=503, detail="Install httpx to enable image generation") from e
        with httpx.Client(timeout=self._timeout_s) as client:
            r = client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"images": data}

    async def ainvoke(self, payload: dict) -> dict:  # noqa: ANN001
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise HTTPException(status_code=503, detail="Install httpx to enable image generation") from e
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            r = await client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"images": data}
