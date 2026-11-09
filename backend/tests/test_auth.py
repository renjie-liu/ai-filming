"""账号系统：密码 / 令牌原语、注册登录流程、邀请码与注册开关、作品归属与可见范围。

接口测试跑在真实的 SQLite 库上（而不是其它接口测试用的内存替身），因为注册 / 登录 / 归属都依赖真实查询。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.core.db import Base
from app.core.security import (
    hash_password,
    new_invite_code,
    read_token,
    sign_token,
    verify_password,
)
from app.dependencies import get_current_user_optional, get_db
from app.deploy_bootstrap import bootstrap_meta_table
from app.main import app
from app.models.studio import Project, ProjectStyle, ProjectVisualStyle
from app.models.users import User  # noqa: F401  # 注册到 Base.metadata

# ---------------------------------------------------------------------------
# 原语
# ---------------------------------------------------------------------------


def test_password_hash_roundtrip_and_rejects_garbage() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("x", "not-a-hash")
    assert hash_password("same") != hash_password("same")  # 随机盐


def test_token_roundtrip_tamper_and_expiry() -> None:
    now = time.time()
    token = sign_token({"sub": "u1", "exp": int(now + 60)}, "secret")
    assert read_token(token, "secret", now=now)["sub"] == "u1"
    assert read_token(token, "other-secret", now=now) is None
    body, _, sig = token.rpartition(".")
    assert read_token(body + "x." + sig, "secret", now=now) is None
    assert read_token(token, "secret", now=now + 61) is None
    assert read_token("", "secret") is None
    assert len(new_invite_code()) == 8


# ---------------------------------------------------------------------------
# 接口：真实 SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """带真实 SQLite 的应用：移除 conftest 的「默认已登录管理员」覆盖，固定签名密钥，返回建 client 的工厂。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(bootstrap_meta_table.create, checkfirst=True)
        await engine.dispose()

    asyncio.run(_create())

    async def _get_db() -> AsyncGenerator:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(settings, "auth_secret", "test-signing-secret")
    app.dependency_overrides.pop(get_current_user_optional, None)
    app.dependency_overrides[get_db] = _get_db
    try:
        yield {"client": lambda: TestClient(app), "maker": maker}
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _project_payload(pid: str, name: str) -> dict:
    return {"id": pid, "name": name, "style": ProjectStyle.real_people_city.value, "visual_style": ProjectVisualStyle.live_action.value}


def test_first_registration_creates_admin_and_switches_to_invite_mode(auth_app) -> None:
    client: TestClient = auth_app["client"]()
    assert client.get("/api/v1/auth/status").json()["data"] == {"has_users": False, "registration": "first_admin"}
    assert client.get("/api/v1/studio/projects/overview").status_code == 401

    created = client.post("/api/v1/auth/register", json={"email": " Admin@Example.com ", "password": "password123", "display_name": "老板"})
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["email"] == "admin@example.com" and data["is_admin"] is True
    assert settings.auth_cookie_name in created.cookies

    me = client.get("/api/v1/auth/me").json()["data"]
    assert me["email"] == "admin@example.com"
    assert client.get("/api/v1/auth/status").json()["data"]["registration"] == "invite"
    settings_read = client.get("/api/v1/auth/settings").json()["data"]
    assert settings_read["enabled"] is True and settings_read["user_count"] == 1
    assert settings_read["invite_code"] and len(settings_read["invite_code"]) == 8


def test_second_user_needs_invite_code_and_sees_only_own_projects(auth_app) -> None:
    admin: TestClient = auth_app["client"]()
    admin.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "password123"})
    code = admin.get("/api/v1/auth/settings").json()["data"]["invite_code"]

    guest: TestClient = auth_app["client"]()
    assert guest.post("/api/v1/auth/register", json={"email": "u2@example.com", "password": "password123"}).status_code == 403
    assert guest.post("/api/v1/auth/register", json={"email": "u2@example.com", "password": "password123", "invite_code": "WRONG"}).status_code == 403
    ok = guest.post("/api/v1/auth/register", json={"email": "u2@example.com", "password": "password123", "invite_code": code.lower()})
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["is_admin"] is False
    assert guest.get("/api/v1/auth/settings").status_code == 403  # 非管理员

    assert admin.post("/api/v1/studio/projects", json=_project_payload("p-admin", "老板的片")).status_code == 201
    assert guest.post("/api/v1/studio/projects", json=_project_payload("p-guest", "访客的片")).status_code == 201

    guest_overview = guest.get("/api/v1/studio/projects/overview").json()["data"]
    assert [p["id"] for p in guest_overview] == ["p-guest"]
    assert guest.get("/api/v1/studio/projects/p-admin").status_code == 403
    assert guest.patch("/api/v1/studio/projects/p-admin", json={"name": "改名"}).status_code == 403
    assert guest.delete("/api/v1/studio/projects/p-admin").status_code == 403
    assert guest.get("/api/v1/studio/chapters", params={"project_id": "p-admin"}).status_code == 403
    assert guest.post("/api/v1/studio/chapters", json={"id": "c1", "project_id": "p-admin", "index": 1, "title": "第 1 集"}).status_code == 403

    admin_overview = admin.get("/api/v1/studio/projects/overview").json()["data"]
    assert {p["id"] for p in admin_overview} == {"p-admin", "p-guest"}  # 管理员看全部
    assert admin.get("/api/v1/studio/projects/p-guest").status_code == 200


