"""浏览器直传：客户端令牌与 @vercel/blob 逐字节一致、路径校验、登记文件记录。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core import storage
from app.models.studio import FileItem, FileType
from app.services.studio import direct_upload
from tests.test_creator_flow import _build_session

# 由 node 的 @vercel/blob/client generateClientTokenFromReadWriteToken 对同一参数生成（2026-11-07 校验）
_EXPECTED_TOKEN = (
    "vercel_blob_client_STORE123abc_MmI1YjRlYTBkOTczZjJjZjJmMDM1NDdkYTFhOTgzNmNjMDlmYmIxZDQ4Nzk3YjY5ODAzMTY5MTk3OWZmMzEwYi5l"
    "eUp3WVhSb2JtRnRaU0k2SW5Wd2JHOWhaSE12WVM5aUxtMXdOQ0lzSW1Ga1pGSmhibVJ2YlZOMVptWnBlQ0k2Wm1Gc2MyVXNJbUZzYkc5M1QzWmxjbmR5YVhS"
    "bElqcG1ZV3h6WlN3aVlXeHNiM2RsWkVOdmJuUmxiblJVZVhCbGN5STZXeUoyYVdSbGJ5OXRjRFFpTENKcGJXRm5aUzl3Ym1jaVhTd2liV0Y0YVcxMWJWTnBl"
    "bVZKYmtKNWRHVnpJam94TURBd0xDSjJZV3hwWkZWdWRHbHNJam94TnprME1EQXdNREF3TURBd2ZRPT0="
)


def test_client_token_matches_vercel_blob_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_STORE123abc_secretXYZ")
    monkeypatch.setattr(storage.settings, "blob_read_write_token", None, raising=False)
    token = storage.generate_blob_client_token(
        pathname="uploads/a/b.mp4",
        allowed_content_types=["video/mp4", "image/png"],
        maximum_size_in_bytes=1000,
        valid_until_ms=1794000000000,
    )
    assert token == _EXPECTED_TOKEN
    assert storage.blob_store_id_from_token("vercel_blob_rw_STORE123abc_secretXYZ") == "STORE123abc"
    assert storage.blob_store_id_from_token("nope") is None


def test_issue_client_token_only_for_prepared_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_STORE123abc_secretXYZ")
    monkeypatch.setattr(storage.settings, "blob_read_write_token", None, raising=False)
    monkeypatch.setattr(direct_upload, "direct_upload_backend", lambda: "vercel_blob")
    key, pathname = direct_upload.build_upload_key("我的 视频.mp4")
    assert key.startswith("uploads/") and key.endswith("/我的-视频.mp4")
    assert direct_upload.issue_client_token(pathname=pathname).startswith("vercel_blob_client_STORE123abc_")
    for bad in ("", "/uploads/x.mp4", "files/x.mp4", "uploads/../x.mp4", "uploads/a/x.exe"):
        with pytest.raises(HTTPException):
            direct_upload.issue_client_token(pathname=bad)
    monkeypatch.setattr(direct_upload, "direct_upload_backend", lambda: None)
    with pytest.raises(HTTPException) as info:
        direct_upload.issue_client_token(pathname=pathname)
    assert info.value.status_code == 409


@pytest.mark.asyncio
async def test_register_uploaded_file_checks_url_and_creates_record() -> None:
    db, engine = await _build_session()
    async with db:
        key, pathname = direct_upload.build_upload_key("clip.mp4")
        good_url = f"https://store.public.blob.vercel-storage.com/{pathname}"
        with pytest.raises(HTTPException):
            await direct_upload.register_uploaded_file(db, storage_key=key, url="https://evil.example/" + pathname, name="clip.mp4")
        with pytest.raises(HTTPException):
            await direct_upload.register_uploaded_file(db, storage_key="files/other.mp4", url=good_url, name="clip.mp4")
        item = await direct_upload.register_uploaded_file(db, storage_key=key, url=good_url, name="clip.mp4")
        assert item.type == FileType.video and item.thumbnail == good_url and item.storage_key == key
        assert (await db.execute(select(FileItem).where(FileItem.id == item.id))).scalars().one().name == "clip.mp4"
    await engine.dispose()
