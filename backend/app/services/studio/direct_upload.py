"""浏览器直传（Vercel Blob）：生成上传路径、签发客户端令牌、登记上传结果。

为什么存在：Vercel 函数请求体上限约 4.5 MB，视频片段几乎都超过；浏览器先向后端要一个一次性客户端令牌，
再直接 PUT 到 blob.vercel-storage.com，最后把结果登记成 FileItem，文件内容不经过后端函数。
S3 模式暂不提供直传（仍走 `/files/upload` 多部分上传）。
"""

from __future__ import annotations

import os
import re
import uuid
from urllib.parse import unquote, urlparse

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.models.studio import FileItem, FileType
from app.services.common import create_and_refresh
from app.services.studio.file_usages import upsert_file_usage

UPLOAD_PREFIX = "uploads/"
ALLOWED_CONTENT_TYPES: tuple[str, ...] = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/quicktime",
    "video/webm",
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
MAX_DIRECT_UPLOAD_BYTES = 500 * 1024 * 1024
# 经函数上传（/files/upload）的建议上限：Vercel 请求体 4.5 MB，留出 multipart 开销
MAX_SERVER_UPLOAD_BYTES = 4 * 1024 * 1024
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._一-鿿-]+")


def direct_upload_backend() -> str | None:
    """可用的直传后端：当前只有 `vercel_blob`（且配置了读写令牌）；否则 None。"""
    if storage.storage_backend() == "vercel_blob" and storage.blob_read_write_token():
        return "vercel_blob"
    return None


def file_type_for_name(filename: str) -> FileType:
    """按扩展名判断图片 / 视频；其它类型拒绝。"""
    _, ext = os.path.splitext((filename or "").lower())
    if ext in IMAGE_EXTENSIONS:
        return FileType.image
    if ext in VIDEO_EXTENSIONS:
        return FileType.video
    raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '未知后缀'}")


def build_upload_key(filename: str) -> tuple[str, str]:
    """为一次直传生成 (storage_key, pathname)：key 存进 FileItem，pathname 是浏览器实际 PUT 的路径（含 base_path）。"""
    base = os.path.basename(filename or "").strip() or "upload"
    safe = _UNSAFE_NAME.sub("-", base).strip("-")[:120] or "upload"
    file_type_for_name(safe)
    key = f"{UPLOAD_PREFIX}{uuid.uuid4().hex}/{safe}"
    return key, storage.normalize_storage_key(key)


def issue_client_token(*, pathname: str) -> str:
    """给 `@vercel/blob/client` 的 handleUpload 协议签发客户端令牌；只允许本服务生成的 uploads/ 路径。"""
    if direct_upload_backend() is None:
        raise HTTPException(status_code=409, detail="direct upload is unavailable: storage backend is not vercel_blob")
    allowed_prefix = storage.normalize_storage_key(UPLOAD_PREFIX.rstrip("/")) + "/"
    if (
        not pathname
        or ".." in pathname
        or pathname.startswith("/")
        or not pathname.startswith(allowed_prefix)
        or len(pathname) > 900
    ):
        raise HTTPException(status_code=400, detail="invalid upload pathname")
    file_type_for_name(pathname)
    return storage.generate_blob_client_token(
        pathname=pathname,
        allowed_content_types=list(ALLOWED_CONTENT_TYPES),
        maximum_size_in_bytes=MAX_DIRECT_UPLOAD_BYTES,
    )


async def register_uploaded_file(
    db: AsyncSession,
    *,
    storage_key: str,
    url: str,
    name: str | None,
    project_id: str | None = None,
    chapter_id: str | None = None,
    shot_id: str | None = None,
    usage_kind: str | None = None,
    source_ref: str | None = None,
) -> FileItem:
    """直传完成后登记 FileItem：校验 URL 确实指向本服务签发的那个 Blob 路径，再按 /files/upload 的规则写用途记录。"""
    if not storage_key.startswith(UPLOAD_PREFIX) or ".." in storage_key:
        raise HTTPException(status_code=400, detail="invalid storage key")
    parsed = urlparse(url or "")
    expected_path = "/" + storage.normalize_storage_key(storage_key)
    if parsed.scheme != "https" or not parsed.netloc.endswith("blob.vercel-storage.com") or unquote(parsed.path) != expected_path:
        raise HTTPException(status_code=400, detail="url does not match the prepared upload path")
    file_type = file_type_for_name(storage_key)
    display_name = (name or os.path.basename(storage_key)).strip()[:255] or os.path.basename(storage_key)
    item = await create_and_refresh(
        db,
        FileItem(id=str(uuid.uuid4()), type=file_type, name=display_name, thumbnail=url, tags=[], storage_key=storage_key),
    )
    if project_id and usage_kind:
        await upsert_file_usage(
            db,
            file_id=item.id,
            project_id=project_id,
            chapter_id=chapter_id,
            shot_id=shot_id,
            usage_kind=usage_kind,
            source_ref=source_ref,
        )
    return item
