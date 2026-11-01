"""应用配置，从环境变量加载。"""

import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_ROOT / ".env"


def is_vercel_runtime() -> bool:
    """是否运行在 Vercel（构建或函数运行时都会注入 VERCEL=1）。"""
    return (os.environ.get("VERCEL") or "").strip().lower() in {"1", "true", "yes"}


def normalize_database_url(url: str) -> str:
    """把各类托管 Postgres 连接串规范为 SQLAlchemy 可用的 psycopg (v3) URL。

    为什么需要：
    - Vercel Marketplace（Neon 等）注入的是 `postgres://` / `postgresql://` 形式；
    - psycopg 同时支持同步与异步引擎，Celery worker（同步）与 API（异步）可共用同一驱动；
    - libpq 参数（sslmode、channel_binding 等）可原样透传给 psycopg。
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    for prefix in ("postgres://", "postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://"):
        if raw.startswith(prefix):
            raw = "postgresql+psycopg://" + raw[len(prefix):]
            break
    if not raw.startswith("postgresql+psycopg://"):
        return raw
    # Prisma/pgbouncer 专用参数 libpq 不认识，去掉以免连接失败。
    parts = urlsplit(raw)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in {"pgbouncer", "connect_timeout_ms"}]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _default_database_url() -> str:
    """数据库 URL 解析顺序：DATABASE_URL > POSTGRES_URL（Vercel/Neon）> 本地 SQLite。"""
    for key in ("DATABASE_URL", "POSTGRES_URL"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return normalize_database_url(value)
    if is_vercel_runtime():
        # Vercel 函数文件系统只读（/tmp 除外）；无托管数据库时退化为临时 SQLite，仅用于冒烟测试。
        return "sqlite+aiosqlite:////tmp/jellyfish.db"
    return "sqlite+aiosqlite:///./jellyfish.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Jellyfish API"
    debug: bool = False

    # API
    api_v1_prefix: str = "/api/v1"

    # Database（为空时按 DATABASE_URL > POSTGRES_URL > SQLite 解析，见 _default_database_url）
    database_url: str = Field(default_factory=_default_database_url)

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> str:
        text = str(value or "").strip()
        return normalize_database_url(text) if text else _default_database_url()

    # 启动时自动建表 + 写入系统提示词模板（Vercel 等无 init 容器的环境默认开启）
    auto_init_db: bool = Field(default_factory=is_vercel_runtime)

    # Redis / Celery Broker
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    celery_broker_url: str | None = None

    # CORS：环境变量中建议使用逗号分隔（更贴近 docker-compose 用法）
    # 也兼容 JSON 数组：'["http://a","http://b"]'
    cors_origins: str = "http://localhost:7788,http://127.0.0.1:7788"

    @property
    def cors_origins_list(self) -> list[str]:
        s = (self.cors_origins or "").strip()
        if not s:
            return []
        if s.startswith("["):
            loaded = json.loads(s)
            if isinstance(loaded, list):
                return [str(x).strip() for x in loaded if str(x).strip()]
            return []
        return [x.strip() for x in s.split(",") if x.strip()]

    # S3 / 对象存储（用于素材文件）
    s3_endpoint_url: str | None = None
    s3_region_name: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket_name: str | None = None
    # 可选：统一前缀，方便按环境/项目隔离，如 "jellyfish/dev"
    s3_base_path: str = ""
    # 可选：对外访问基址（CDN 或自定义域名），为空则使用 S3 自带 URL 或预签名 URL
    s3_public_base_url: str | None = None

    # Vercel Blob（未配置 S3 且存在 BLOB_READ_WRITE_TOKEN 时作为对象存储）
    blob_read_write_token: str | None = None
    blob_access: str = "public"

    # 火山方舟 / BytePlus ModelArk（Seedance 视频、Seedream 图片、Seed 文本）
    # 若设置了 key，启动时自动创建供应商、模型与默认模型设置（幂等）。
    ark_api_key: str | None = Field(
        default_factory=lambda: (os.environ.get("ARK_API_KEY") or os.environ.get("SEEDDANCE_API_KEY") or "").strip() or None
    )
    ark_base_url: str | None = None
    ark_text_model: str | None = None
    ark_image_model: str | None = None
    ark_video_model: str | None = None

    def model_post_init(self, __context: object) -> None:
        if (not self.celery_broker_url or not str(self.celery_broker_url).strip()) and is_vercel_runtime():
            # Vercel 上使用 Vercel Queues 作为 Celery broker（vercel-celery 集成）。
            self.celery_broker_url = "vercel://"
        if not self.celery_broker_url or not str(self.celery_broker_url).strip():
            password_part = f":{self.redis_password}@" if self.redis_password else ""
            self.celery_broker_url = f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
