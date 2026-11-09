"""SQLAlchemy 异步引擎与会话。"""

import threading
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def engine_options(url: str) -> dict[str, Any]:
    """按方言返回引擎参数（同步 / 异步引擎共用）。

    Postgres（Neon 等托管库，通常经 PgBouncer 连接池）：
    - `prepare_threshold=None` 关闭 psycopg 服务端预编译语句，兼容 PgBouncer transaction 模式；
    - `pool_pre_ping` + `pool_recycle` 处理 serverless 冻结 / 托管库空闲断连。
    """
    if url.startswith("postgresql+psycopg://"):
        return {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 5,
            "max_overflow": 5,
            "connect_args": {"prepare_threshold": None},
        }
    return {}


def _build_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,
        future=True,
        **engine_options(settings.database_url),
    )


def _build_session_maker(bind_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# 线程级 async DB runtime（engine + sessionmaker）覆盖。
# 进程内后台线程执行任务（Vercel inline 模式）时使用，避免替换 / 释放 API 主事件循环正在使用的全局 engine。
_thread_runtime = threading.local()


class _AsyncSessionMakerProxy:
    """可重绑定的 sessionmaker 代理。

    Celery prefork 模式下，worker 子进程不能继续复用父进程里初始化的
    async engine / sessionmaker。这里保持导入对象稳定，同时允许在子进程
    启动后重新绑定底层 sessionmaker。

    若当前线程通过 `reset_db_runtime()` 建立了线程级 runtime，则优先使用线程级 sessionmaker。
    """

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker

    def configure(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        maker = getattr(_thread_runtime, "maker", None) or self._maker
        return maker(*args, **kwargs)


engine = _build_engine()
async_session_maker = _AsyncSessionMakerProxy(_build_session_maker(engine))


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


async def init_db() -> None:
    """创建所有表（开发/迁移用）。"""
    # 确保 ORM 模型已导入，从而注册到 Base.metadata
    import app.models.llm  # noqa: F401  # pylint: disable=unused-import
    import app.models.studio  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401
    import app.models.users  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """关闭数据库连接。"""
    local_engine = getattr(_thread_runtime, "engine", None)
    if local_engine is not None:
        # 仅释放当前线程自己的 runtime，不影响主线程（API 事件循环）的全局 engine。
        _thread_runtime.engine = None
        _thread_runtime.maker = None
        await local_engine.dispose()
        return
    await engine.dispose()


def reset_db_runtime() -> None:
    """为即将在新事件循环中执行的任务重建 async engine 与 sessionmaker。

    - 主线程（Celery prefork 子进程）：替换全局 engine，避免继承父进程中的 engine，
      导致连接对象和事件循环绑定错乱，触发 Future attached to a different loop；
    - 非主线程（API 进程内后台线程执行任务）：只建立线程级 runtime，
      主事件循环继续使用原全局 engine，互不干扰。
    """

    global engine

    if threading.current_thread() is not threading.main_thread():
        local_engine = _build_engine()
        _thread_runtime.engine = local_engine
        _thread_runtime.maker = _build_session_maker(local_engine)
        return

    engine = _build_engine()
    async_session_maker.configure(_build_session_maker(engine))
