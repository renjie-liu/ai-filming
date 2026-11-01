"""SQLAlchemy 同步引擎与会话。

给 Celery worker 使用，避免在同步 worker 进程里承载 async DB runtime。
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.db import Base, engine_options


def _to_sync_database_url(url: str) -> str:
    if url.startswith("mysql+aiomysql://"):
        return "mysql+pymysql://" + url.removeprefix("mysql+aiomysql://")
    if url.startswith("sqlite+aiosqlite:///"):
        return "sqlite:///" + url.removeprefix("sqlite+aiosqlite:///")
    # postgresql+psycopg:// 同一 URL 既可用于异步也可用于同步引擎，无需转换。
    return url


def _build_sync_engine() -> Engine:
    url = _to_sync_database_url(settings.database_url)
    options = {"pool_pre_ping": True, **engine_options(url)}
    return create_engine(
        url,
        echo=settings.debug,
        future=True,
        **options,
    )


engine_sync = _build_sync_engine()
sync_session_maker = sessionmaker(
    bind=engine_sync,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

__all__ = [
    "Base",
    "engine_sync",
    "sync_session_maker",
]
