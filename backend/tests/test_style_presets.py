"""画面风格预设目录：目录完整性、提示词解析优先级、接口契约与老库补列。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect

from app.api.v1.routes.studio.projects import _build_project_style_options
from app.deploy_bootstrap import add_missing_columns
from app.dependencies import get_db
from app.main import app
from app.models.studio import Project
from app.services.studio.style_presets import (
    STYLE_GROUPS,
    STYLE_PRESETS,
    default_style_preset_key,
    get_style_preset,
    resolve_style_text,
    style_label,
)


def test_catalogue_is_rich_unique_and_maps_to_valid_buckets() -> None:
    """至少 16 种风格、key 唯一、每个分组都有卡片，且每张卡片的粗分桶组合都能通过创建校验。"""
    assert len(STYLE_PRESETS) >= 16
    keys = [item.key for item in STYLE_PRESETS]
    assert len(keys) == len(set(keys))
    groups = {item.group for item in STYLE_PRESETS}
    assert groups == set(STYLE_GROUPS)
    mapping, _defaults = _build_project_style_options()
    for item in STYLE_PRESETS:
        assert item.style in mapping[item.visual_style], item.key
        assert item.prompt and item.label and item.blurb, item.key
    assert get_style_preset(default_style_preset_key()) is not None
    assert get_style_preset("nope") is None
    assert get_style_preset(None) is None


def test_resolve_style_text_prefers_preset_then_custom_then_legacy_bucket() -> None:
    """预设 + 补充 → 「预设提示词；补充」；仅补充 → 补充；都没有 → 旧题材枚举值（老作品行为不变）。"""
    preset = get_style_preset("cinematic_film")
    assert preset is not None
    both = SimpleNamespace(style_preset="cinematic_film", style_prompt=" 偏青橙调 ", style="真人都市")
    assert resolve_style_text(both) == f"{preset.prompt}；偏青橙调"
    assert style_label(both) == "电影胶片"
    only_custom = SimpleNamespace(style_preset=None, style_prompt="黑白默片", style="真人都市")
    assert resolve_style_text(only_custom) == "黑白默片"
    legacy = SimpleNamespace(style_preset=None, style_prompt=None, style="真人都市")
    assert resolve_style_text(legacy) == "真人都市"
    assert style_label(legacy) == "真人都市"
    assert resolve_style_text(None) == ""


class _FakeDB:
    """只记录 add 进来的 Project 的最小 DB 替身。"""

    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}

    async def get(self, model: type, entity_id: str):  # noqa: ANN001
        return self.projects.get(entity_id) if model is Project else None

    def add(self, obj: object) -> None:
        assert isinstance(obj, Project)
        self.projects[obj.id] = obj

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def _override(db: _FakeDB):
    async def _dep() -> AsyncGenerator[_FakeDB, None]:
        yield db

    return _dep


def test_style_options_expose_presets_and_create_applies_preset_bucket() -> None:
    """接口返回预设目录；带 style_preset 创建时 visual_style / style 以预设为准；未知 key 返回 400。"""
    client = TestClient(app)
    options = client.get("/api/v1/studio/projects/style-options").json()["data"]
    assert options["preset_groups"] == list(STYLE_GROUPS)
    assert len(options["presets"]) == len(STYLE_PRESETS)
    assert options["default_preset"] == default_style_preset_key()
    ink = next(item for item in options["presets"] if item["key"] == "ink_wash")
    assert ink["visual_style"] == "动漫" and ink["style"] == "水墨画" and ink["group"] == "艺术"

    db = _FakeDB()
    app.dependency_overrides[get_db] = _override(db)
    try:
        created = client.post(
            "/api/v1/studio/projects",
            json={"id": "p-ink", "name": "墨", "style": "真人都市", "visual_style": "现实", "style_preset": "ink_wash", "style_prompt": "多留白"},
        )
        assert created.status_code == 201, created.text
        data = created.json()["data"]
        assert data["style_preset"] == "ink_wash"
        assert data["visual_style"] == "动漫" and data["style"] == "水墨画"
        assert data["style_prompt"] == "多留白"

        bad = client.post(
            "/api/v1/studio/projects",
            json={"id": "p-bad", "name": "x", "style": "真人都市", "visual_style": "现实", "style_preset": "does_not_exist"},
        )
        assert bad.status_code == 400
        assert "unknown style_preset" in bad.json()["message"]
    finally:
        app.dependency_overrides.clear()


def test_add_missing_columns_adds_new_nullable_columns_to_existing_table() -> None:
    """老库里的 projects 表缺少新列时，启动补列把 style_preset / style_prompt 加上，非空列不动。"""
    engine = create_engine("sqlite://")
    legacy = MetaData()
    Table("projects", legacy, Column("id", String(64), primary_key=True), Column("name", String(255), nullable=False))
    legacy.create_all(engine)
    with engine.begin() as conn:
        added = add_missing_columns(conn)
    assert "projects.style_preset" in added
    assert "projects.style_prompt" in added
    columns = {col["name"] for col in inspect(engine).get_columns("projects")}
    assert {"style_preset", "style_prompt", "default_video_ratio"} <= columns
    # 非空且无默认值的列（如 description）不能用 ADD COLUMN 安全补齐，应被跳过而不是报错
    assert "description" not in columns
    with engine.begin() as conn:
        assert add_missing_columns(conn) == []
