"""S3 兼容存储的 Cloudflare R2 适配：客户端参数、预签名 PUT、建桶 / CORS、S3 模式浏览器直传与登记。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from botocore.stub import Stubber
from fastapi import HTTPException

from app.core import storage
from app.services.studio import direct_upload
from tests.test_creator_flow import _build_session

R2_ENDPOINT = "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"


def _configure_r2(monkeypatch: pytest.MonkeyPatch, *, public_base_url: str | None = "https://pub-abc.r2.dev") -> None:
    """把 settings 切到一组假的 R2 配置（密钥是假的，预签名是本地 HMAC，不发请求）。"""
    monkeypatch.setattr(storage.settings, "s3_endpoint_url", R2_ENDPOINT)
    monkeypatch.setattr(storage.settings, "s3_region_name", None)
    monkeypatch.setattr(storage.settings, "s3_access_key_id", "AKIDTEST")
    monkeypatch.setattr(storage.settings, "s3_secret_access_key", "secret-test")
    monkeypatch.setattr(storage.settings, "s3_bucket_name", "ai-filming-media")
    monkeypatch.setattr(storage.settings, "s3_base_path", "")
    monkeypatch.setattr(storage.settings, "s3_public_base_url", public_base_url)
    monkeypatch.setattr(storage.settings, "s3_addressing_style", None)
    monkeypatch.setattr(storage.settings, "blob_read_write_token", None)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)


def test_r2_client_uses_auto_region_path_style_and_no_default_checksums(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    assert storage.is_cloudflare_r2()
    assert storage.storage_backend() == "s3"
    client = storage._build_s3_client()
    assert client.meta.region_name == "auto"
    assert client.meta.config.s3["addressing_style"] == "path"
    assert client.meta.config.request_checksum_calculation == "when_required"
    assert client.meta.config.response_checksum_validation == "when_required"
    # 非 R2 端点保持原行为（virtual，region 按配置）
    monkeypatch.setattr(storage.settings, "s3_endpoint_url", "https://s3.ap-southeast-1.amazonaws.com")
    monkeypatch.setattr(storage.settings, "s3_region_name", "ap-southeast-1")
    assert not storage.is_cloudflare_r2()
    other = storage._build_s3_client()
    assert other.meta.region_name == "ap-southeast-1"
    assert other.meta.config.s3["addressing_style"] == "virtual"
    monkeypatch.setattr(storage.settings, "s3_addressing_style", "path")
    assert storage._build_s3_client().meta.config.s3["addressing_style"] == "path"


def test_presigned_put_url_targets_bucket_key_and_signs_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    url = storage.generate_presigned_put_url(key="uploads/abc/我的-视频.mp4", content_type="video/mp4", expires_in=600)
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}" == R2_ENDPOINT
    assert parsed.path == "/ai-filming-media/uploads/abc/%E6%88%91%E7%9A%84-%E8%A7%86%E9%A2%91.mp4"
    query = parse_qs(parsed.query)
    assert query["X-Amz-Expires"] == ["600"]
    assert "X-Amz-Signature" in query
    assert "content-type" in query["X-Amz-SignedHeaders"][0]
    assert "/auto/s3/aws4_request" in query["X-Amz-Credential"][0]


def test_public_url_quotes_key_and_prefers_public_base(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    assert storage.public_url_for_key("uploads/x/我的 视频.mp4") == "https://pub-abc.r2.dev/uploads/x/%E6%88%91%E7%9A%84%20%E8%A7%86%E9%A2%91.mp4"
    monkeypatch.setattr(storage.settings, "s3_public_base_url", None)
    assert storage.public_url_for_key("a/b.png") == f"{R2_ENDPOINT}/ai-filming-media/a/b.png"
    monkeypatch.setattr(storage.settings, "s3_base_path", "jellyfish/prod")
    assert storage.public_url_for_key("a/b.png") == f"{R2_ENDPOINT}/ai-filming-media/jellyfish/prod/a/b.png"


def test_init_storage_creates_r2_bucket_without_location_and_writes_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    client = storage._build_s3_client()
    monkeypatch.setattr(storage, "_build_s3_client", lambda: client)
    with Stubber(client) as stub:
        stub.add_client_error("head_bucket", service_error_code="404", http_status_code=404, expected_params={"Bucket": "ai-filming-media"})
        # R2（region=auto）建桶不能带 CreateBucketConfiguration；expected_params 精确匹配确保没有多余参数
        stub.add_response("create_bucket", {}, expected_params={"Bucket": "ai-filming-media"})
        stub.add_response("head_bucket", {}, expected_params={"Bucket": "ai-filming-media"})
        stub.add_client_error("get_bucket_cors", service_error_code="NoSuchCORSConfiguration", http_status_code=404)
        stub.add_response(
            "put_bucket_cors",
            {},
            expected_params={"Bucket": "ai-filming-media", "CORSConfiguration": {"CORSRules": [storage._CORS_RULE]}},
        )
        assert storage.init_storage() == {"bucket_created": True, "cors": "written"}
        stub.assert_no_pending_responses()

    with Stubber(client) as stub:
        stub.add_response("head_bucket", {}, expected_params={"Bucket": "ai-filming-media"})
        # 控制台里手工配过等价规则 → 不重复写
        stub.add_response(
            "get_bucket_cors",
            {"CORSRules": [{"AllowedOrigins": ["*"], "AllowedMethods": ["GET", "PUT", "HEAD"], "AllowedHeaders": ["*"]}]},
        )
        assert storage.init_storage() == {"bucket_created": False, "cors": "present"}
        stub.assert_no_pending_responses()

    with Stubber(client) as stub:
        stub.add_response("head_bucket", {}, expected_params={"Bucket": "ai-filming-media"})
        # 只有对象读写权限的令牌：桶级操作 AccessDenied → 记录为 error，不抛出
        stub.add_client_error("get_bucket_cors", service_error_code="AccessDenied", http_status_code=403)
        assert storage.init_storage() == {"bucket_created": False, "cors": "error"}


def test_aws_bucket_creation_keeps_location_constraint(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    monkeypatch.setattr(storage.settings, "s3_endpoint_url", "https://s3.ap-southeast-1.amazonaws.com")
    monkeypatch.setattr(storage.settings, "s3_region_name", "ap-southeast-1")
    client = storage._build_s3_client()
    monkeypatch.setattr(storage, "_build_s3_client", lambda: client)
    with Stubber(client) as stub:
        stub.add_client_error("head_bucket", service_error_code="NoSuchBucket", http_status_code=404)
        stub.add_response(
            "create_bucket",
            {},
            expected_params={"Bucket": "ai-filming-media", "CreateBucketConfiguration": {"LocationConstraint": "ap-southeast-1"}},
        )
        stub.add_response("head_bucket", {})
        assert storage.init_storage(configure_cors=False) == {"bucket_created": True, "cors": "skipped"}
        stub.assert_no_pending_responses()


def test_prepare_direct_upload_in_s3_mode_returns_presigned_put(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    assert direct_upload.direct_upload_backend() == "s3"
    prepared = direct_upload.prepare_direct_upload(filename="片段 01.mov", content_type="video/quicktime")
    assert prepared.backend == "s3"
    assert prepared.storage_key.startswith("uploads/") and prepared.storage_key.endswith("/片段-01.mov")
    assert prepared.pathname == prepared.storage_key
    assert prepared.upload_url and prepared.upload_url.startswith(R2_ENDPOINT + "/ai-filming-media/uploads/")
    assert prepared.public_url == storage.public_url_for_key(prepared.storage_key)
    assert prepared.headers == {"Content-Type": "video/quicktime"}
    # 浏览器没给 MIME 或给了白名单外的类型 → 按扩展名推断
    assert direct_upload.prepare_direct_upload(filename="voice.m4a", content_type="").headers == {"Content-Type": "audio/mp4"}
    assert direct_upload.prepare_direct_upload(filename="a.png", content_type="application/x-evil").headers == {"Content-Type": "image/png"}
    with pytest.raises(HTTPException) as info:
        direct_upload.issue_client_token(pathname=prepared.pathname)
    assert info.value.status_code == 409
    # 没有任何直传后端 → 409
    monkeypatch.setattr(storage.settings, "s3_bucket_name", None)
    assert direct_upload.direct_upload_backend() is None
    with pytest.raises(HTTPException) as info:
        direct_upload.prepare_direct_upload(filename="a.mp4")
    assert info.value.status_code == 409 and "direct upload is unavailable" in str(info.value.detail)


@pytest.mark.asyncio
async def test_register_in_s3_mode_requires_public_url_and_existing_object(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    heads: list[str] = []

    async def fake_head(*, key: str) -> storage.StoredFileInfo:
        heads.append(key)
        if key.endswith("missing.mp4"):
            raise RuntimeError("NoSuchKey")
        return storage.StoredFileInfo(key=key, url=storage.public_url_for_key(key), size=12, content_type="video/mp4")

    monkeypatch.setattr(storage, "get_file_info", fake_head)
    db, engine = await _build_session()
    async with db:
        prepared = direct_upload.prepare_direct_upload(filename="clip.mp4", content_type="video/mp4")
        assert prepared.public_url
        with pytest.raises(HTTPException) as info:
            await direct_upload.register_uploaded_file(db, storage_key=prepared.storage_key, url="https://evil.example/" + prepared.pathname, name="clip.mp4")
        assert info.value.status_code == 400 and heads == []
        with pytest.raises(HTTPException) as info:
            await direct_upload.register_uploaded_file(db, storage_key="files/other.mp4", url=prepared.public_url, name="clip.mp4")
        assert info.value.status_code == 400
        item = await direct_upload.register_uploaded_file(db, storage_key=prepared.storage_key, url=prepared.public_url, name="clip.mp4")
        assert item.thumbnail == prepared.public_url and item.storage_key == prepared.storage_key and heads == [prepared.storage_key]
        # 对象不存在（浏览器 PUT 失败却仍登记）→ 400
        missing = direct_upload.prepare_direct_upload(filename="missing.mp4", content_type="video/mp4")
        with pytest.raises(HTTPException) as info:
            await direct_upload.register_uploaded_file(db, storage_key=missing.storage_key, url=missing.public_url or "", name="missing.mp4")
        assert info.value.status_code == 400 and "not found" in str(info.value.detail)
    await engine.dispose()


def test_describe_storage_has_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_r2(monkeypatch)
    info = storage.describe_storage()
    assert info["backend"] == "s3" and info["cloudflare_r2"] is True and info["region"] == "auto"
    assert info["bucket"] == "ai-filming-media" and info["endpoint_host"].endswith(".r2.cloudflarestorage.com")
    assert "secret-test" not in repr(info) and "AKIDTEST" not in repr(info)