def test_login_logout_and_protected_routes(auth_app) -> None:
    client: TestClient = auth_app["client"]()
    client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "password123"})
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "password123"}).status_code == 401
    logged = client.post("/api/v1/auth/login", json={"email": "ADMIN@example.com", "password": "password123"})
    assert logged.status_code == 200, logged.text
    assert client.get("/api/v1/auth/me").json()["data"]["email"] == "admin@example.com"
    assert client.get("/api/v1/studio/projects/overview").status_code == 200
    # Bearer 头也能用（脚本调用）
    token = logged.cookies.get(settings.auth_cookie_name)
    bare: TestClient = auth_app["client"]()
    assert bare.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert bare.get("/api/v1/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    # 模型管理只给管理员；普通路由登录即可
    assert client.get("/api/v1/llm/providers").status_code != 401


def test_first_admin_adopts_legacy_projects_and_registration_can_be_closed(auth_app) -> None:
    maker = auth_app["maker"]

    async def _seed() -> None:
        async with maker() as session:
            session.add(Project(id="legacy", name="老作品", description="", style=ProjectStyle.real_people_city, visual_style=ProjectVisualStyle.live_action))
            await session.commit()

    asyncio.run(_seed())
    admin: TestClient = auth_app["client"]()
    admin.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "password123"})
    overview = admin.get("/api/v1/studio/projects/overview").json()["data"]
    assert [p["id"] for p in overview] == ["legacy"]

    async def _owner() -> str | None:
        async with maker() as session:
            return (await session.get(Project, "legacy")).owner_id

    admin_id = admin.get("/api/v1/auth/me").json()["data"]["id"]
    assert asyncio.run(_owner()) == admin_id

    closed = admin.put("/api/v1/auth/settings", json={"enabled": False})
    assert closed.json()["data"]["enabled"] is False
    assert admin.get("/api/v1/auth/status").json()["data"]["registration"] == "closed"
    guest: TestClient = auth_app["client"]()
    assert guest.post("/api/v1/auth/register", json={"email": "u2@example.com", "password": "password123"}).status_code == 403

    opened = admin.put("/api/v1/auth/settings", json={"enabled": True, "invite_code": ""})
    assert opened.json()["data"]["invite_code"] is None
    assert admin.get("/api/v1/auth/status").json()["data"]["registration"] == "open"
    assert guest.post("/api/v1/auth/register", json={"email": "u2@example.com", "password": "password123"}).status_code == 201
    assert guest.post("/api/v1/auth/register", json={"email": "u2@example.com", "password": "password123"}).status_code == 409
    regenerated = admin.put("/api/v1/auth/settings", json={"regenerate_invite_code": True}).json()["data"]
    assert regenerated["invite_code"] and regenerated["user_count"] == 2
    users = admin.get("/api/v1/auth/users").json()["data"]
    assert [u["email"] for u in users] == ["admin@example.com", "u2@example.com"]


def test_change_password_requires_current_and_takes_effect_on_next_login(auth_app) -> None:
    client: TestClient = auth_app["client"]()
    client.post("/api/v1/auth/register", json={"email": "admin@example.com", "password": "password123"})
    assert client.post("/api/v1/auth/password", json={"current_password": "nope", "new_password": "newpassword456"}).status_code == 403
    assert client.post("/api/v1/auth/password", json={"current_password": "password123", "new_password": "password123"}).status_code == 400
    assert client.post("/api/v1/auth/password", json={"current_password": "password123", "new_password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/password", json={"current_password": "password123", "new_password": "newpassword456"}).status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "password123"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "newpassword456"}).status_code == 200
