"""统一的对象存储封装（目前以 S3 兼容为主）。

设计目标：
- 提供上传 / 下载 / 列表 / 详情 等基础能力；
- 尽量不绑定具体云厂商，只依赖 S3 兼容协议；
- 在 FastAPI 异步环境下，避免阻塞事件循环：通过 anyio 在线程池中调用 boto3。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, BinaryIO

import boto3
from anyio import to_thread
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings


class StorageUnavailableError(RuntimeError):
    """对象存储暂时不可用（Vercel Blob 超出额度被暂停、凭证失效、限流等）。

    为什么存在：这类错误不是用户输入问题，也不是代码缺陷；上传接口把它转成 503 并给出可读原因，
    生成任务则把它写进 task.error，前端统一映射成「存储已暂停」提示，而不是笼统的 500。
    """


# vercel.blob 里表示「整个存储不可用」的异常类名（按名字匹配，避免在 S3 模式下导入 Blob SDK）
_BLOB_UNAVAILABLE_ERROR_NAMES = {
    "BlobStoreSuspendedError",
    "BlobStoreNotFoundError",
    "BlobServiceRateLimited",
    "BlobAccessError",
    "BlobCredentialsError",
}


def _wrap_blob_error(exc: BaseException, operation: str) -> BaseException:
    """把 Blob SDK 的「存储不可用」异常包成 StorageUnavailableError；其它异常原样返回。"""
    name = type(exc).__name__
    if name in _BLOB_UNAVAILABLE_ERROR_NAMES:
        return StorageUnavailableError(f"Blob storage unavailable during {operation}: {name}: {exc}")
    return exc


@dataclass
class StoredFileInfo:
    """文件基础信息（供调用方在路由层自行封装为 Pydantic schema）。"""

    key: str
    url: str
    size: int | None = None
    content_type: str | None = None
    etag: str | None = None
    extra: dict[str, Any] | None = None


def storage_backend() -> str:
    """当前对象存储后端：`s3`（显式配置了 bucket）或 `vercel_blob`（存在 Blob 凭证）。"""
    if settings.s3_bucket_name:
        return "s3"
    if (
        settings.blob_read_write_token
        or os.environ.get("BLOB_READ_WRITE_TOKEN")
        or os.environ.get("VERCEL_BLOB_READ_WRITE_TOKEN")
        or os.environ.get("BLOB_STORE_ID")
    ):
        return "vercel_blob"
    return "s3"


def _use_blob() -> bool:
    return storage_backend() == "vercel_blob"


def _blob_access() -> str:
    return "private" if (settings.blob_access or "").strip().lower() == "private" else "public"


def _ensure_blob_token_env() -> None:
    """vercel-blob SDK 只读取环境变量；若通过 settings/.env 提供 token，则同步到环境变量。"""
    if settings.blob_read_write_token and not os.environ.get("BLOB_READ_WRITE_TOKEN"):
        os.environ["BLOB_READ_WRITE_TOKEN"] = settings.blob_read_write_token


def _build_s3_client():
    if not settings.s3_bucket_name:
        raise RuntimeError("S3 未配置：请在配置中设置 s3_bucket_name 等必要字段")

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region_name,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=BotoConfig(s3={"addressing_style": "virtual"}),
    )
    return client


def _normalize_key(key: str) -> str:
    key = key.lstrip("/")
    base = settings.s3_base_path.strip().strip("/")
    if base:
        return f"{base}/{key}"
    return key


def _build_public_url(key: str) -> str:
    key = _normalize_key(key)
    if settings.s3_public_base_url:
        base = settings.s3_public_base_url.rstrip("/")
        return f"{base}/{key}"
    # fallback：使用标准 S3 URL 形式；具体可根据实际厂商调整
    if not settings.s3_bucket_name:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")
    endpoint = settings.s3_endpoint_url.rstrip("/") if settings.s3_endpoint_url else ""
    if endpoint:
        return f"{endpoint}/{settings.s3_bucket_name}/{key}"
    # 若未配置 endpoint，则退回最基础的 path 形式
    return f"/{settings.s3_bucket_name}/{key}"


def init_storage() -> None:
    """初始化对象存储（例如创建 bucket）。

    说明：
    - 若 bucket 已存在则直接返回；
    - 若无权限/配置错误会抛出异常，便于在部署时尽早失败；
    - 对于部分 S3 兼容服务（MinIO 等），CreateBucket 的参数可能不同，这里尽量兼容常见情形。
    """
    if _use_blob():
        # Vercel Blob store 由平台创建并通过环境变量注入凭证，无需初始化。
        return

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if not bucket:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        # 常见不存在：404 / NoSuchBucket / NotFound
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise

    params: dict[str, Any] = {"Bucket": bucket}
    region = settings.s3_region_name
    # AWS S3 在 us-east-1 不需要 LocationConstraint，其他 region 需要
    if region and region != "us-east-1":
        params["CreateBucketConfiguration"] = {"LocationConstraint": region}

    try:
        client.create_bucket(**params)
    except ClientError as e:
        # 可能出现并发创建或服务端返回已存在
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            return
        raise

    # 再次确认 bucket 可用
    client.head_bucket(Bucket=bucket)


async def upload_file(
    *,
    key: str,
    data: bytes | BinaryIO,
    content_type: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> StoredFileInfo:
    """上传文件到 S3。

    参数：
    - key：逻辑 key（不需要带 base_path，会自动拼接）；
    - data：字节内容或类文件对象；
    - content_type：MIME 类型，例如 image/png；
    - extra_args：透传给 boto3 的 ExtraArgs，如 {"ACL": "public-read"}。
    """

    if _use_blob():
        return await _blob_upload(key=key, data=data, content_type=content_type)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)
    extra = extra_args.copy() if extra_args else {}
    if content_type and "ContentType" not in extra:
        extra["ContentType"] = content_type

    def _upload():
        if isinstance(data, (bytes, bytearray)):
            return client.put_object(Bucket=bucket, Key=s3_key, Body=data, **extra)
        return client.upload_fileobj(data, bucket, s3_key, ExtraArgs=extra)  # type: ignore[arg-type]

    result = await to_thread.run_sync(_upload)

    etag = None
    if isinstance(result, dict):
        etag = result.get("ETag")

    url = _build_public_url(key)
    return StoredFileInfo(key=s3_key, url=url, etag=etag)


async def download_file(*, key: str) -> bytes:
    """下载文件内容（整个对象读入内存）。"""
    if _use_blob():
        return await _blob_download(key=key)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)

    def _download() -> bytes:
        obj = client.get_object(Bucket=bucket, Key=s3_key)
        body = obj["Body"].read()
        return body  # type: ignore[no-any-return]

    return await to_thread.run_sync(_download)


async def get_file_info(*, key: str) -> StoredFileInfo:
    """获取文件元信息（不下载内容）。"""
    if _use_blob():
        return await _blob_head(key=key)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)

    def _head() -> dict[str, Any]:
        return client.head_object(Bucket=bucket, Key=s3_key)  # type: ignore[no-any-return]

    meta = await to_thread.run_sync(_head)

    size = int(meta.get("ContentLength") or 0)
    content_type = meta.get("ContentType")
    etag = meta.get("ETag")

    url = _build_public_url(key)
    return StoredFileInfo(
        key=s3_key,
        url=url,
        size=size,
        content_type=content_type,
        etag=etag,
        extra={k: v for k, v in meta.items() if k not in {"ContentLength", "ContentType", "ETag"}},
    )


async def list_files(*, prefix: str = "") -> list[StoredFileInfo]:
    """根据前缀列出文件（最多一页，若需翻页可扩展）。"""
    if _use_blob():
        return await _blob_list(prefix=prefix)

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    normalized_prefix = _normalize_key(prefix) if prefix else settings.s3_base_path.strip().strip("/")

    def _list() -> list[dict[str, Any]]:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=normalized_prefix or None)
        return resp.get("Contents", [])  # type: ignore[no-any-return]

    contents = await to_thread.run_sync(_list)

    results: list[StoredFileInfo] = []
    for item in contents:
        key = item["Key"]
        size = int(item.get("Size") or 0)
        url = _build_public_url(key)
        results.append(
            StoredFileInfo(
                key=key,
                url=url,
                size=size,
                extra={"LastModified": item.get("LastModified"), "StorageClass": item.get("StorageClass")},
            )
        )
    return results


async def delete_file(*, key: str) -> None:
    """删除文件。"""
    if _use_blob():
        await _blob_delete(key=key)
        return

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if bucket is None:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    s3_key = _normalize_key(key)

    def _delete() -> None:
        client.delete_object(Bucket=bucket, Key=s3_key)

    await to_thread.run_sync(_delete)



# ---------------------------------------------------------------------------
# Vercel Blob 后端
#
# 说明：
# - key 语义与 S3 一致（逻辑 key + 可选 s3_base_path 前缀），作为 Blob pathname；
# - 允许覆盖同名对象，保持与 S3 put_object 相同的语义；
# - 默认 public store：返回的 url 可直接在浏览器预览（key 中通常包含 uuid）。
# ---------------------------------------------------------------------------


def _blob_module():
    _ensure_blob_token_env()
    from vercel import blob as vercel_blob

    return vercel_blob


async def _blob_upload(*, key: str, data: bytes | BinaryIO, content_type: str | None) -> StoredFileInfo:
    vercel_blob = _blob_module()
    pathname = _normalize_key(key)
    body = bytes(data) if isinstance(data, (bytes, bytearray, memoryview)) else data.read()
    try:
        result = await vercel_blob.put_blob(
            pathname,
            body,
            access=_blob_access(),  # type: ignore[arg-type]
            content_type=content_type,
            allow_overwrite=True,
        )
    except Exception as exc:
        raise _wrap_blob_error(exc, "upload") from exc
    return StoredFileInfo(key=pathname, url=result.url, size=len(body), content_type=content_type, etag=result.etag)


async def _blob_download(*, key: str) -> bytes:
    vercel_blob = _blob_module()
    result = await vercel_blob.get_blob(_normalize_key(key), access=_blob_access())  # type: ignore[arg-type]
    return result.body


async def _blob_head(*, key: str) -> StoredFileInfo:
    vercel_blob = _blob_module()
    pathname = _normalize_key(key)
    meta = await vercel_blob.head_blob(pathname)
    return StoredFileInfo(
        key=pathname,
        url=meta.url,
        size=int(meta.size or 0),
        content_type=meta.content_type,
        etag=meta.etag,
        extra={"uploaded_at": meta.uploaded_at, "download_url": meta.download_url},
    )


async def _blob_list(*, prefix: str = "") -> list[StoredFileInfo]:
    vercel_blob = _blob_module()
    normalized_prefix = _normalize_key(prefix) if prefix else settings.s3_base_path.strip().strip("/")
    results: list[StoredFileInfo] = []
    async for item in vercel_blob.query_blobs(prefix=normalized_prefix or None, page_size=1000):
        results.append(
            StoredFileInfo(
                key=item.pathname,
                url=item.url,
                size=int(item.size or 0),
                etag=item.etag,
                extra={"LastModified": item.uploaded_at},
            )
        )
        if len(results) >= 1000:
            break
    return results


async def _blob_delete(*, key: str) -> None:
    vercel_blob = _blob_module()
    await vercel_blob.delete_blob(_normalize_key(key))
