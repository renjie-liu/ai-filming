"""无 init 容器环境（如 Vercel）下的启动引导。

为什么存在：
- Docker Compose 部署通过 `backend-init-db` / `mysql-init-sql` 两个一次性容器建表并写入系统提示词；
- Vercel Functions 没有这类一次性步骤，这里在应用启动时幂等地完成同样的工作：
  1. 建表（Base.metadata.create_all），通过表结构指纹跳过重复执行；
  2. 写入 `sql/001-init-prompt-template.sql` 中的系统提示词模板（解析 MySQL INSERT，按 ORM 写入，方言无关）；
  3. 若部署环境提供了方舟 API Key（SEEDDANCE_API_KEY 等，见 config.ark_api_key），
     自动探测区域与已开通模型（见 app.services.ark_autoconfig），创建供应商、文本/图片/视频模型与默认模型。

所有步骤均可重复执行；Postgres 下使用 advisory lock 防止多个冷启动实例并发建表。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.config import BACKEND_ROOT, settings

logger = logging.getLogger(__name__)

_ADVISORY_LOCK_KEY = 0x4A454C4C  # "JELL"
_META_TABLE_NAME = "jellyfish_bootstrap_meta"
_PROMPT_SEED_FILE = BACKEND_ROOT / "sql" / "001-init-prompt-template.sql"

ARK_PROVIDER_ID = "ark-seedance"

def _import_all_models() -> None:
    import app.models.llm  # noqa: F401  # pylint: disable=unused-import
    import app.models.studio  # noqa: F401
    import app.models.task  # noqa: F401
    import app.models.task_links  # noqa: F401


def _schema_fingerprint() -> str:
    """表结构指纹：表名 + 列名 + 列类型；模型变化时自动触发重新 create_all。"""
    from app.core.db import Base

    parts: list[str] = []
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        cols = ",".join(f"{c.name}:{c.type!r}" for c in table.columns)
        parts.append(f"{table.name}({cols})")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


_meta = MetaData()
bootstrap_meta_table = Table(
    _META_TABLE_NAME,
    _meta,
    Column("key", String(64), primary_key=True),
    Column("value", String(255), nullable=False),
)


async def _read_meta(conn: AsyncConnection, key: str) -> str | None:
    row = (await conn.execute(select(bootstrap_meta_table.c.value).where(bootstrap_meta_table.c.key == key))).first()
    return row[0] if row else None


async def _write_meta(conn: AsyncConnection, key: str, value: str) -> None:
    await conn.execute(bootstrap_meta_table.delete().where(bootstrap_meta_table.c.key == key))
    await conn.execute(bootstrap_meta_table.insert().values(key=key, value=value))


async def ensure_schema() -> bool:
    """幂等建表；返回本次是否执行了 create_all。"""
    from app.core.db import Base, engine

    _import_all_models()
    fingerprint = _schema_fingerprint()
    is_pg = engine.dialect.name == "postgresql"

    async with engine.begin() as conn:
        if is_pg:
            # 事务级 advisory lock：并发冷启动时串行化建表，事务结束自动释放。
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        await conn.run_sync(_meta.create_all)
        if await _read_meta(conn, "schema_fingerprint") == fingerprint:
            return False
        await conn.run_sync(Base.metadata.create_all)
        await _write_meta(conn, "schema_fingerprint", fingerprint)
        logger.info("deploy bootstrap: schema created/updated (fingerprint=%s)", fingerprint)
        return True


# ---------------------------------------------------------------------------
# 系统提示词模板：解析 MySQL 方言的 INSERT 语句
# ---------------------------------------------------------------------------

_MYSQL_ESCAPES = {
    "0": "\0",
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "%": "\\%",
    "_": "\\_",
}


def _parse_mysql_values(sql: str, start: int) -> tuple[list[list[Any]], int]:
    """从 `VALUES` 之后解析若干 `(...)` 元组，支持 MySQL 字符串转义。返回 (rows, 结束位置)。"""
    rows: list[list[Any]] = []
    i = start
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch in " \t\r\n,":
            i += 1
            continue
        if ch == ";":
            return rows, i + 1
        if ch != "(":
            raise ValueError(f"unexpected token {ch!r} at {i}")
        i += 1
        row: list[Any] = []
        while True:
            while sql[i] in " \t\r\n":
                i += 1
            ch = sql[i]
            if ch == "'":
                i += 1
                buf: list[str] = []
                while True:
                    c = sql[i]
                    if c == "\\":
                        buf.append(_MYSQL_ESCAPES.get(sql[i + 1], sql[i + 1]))
                        i += 2
                    elif c == "'":
                        if i + 1 < n and sql[i + 1] == "'":
                            buf.append("'")
                            i += 2
                        else:
                            i += 1
                            break
                    else:
                        buf.append(c)
                        i += 1
                row.append("".join(buf))
            else:
                m = re.match(r"[^,)\s]+", sql[i:])
                if not m:
                    raise ValueError(f"cannot parse literal at {i}")
                token = m.group(0)
                i += len(token)
                if token.upper() == "NULL":
                    row.append(None)
                elif re.fullmatch(r"-?\d+", token):
                    row.append(int(token))
                elif re.fullmatch(r"-?\d+\.\d*", token):
                    row.append(float(token))
                elif token.upper() in {"NOW()", "CURRENT_TIMESTAMP"}:
                    row.append(datetime.now(timezone.utc))
                else:
                    row.append(token)
            while sql[i] in " \t\r\n":
                i += 1
            if sql[i] == ",":
                i += 1
                continue
            if sql[i] == ")":
                i += 1
                break
            raise ValueError(f"expected , or ) at {i}")
        rows.append(row)
    return rows, i


def load_prompt_template_seed(path: Path = _PROMPT_SEED_FILE) -> list[dict[str, Any]]:
    """把 MySQL 种子 SQL 中的 prompt_templates 行解析为 dict 列表。"""
    sql = path.read_text(encoding="utf-8")
    records: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"INSERT\s+(?:IGNORE\s+)?INTO\s+`?prompt_templates`?\s*\(([^)]*)\)\s*VALUES",
        re.IGNORECASE,
    )
    for m in pattern.finditer(sql):
        columns = [c.strip().strip("`") for c in m.group(1).split(",")]
        rows, _ = _parse_mysql_values(sql, m.end())
        for row in rows:
            rec = dict(zip(columns, row))
            records.setdefault(str(rec["id"]), rec)
    return list(records.values())


def _coerce_template_record(rec: dict[str, Any]) -> dict[str, Any]:
    variables = rec.get("variables")
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except json.JSONDecodeError:
            variables = []
    out: dict[str, Any] = {
        "id": str(rec["id"]),
        "category": rec["category"],
        "name": rec["name"],
        "preview": rec.get("preview") or "",
        "content": rec["content"],
        "variables": variables or [],
        "is_system": bool(rec.get("is_system")),
        "is_default": bool(rec.get("is_default")),
    }
    return out


async def seed_prompt_templates(session: AsyncSession) -> int:
    """写入缺失的系统提示词模板（已存在的同 id 记录不覆盖，保留用户修改）。"""
    from app.models.studio import PromptTemplate

    if not _PROMPT_SEED_FILE.exists():
        return 0
    existing = set((await session.execute(select(PromptTemplate.id))).scalars().all())
    added = 0
    for rec in load_prompt_template_seed():
        data = _coerce_template_record(rec)
        if data["id"] in existing:
            continue
        session.add(PromptTemplate(**data))
        added += 1
    if added:
        await session.flush()
    return added


# ---------------------------------------------------------------------------
# 火山方舟 / BytePlus ModelArk（Seedance）供应商
# ---------------------------------------------------------------------------


async def seed_ark_provider(session: AsyncSession) -> bool:
    """幂等创建 / 同步方舟供应商与默认模型；返回是否有写入。

    - 供应商 api_key / base_url 每次启动与环境变量同步（便于轮换 key）；
    - 模型按 (provider, category, name) 去重创建；
    - 默认模型在未设置、或仍指向本引导创建的模型时与环境变量保持一致；不覆盖用户在 UI 中选择的其他模型。
    """
    from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider, ProviderStatus
    from app.services.ark_autoconfig import ARK_REGION_LABELS, resolve_ark_plan

    plan = await resolve_ark_plan(session)
    if plan is None:
        return False

    changed = False
    provider = await session.get(Provider, ARK_PROVIDER_ID)
    if provider is None:
        provider = Provider(
            id=ARK_PROVIDER_ID,
            name="volcengine",
            base_url=plan["base_url"],
            api_key=plan["api_key"],
            api_secret="",
            description=f"Seedance / Seedream / Seed via {ARK_REGION_LABELS.get(plan['region'], 'Ark')} (auto-configured from deployment API key)",
            status=ProviderStatus.active,
            created_by="deploy-bootstrap",
        )
        session.add(provider)
        await session.flush()
        changed = True
    else:
        if provider.api_key != plan["api_key"] or provider.base_url != plan["base_url"]:
            provider.api_key = plan["api_key"]
            provider.base_url = plan["base_url"]
            changed = True

    model_ids: dict[ModelCategoryKey, str] = {}
    for category in (ModelCategoryKey.text, ModelCategoryKey.image, ModelCategoryKey.video):
        name = plan[category.value]
        stmt = select(Model).where(
            Model.provider_id == ARK_PROVIDER_ID,
            Model.category == category,
            Model.name == name,
        )
        model = (await session.execute(stmt)).scalars().first()
        if model is None:
            model = Model(
                id=f"{ARK_PROVIDER_ID}-{category.value}-{hashlib.sha1(name.encode()).hexdigest()[:8]}",
                name=name,
                category=category,
                provider_id=ARK_PROVIDER_ID,
                params={},
                description="auto-configured",
                created_by="deploy-bootstrap",
            )
            session.add(model)
            await session.flush()
            changed = True
        model_ids[category] = model.id

    settings_row = await session.get(ModelSettings, 1)
    if settings_row is None:
        settings_row = ModelSettings(id=1, api_timeout=120)
        session.add(settings_row)
        changed = True
    field_by_category = {
        ModelCategoryKey.text: "default_text_model_id",
        ModelCategoryKey.image: "default_image_model_id",
        ModelCategoryKey.video: "default_video_model_id",
    }
    for category, field in field_by_category.items():
        current_id = getattr(settings_row, field)
        target_id = model_ids[category]
        if current_id == target_id:
            continue
        if current_id:
            # 只跟随环境变量调整「由本引导创建的」默认模型；用户在 UI 中选择的其他模型不覆盖。
            current = await session.get(Model, current_id)
            if current is not None and current.created_by != "deploy-bootstrap":
                continue
        setattr(settings_row, field, target_id)
        changed = True
    await session.flush()
    return changed


async def run_deploy_bootstrap() -> dict[str, Any]:
    """完整引导流程（API 启动时调用）。异常向上抛出，由调用方决定是否阻断启动。"""
    from app.core.db import async_session_maker

    created = await ensure_schema()
    async with async_session_maker() as session:
        if session.bind.dialect.name == "postgresql":
            # 与建表相同的事务级 advisory lock：并发冷启动实例串行写入种子数据，避免主键冲突。
            await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        added_templates = await seed_prompt_templates(session)
        ark_changed = await seed_ark_provider(session)
        await session.commit()
    summary = {
        "schema_created": created,
        "prompt_templates_added": added_templates,
        "ark_provider_changed": ark_changed,
    }
    logger.info("deploy bootstrap done: %s", summary)
    return summary
