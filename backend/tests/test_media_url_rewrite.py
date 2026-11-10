"""换对象存储公网域名后，启动引导把老文件的 r2.dev 地址改到新域名；基址未配或仍是 r2.dev 时不动。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.core.db import Base
from app.deploy_bootstrap import rewrite_legacy_media_urls
from app.models.studio import FileItem, FileType


def _run(tmp_path: Path, base: str | None, monkeypatch: pytest.MonkeyPatch) -> tuple[int, list[str]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'media.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "s3_public_base_url", base)

    async def go() -> tuple[int, list[str]]:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with maker() as session:
            session.add_all(
                [
                    FileItem(id="f1", type=FileType.image, name="a.jpeg", storage_key="generated-images/a.jpeg", thumbnail="https://pub-abc123.r2.dev/generated-images/a%20b.jpeg"),
                    FileItem(id="f2", type=FileType.video, name="v.mp4", storage_key="generated-videos/v.mp4", thumbnail="https://pub-abc123.r2.dev/generated-videos/v.mp4"),
                    FileItem(id="f3", type=FileType.image, name="blob.png", storage_key="x", thumbnail="https://xyz.public.blob.vercel-storage.com/x.png"),
                    FileItem(id="f4", type=FileType.image, name="none", storage_key="y", thumbnail=""),
                ]
            )
            await session.commit()
        async with maker() as session:
            count = await rewrite_legacy_media_urls(session)
            await session.commit()
        async with maker() as session:
            urls = list((await session.execute(select(FileItem.thumbnail).order_by(FileItem.id))).scalars().all())
        await engine.dispose()
        return count, urls

    return asyncio.run(go())


def test_rewrites_r2_dev_urls_to_the_custom_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    count, urls = _run(tmp_path, "https://media.example.com/", monkeypatch)
    assert count == 2
    assert urls[0] == "https://media.example.com/generated-images/a%20b.jpeg"
    assert urls[1] == "https://media.example.com/generated-videos/v.mp4"
    assert urls[2].startswith("https://xyz.public.blob")  # 非 r2.dev 地址不动
    assert urls[3] == ""


def test_noop_when_base_missing_or_still_r2_dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    count, urls = _run(tmp_path, "https://pub-abc123.r2.dev", monkeypatch)
    assert count == 0 and urls[0].startswith("https://pub-abc123.r2.dev/")
    (tmp_path / "again").mkdir()
    count, _ = _run(tmp_path / "again", None, monkeypatch)
    assert count == 0
