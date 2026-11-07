"""对象存储：Vercel Blob「存储不可用」类异常会被包成 StorageUnavailableError，上传接口转成 503。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import storage


class BlobStoreSuspendedError(Exception):
    """模拟 vercel.blob 的同名异常（按类名匹配，不依赖 SDK）。"""


class _FakeBlobModule:
    async def put_blob(self, *_args, **_kwargs):
        raise BlobStoreSuspendedError("This store has been suspended.")


@pytest.mark.asyncio
async def test_blob_suspended_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "_blob_module", lambda: _FakeBlobModule())
    with pytest.raises(storage.StorageUnavailableError) as info:
        await storage._blob_upload(key="files/x/a.png", data=b"png", content_type="image/png")
    assert "BlobStoreSuspendedError" in str(info.value) and "suspended" in str(info.value)


def test_other_blob_errors_pass_through() -> None:
    exc = ValueError("content_type must be a string")
    assert storage._wrap_blob_error(exc, "upload") is exc


@pytest.mark.asyncio
async def test_upload_api_maps_unavailable_storage_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    from io import BytesIO

    from starlette.datastructures import UploadFile

    from app.services.studio import files as files_service

    async def _boom(**_kwargs):
        raise storage.StorageUnavailableError("Blob storage unavailable during upload: BlobStoreSuspendedError: suspended")

    monkeypatch.setattr(files_service.storage, "upload_file", _boom)
    upload = UploadFile(filename="a.png", file=BytesIO(b"png"))
    with pytest.raises(HTTPException) as info:
        await files_service.upload_file(None, file=upload)  # type: ignore[arg-type]  # 未触达数据库即抛错
    assert info.value.status_code == 503 and "BlobStoreSuspendedError" in str(info.value.detail)
