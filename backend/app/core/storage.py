"""统一的对象存储封装（S3 兼容协议为主，含 Cloudflare R2；也支持 Vercel Blob）。

设计目标：
- 提供上传 / 下载 / 列表 / 详情 / 浏览器直传预签名 等基础能力；
- 尽量不绑定具体云厂商，只依赖 S3 兼容协议（AWS S3、Cloudflare R2、MinIO / RustFS 等）；
- 在 FastAPI 异步环境下，避免阻塞事件循环：通过 anyio 在线程池中调用 boto3。

Cloudflare R2 的差异（端点 `*.r2.cloudflarestorage.com` 时自动启用）：region 固定为 `auto`、
path-style 寻址、不能带 LocationConstraint 建桶，并且不接受 boto3 ≥ 1.36 默认附加的 CRC 校验头
（需要 `request_checksum_calculation=when_required`）。
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, BinaryIO
from urllib.parse import quote, urlparse

import boto3
from anyio import to_thread
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

# 浏览器直传预签名 PUT 的有效期（秒）：足够覆盖大文件上传，又不会长期有效。
PRESIGNED_PUT_EXPIRES_SECONDS = 3600
# 浏览器直传与跨域读取（合成导出 fetch 片段）需要的 CORS 规则；写入桶时按此规则比对，已存在则不重复写。
_CORS_RULE: dict[str, Any] = {
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["GET", "HEAD", "PUT"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
    "MaxAgeSeconds": 3600,
}


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


def is_cloudflare_r2() -> bool:
    """端点是否为 Cloudflare R2（`<account>.r2.cloudflarestorage.com`）；R2 需要几处与 AWS 不同的客户端参数。"""
    host = (urlparse(settings.s3_endpoint_url or "").hostname or "").lower()
    return host.endswith(".r2.cloudflarestorage.com") or host == "r2.cloudflarestorage.com"


def _s3_region() -> str | None:
    """签名用的 region：显式配置优先；R2 固定为 `auto`。"""
    region = (settings.s3_region_name or "").strip()
    if region:
        return region
    return "auto" if is_cloudflare_r2() else None


def _s3_addressing_style() -> str:
    """寻址方式：显式配置（`S3_ADDRESSING_STYLE=path|virtual|auto`）优先；R2 用 path，其它沿用 virtual。"""
    style = (settings.s3_addressing_style or "").strip().lower()
    if style in {"path", "virtual", "auto"}:
        return style
    return "path" if is_cloudflare_r2() else "virtual"


def _build_s3_client():
    """按配置构造 boto3 S3 客户端；R2 额外关闭默认 CRC 校验（R2 不接受 aws-chunked + x-amz-checksum-*）。"""
    if not settings.s3_bucket_name:
        raise RuntimeError("S3 未配置：请在配置中设置 s3_bucket_name 等必要字段")

    config_kwargs: dict[str, Any] = {"s3": {"addressing_style": _s3_addressing_style()}, "signature_version": "s3v4"}
    if is_cloudflare_r2():
        config_kwargs["request_checksum_calculation"] = "when_required"
        config_kwargs["response_checksum_validation"] = "when_required"
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=_s3_region(),
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=BotoConfig(**config_kwargs),
    )
    return client


def _normalize_key(key: str) -> str:
    key = key.lstrip("/")
    base = settings.s3_base_path.strip().strip("/")
    if base:
        return f"{base}/{key}"
    return key


def _build_public_url(key: str) -> str:
    """对象的公网 URL：`S3_PUBLIC_BASE_URL/<key>`（R2 的 r2.dev 或自定义域名、CDN），否则 `<endpoint>/<bucket>/<key>`。

    key 中的中文 / 空格等按 RFC 3986 转义（保留 `/`），保证 URL 可直接放进 `<img>` / `<video>` 与方舟请求。
    """
    key = quote(_normalize_key(key), safe="/")
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


def public_url_for_key(key: str) -> str:
    """对外暴露的公网 URL 计算（S3 模式）；直传登记时用它校验浏览器回传的 URL。"""
    return _build_public_url(key)


def _cors_rule_present(rules: list[dict[str, Any]]) -> bool:
    """桶上是否已有一条「允许任意来源 GET/HEAD/PUT」的规则（手工在控制台配置的也算）。"""
    for rule in rules or []:
        origins = set(rule.get("AllowedOrigins") or [])
        methods = {m.upper() for m in (rule.get("AllowedMethods") or [])}
        if "*" in origins and {"GET", "PUT"} <= methods:
            return True
    return False


def ensure_bucket_cors(client: Any | None = None) -> bool:
    """确保桶允许浏览器跨域 PUT（直传）与 GET（合成导出 fetch 片段）；已有等价规则则不写。返回是否写入。

    R2 / S3 的 PutBucketCors 需要桶级（管理）权限；只给了对象读写权限的令牌会抛 AccessDenied，
    调用方按「尽力而为」处理并提示在控制台手工配置。
    """
    client = client or _build_s3_client()
    bucket = settings.s3_bucket_name
    try:
        existing = client.get_bucket_cors(Bucket=bucket).get("CORSRules", [])
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code not in {"NoSuchCORSConfiguration", "404", "NotFound"}:
            raise
        existing = []
    if _cors_rule_present(existing):
        return False
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [*existing, dict(_CORS_RULE)]})
    return True


def init_storage(*, configure_cors: bool = True) -> dict[str, Any]:
    """初始化对象存储：确保 bucket 存在，并（可选）写入浏览器直传需要的 CORS 规则。

    说明：
    - 若 bucket 已存在则不重复创建；R2 / region=auto 不带 LocationConstraint，AWS 非 us-east-1 才带；
    - 若无权限 / 配置错误会抛出异常，便于在部署时尽早失败；
    - CORS 写入失败（通常是令牌没有桶级权限）只记录警告、不抛出，返回值里标明 `cors=error`。
    返回 `{"bucket_created": bool, "cors": "written" | "present" | "skipped" | "error"}`。
    """
    if _use_blob():
        # Vercel Blob store 由平台创建并通过环境变量注入凭证，无需初始化。
        return {"bucket_created": False, "cors": "skipped"}

    client = _build_s3_client()
    bucket = settings.s3_bucket_name
    if not bucket:
        raise RuntimeError("S3 未配置：缺少 s3_bucket_name")

    created = False
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        # 常见不存在：404 / NoSuchBucket / NotFound
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        params: dict[str, Any] = {"Bucket": bucket}
        region = _s3_region()
        # AWS S3 在 us-east-1 不需要 LocationConstraint，其他 region 需要；R2（auto）不接受该参数
        if region and region not in {"us-east-1", "auto"}:
            params["CreateBucketConfiguration"] = {"LocationConstraint": region}
        try:
            client.create_bucket(**params)
            created = True
        except ClientError as e2:
            # 可能出现并发创建或服务端返回已存在
            code = str(e2.response.get("Error", {}).get("Code", ""))
            if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise
        # 再次确认 bucket 可用
        client.head_bucket(Bucket=bucket)

    cors = "skipped"
    if configure_cors:
        try:
            cors = "written" if ensure_bucket_cors(client) else "present"
        except Exception as exc:
            logger.warning("storage: could not configure bucket CORS (configure it in the console): %s", exc)
            cors = "error"
    return {"bucket_created": created, "cors": cors}


def generate_presigned_put_url(*, key: str, content_type: str | None, expires_in: int = PRESIGNED_PUT_EXPIRES_SECONDS) -> str:
    """为浏览器直传签发预签名 PUT URL（S3 / R2）。

    浏览器必须用同样的 Content-Type 头 PUT（它参与签名），文件内容不经过后端函数。
    这是本地 HMAC 计算，不发网络请求。
    """
    client = _build_s3_client()
    params: dict[str, Any] = {"Bucket": settings.s3_bucket_name, "Key": _normalize_key(key)}
    if content_type:
        params["ContentType"] = content_type
    return client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires_in, HttpMethod="PUT")  # type: ignore[no-any-return]


def describe_storage() -> dict[str, Any]:
    """面向诊断接口的存储配置摘要（不含密钥）：后端、桶、端点主机、公网基址、是否 R2、直传方式。"""
    backend = storage_backend()
    info: dict[str, Any] = {"backend": backend}
    if backend == "s3":
        info.update(
            {
                "bucket": settings.s3_bucket_name,
                "endpoint_host": urlparse(settings.s3_endpoint_url or "").hostname,
                "region": _s3_region(),
                "public_base_url": settings.s3_public_base_url,
                "cloudflare_r2": is_cloudflare_r2(),
                "configured": bool(settings.s3_bucket_name),
            }
        )
    else:
        token = blob_read_write_token()
        info.update({"store_id": blob_store_id_from_token(token) if token else None, "access": _blob_access(), "configured": bool(token)})
    return info


async def probe_storage() -> dict[str, Any]:
    """对当前存储做一次轻量只读探测：S3 为 HeadBucket，Blob 为 head 一个不存在的路径（能区分「未找到」与「已暂停」）。"""
    out: dict[str, Any] = {}
    t0 = time.perf_counter()
    try:
        if _use_blob():
            try:
                await _blob_head(key="_deploy/probe-does-not-exist")
            except Exception as exc:  # noqa: BLE001
                wrapped = _wrap_blob_error(exc, "probe")
                if isinstance(wrapped, StorageUnavailableError) or type(exc).__name__ != "BlobNotFoundError":
                    raise wrapped from exc
            out["ok"] = True
        elif settings.s3_bucket_name:
            client = _build_s3_client()
            await to_thread.run_sync(lambda: client.head_bucket(Bucket=settings.s3_bucket_name))
            out["ok"] = True
        else:
            out["ok"] = False
            out["error"] = "storage is not configured"
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    out["ms"] = int((time.perf_counter() - t0) * 1000)
    return out


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


# ---------------------------------------------------------------------------
# Vercel Blob 浏览器直传：客户端令牌
# ---------------------------------------------------------------------------


def blob_read_write_token() -> str | None:
    """当前配置的 Blob 读写令牌（settings 或环境变量）；未配置返回 None。"""
    _ensure_blob_token_env()
    return (settings.blob_read_write_token or os.environ.get("BLOB_READ_WRITE_TOKEN") or "").strip() or None


def blob_store_id_from_token(token: str) -> str | None:
    """读写令牌格式 `vercel_blob_rw_<storeId>_<secret>`，取第 4 段为 store ID。"""
    parts = token.split("_")
    if len(parts) >= 5 and parts[0] == "vercel" and parts[1] == "blob":
        return parts[3] or None
    return None


def normalize_storage_key(key: str) -> str:
    """对外暴露的 key 归一化（拼上 base_path），直传时浏览器要用归一化后的 pathname。"""
    return _normalize_key(key)


def generate_blob_client_token(
    *,
    pathname: str,
    allowed_content_types: list[str] | None = None,
    maximum_size_in_bytes: int | None = None,
    valid_until_ms: int | None = None,
    valid_for_seconds: int = 3600,
    add_random_suffix: bool = False,
    allow_overwrite: bool = False,
) -> str:
    """签发 Vercel Blob 客户端上传令牌，与 `@vercel/blob` 的 `generateClientTokenFromReadWriteToken` 逐字节一致。

    算法：payload = base64(JSON)；signature = HMAC-SHA256(key=读写令牌, msg=payload) 的 hex；
    token = `vercel_blob_client_<storeId>_` + base64(signature + "." + payload)。
    浏览器用它直接 PUT 到 blob.vercel-storage.com，文件不经过函数（避开 4.5 MB 请求体上限）。
    """
    import base64
    import hashlib
    import hmac
    import json
    import time

    token = blob_read_write_token()
    if not token:
        raise StorageUnavailableError("Blob read-write token is not configured")
    store_id = blob_store_id_from_token(token)
    if not store_id:
        raise StorageUnavailableError("Blob read-write token has an invalid format")
    payload: dict[str, Any] = {"pathname": pathname, "addRandomSuffix": add_random_suffix, "allowOverwrite": allow_overwrite}
    if allowed_content_types:
        payload["allowedContentTypes"] = list(allowed_content_types)
    if maximum_size_in_bytes:
        payload["maximumSizeInBytes"] = int(maximum_size_in_bytes)
    payload["validUntil"] = int(valid_until_ms) if valid_until_ms else int(time.time() * 1000) + valid_for_seconds * 1000
    payload_b64 = base64.b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).decode("ascii")
    signature = hmac.new(token.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"vercel_blob_client_{store_id}_" + base64.b64encode(f"{signature}.{payload_b64}".encode("utf-8")).decode("ascii")
