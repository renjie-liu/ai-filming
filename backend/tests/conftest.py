"""Pytest 共享 fixture：FastAPI 应用与 TestClient。"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from fastapi.testclient import TestClient

try:
    from app.main import app  # type: ignore
except Exception:  # noqa: BLE001
    # 测试环境里有些可选依赖（例如 langgraph）可能未安装。
    # 不要让整个测试套件在导入 conftest 时直接失败；仅在需要 client 的测试里跳过。
    app = None


@pytest.fixture(autouse=True)
def _signed_in_admin():
    """业务接口现在都要求登录：默认把每个测试当作已登录的管理员，登录相关的测试自行移除这个覆盖。"""
    if app is None:
        yield
        return
    from app.dependencies import get_current_user_optional
    from app.models.users import User

    admin = User(id="test-admin", email="admin@test.local", password_hash="x", display_name="测试管理员", is_admin=True, is_active=True)

    async def _override():
        return admin

    app.dependency_overrides[get_current_user_optional] = _override
    try:
        yield admin
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.fixture
def client() -> TestClient:
    """FastAPI 应用 TestClient，用于集成测试。"""
    if app is None:
        pytest.skip("FastAPI app 依赖未满足（例如缺少 langgraph），跳过需要 client 的集成测试。")
    return TestClient(app)


def pytest_configure(config: pytest.Config) -> None:
    """为轻量测试环境补齐 asyncio marker。"""
    config.addinivalue_line("markers", "asyncio: mark test as asyncio coroutine")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """在未安装 pytest-asyncio 的环境中兜底执行 async 测试。"""

    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None

    funcargs = {
        arg: pyfuncitem.funcargs[arg]
        for arg in pyfuncitem._fixtureinfo.argnames
        if arg in pyfuncitem.funcargs
    }
    asyncio.run(pyfuncitem.obj(**funcargs))
    return True
