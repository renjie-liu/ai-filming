"""浏览器直传：生成上传路径、签发上传凭证（Blob 客户端令牌 / S3 预签名 PUT）、登记上传结果。

为什么存在：Vercel 函数请求体上限约 4.5 MB，视频片段几乎都超过；浏览器先向后端要一次性上传凭证，
再把文件直接 PUT 到对象存储，最后把结果登记成 FileItem，文件内容不经过后端函数。

两种后端：
- `vercel_blob`：按 `@vercel/blob/client` 的 handleUpload 协议签发客户端令牌，浏览器 PUT 到 blob.vercel-storage.com；
- `s3`（含 Cloudflare R2）：后端用 boto3 本地签出预签名 PUT URL，浏览器带同样的 Content-Type 直接 PUT 到桶；
  登记时后端 HeadObject 确认对象确实存在，再写 FileItem。桶需要允许跨域 PUT（见 storage.ensure_bucket_cors）。
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/aac",
    "audio/x-m4a",
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}
# 扩展名 → 直传时默认的 Content-Type（浏览器未给出 file.type 时使用）
_DEFAULT_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}
MAX_DIRECT_UPLOAD_BYTES = 500 * 1024 * 1024
# 经函数上传（/files/upload）的建议上限：Vercel 请求体 4.5 MB，留出 multipart 开销
MAX_SERVER_UPLOAD_BYTES = 4 * 1024 * 1024
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._一-鿿-]+")
_UNAVAILABLE_DETAIL = "direct upload is unavailable: storage backend has no browser upload path"


@dataclass
class PreparedUpload:
    """一次直传的准备结果：浏览器据此直接 PUT。

    - storage_key：登记时回传、写进 FileItem 的逻辑 key；
    - pathname：实际对象路径（含 base_path）；Blob 直传时浏览器用它调用 `upload()`；
    - upload_url / headers：S3 模式下预签名 PUT 的地址与必须携带的请求头（Content-Type 参与签名）；Blob 模式为空；
    - public_url：S3 模式下上传完成后对象的公网 URL（登记时必须回传同一个）。
    """

    backend: str
    storage_key: str
    pathname: str
    upload_url: str | None = None
    public_url: str | None = None
    headers: dict[str, str] | None = None


def direct_upload_backend() -> str | None:
    """可用的直传后端：`vercel_blob`（配置了读写令牌）或 `s3`（配置了桶，含 R2）；否则 None（只能经函数上传）。"""
    backend = storage.storage_backend()
    if backend == "vercel_blob" and storage.blob_read_write_token():
        return "vercel_blob"
    if backend == "s3" and settings.s3_bucket_name:
        return "s3"
    return None


def file_type_for_name(filename: str) -> FileType:
    """按扩展名判断图片 / 视频 / 音频；其它类型拒绝。"""
    _, ext = os.path.splitext((filename or "").lower())
    if ext in IMAGE_EXTENSIONS:
        return FileType.image
    if ext in VIDEO_EXTENSIONS:
        return FileType.video
    if ext in AUDIO_EXTENSIONS:
        return FileType.audio
    raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '未知后缀'}")


def content_type_for_upload(filename: str, requested: str | None) -> str:
    """直传对象的 Content-Type：浏览器给出且在白名单内则用它，否则按扩展名推断。"""
    requested = (requested or "").split(";", 1)[0].strip().lower()
    if requested in ALLOWED_CONTENT_TYPES:
        return requested
    _, ext = os.path.splitext((filename or "").lower())
    return _DEFAULT_CONTENT_TYPES.get(ext, "application/octet-stream")


def build_upload_key(filename: str) -> tuple[str, str]:
    """为一次直传生成 (storage_key, pathname)：key 存进 FileItem，pathname 是浏览器实际 PUT 的路径（含 base_path）。"""
    base = os.path.basename(filename or "").strip() or "upload"
    safe = _UNSAFE_NAME.sub("-", base).strip("-")[:120] or "upload"
    file_type_for_name(safe)
    key = f"{UPLOAD_PREFIX}{uuid.uuid4().hex}/{safe}"
    return key, storage.normalize_storage_key(key)


def prepare_direct_upload(*, filename: str, content_type: str | None = None) -> PreparedUpload:
    """准备一次直传：生成路径；S3 模式额外签出预签名 PUT URL 与公网 URL。无直传后端时 409。"""
    backend = direct_upload_backend()
    if backend is None:
        raise HTTPException(status_code=409, detail=_UNAVAILABLE_DETAIL)
    storage_key, pathname = build_upload_key(filename)
    if backend == "vercel_blob":
        return PreparedUpload(backend=backend, storage_key=storage_key, pathname=pathname)
    resolved_type = content_type_for_upload(storage_key, content_type)
    try:
        upload_url = storage.generate_presigned_put_url(key=storage_key, content_type=resolved_type)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Storage unavailable: could not presign upload ({type(exc).__name__})") from exc
    return PreparedUpload(
        backend=backend,
        storage_key=storage_key,
        pathname=pathname,
        upload_url=upload_url,
        public_url=storage.public_url_for_key(storage_key),
        headers={"Content-Type": resolved_type},
    )


def issue_client_token(*, pathname: str) -> str:
    """给 `@vercel/blob/client` 的 handleUpload 协议签发客户端令牌；只允许本服务生成的 uploads/ 路径。"""
    if direct_upload_backend() != "vercel_blob":
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


def _check_blob_url(storage_key: str, url: str) -> None:
    """Blob 模式：URL 必须是 blob.vercel-storage.com 上、路径等于本服务签发的 pathname。"""
    parsed = urlparse(url or "")
    expected_path = "/" + storage.normalize_storage_key(storage_key)
    if parsed.scheme != "https" or not parsed.netloc.endswith("blob.vercel-storage.com") or unquote(parsed.path) != expected_path:
        raise HTTPException(status_code=400, detail="url does not match the prepared upload path")


async def _check_s3_url(storage_key: str, url: str) -> storage.StoredFileInfo:
    """S3 / R2 模式：URL 必须等于本服务计算的公网 URL，并且对象确实已上传（HeadObject）。返回对象元信息。"""
    expected = storage.public_url_for_key(storage_key)
    if unquote(url or "") != unquote(expected):
        raise HTTPException(status_code=400, detail="url does not match the prepared upload path")
    try:
        return await storage.get_file_info(key=storage_key)
    except storage.StorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # boto3 ClientError 404 等
        raise HTTPException(status_code=400, detail=f"uploaded object not found in storage: {type(exc).__name__}") from exc


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
    """直传完成后登记 FileItem：按当前存储后端校验 URL 确实指向本服务签发的那个对象，再按 /files/upload 的规则写用途记录。"""
    if not storage_key.startswith(UPLOAD_PREFIX) or ".." in storage_key:
        raise HTTPException(status_code=400, detail="invalid storage key")
    if storage.storage_backend() == "vercel_blob":
        _check_blob_url(storage_key, url)
    else:
        await _check_s3_url(storage_key, url)
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
