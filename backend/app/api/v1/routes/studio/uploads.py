"""文件浏览器直传路由（Vercel Blob / S3 兼容含 Cloudflare R2）：能力探测、准备、签发凭证、登记结果。

`/client-upload` 实现 `@vercel/blob/client` 的 handleUpload 协议，响应体是协议要求的裸 JSON，不包 ApiResponse。
S3 模式不经过该接口：`/direct-upload/prepare` 直接返回预签名 PUT URL。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.common import ApiResponse, created_response, success_response
from app.schemas.studio import FileRead
from app.services.studio.direct_upload import (
    MAX_DIRECT_UPLOAD_BYTES,
    MAX_SERVER_UPLOAD_BYTES,
    direct_upload_backend,
    issue_client_token,
    prepare_direct_upload,
    register_uploaded_file,
)

router = APIRouter()


class DirectUploadCapabilitiesRead(BaseModel):
    """前端据此决定走直传还是经函数上传。"""

    direct: str | None = Field(None, description="可用的直传后端：vercel_blob（客户端令牌）或 s3（预签名 PUT，含 R2）；None 表示只能经函数上传")
    max_server_upload_bytes: int = Field(..., description="经函数上传的建议大小上限（字节）")
    max_direct_upload_bytes: int = Field(..., description="直传大小上限（字节）")


class DirectUploadPrepareRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str | None = Field(None, max_length=100, description="浏览器给出的 MIME 类型；S3 模式参与预签名，PUT 时必须原样携带")


class DirectUploadPrepareRead(BaseModel):
    backend: str = Field(..., description="本次直传使用的后端：vercel_blob 或 s3")
    storage_key: str = Field(..., description="登记时回传的存储 key")
    pathname: str = Field(..., description="对象路径；Blob 直传时作为 `upload()` 的 pathname")
    upload_url: str | None = Field(None, description="s3：浏览器直接 PUT 的预签名 URL；vercel_blob 为空")
    public_url: str | None = Field(None, description="s3：上传完成后的公网 URL，登记时原样回传；vercel_blob 为空")
    headers: dict[str, str] | None = Field(None, description="s3：PUT 必须携带的请求头（Content-Type）")


class ClientUploadEvent(BaseModel):
    """`@vercel/blob/client` 发来的事件：blob.generate-client-token / blob.upload-completed。"""

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class DirectUploadRegisterRequest(BaseModel):
    storage_key: str
    url: str
    name: str | None = None
    content_type: str | None = None
    size: int | None = None
    project_id: str | None = None
    chapter_id: str | None = None
    shot_id: str | None = None
    usage_kind: str | None = None
    source_ref: str | None = None


@router.get("/direct-upload/capabilities", response_model=ApiResponse[DirectUploadCapabilitiesRead], summary="上传能力探测")
async def direct_upload_capabilities_api() -> ApiResponse[DirectUploadCapabilitiesRead]:
    return success_response(
        DirectUploadCapabilitiesRead(
            direct=direct_upload_backend(),
            max_server_upload_bytes=MAX_SERVER_UPLOAD_BYTES,
            max_direct_upload_bytes=MAX_DIRECT_UPLOAD_BYTES,
        )
    )


@router.post("/direct-upload/prepare", response_model=ApiResponse[DirectUploadPrepareRead], summary="直传准备：生成存储 key / pathname，S3 模式附预签名 PUT URL")
async def direct_upload_prepare_api(body: DirectUploadPrepareRequest) -> ApiResponse[DirectUploadPrepareRead]:
    prepared = prepare_direct_upload(filename=body.filename, content_type=body.content_type)
    return success_response(
        DirectUploadPrepareRead(
            backend=prepared.backend,
            storage_key=prepared.storage_key,
            pathname=prepared.pathname,
            upload_url=prepared.upload_url,
            public_url=prepared.public_url,
            headers=prepared.headers,
        )
    )


@router.post("/client-upload", summary="直传：签发 Vercel Blob 客户端令牌（@vercel/blob handleUpload 协议）")
async def client_upload_api(body: ClientUploadEvent) -> dict[str, Any]:
    if body.type == "blob.generate-client-token":
        pathname = str(body.payload.get("pathname") or "")
        return {"type": body.type, "clientToken": issue_client_token(pathname=pathname)}
    if body.type == "blob.upload-completed":
        # 未开启 onUploadCompleted 回调；若 Blob 仍然回调，确认收到即可，登记由前端显式调用 register 完成。
        return {"response": "ok"}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unsupported event type: {body.type}")


@router.post(
    "/direct-upload/register",
    response_model=ApiResponse[FileRead],
    status_code=status.HTTP_201_CREATED,
    summary="直传完成：登记为文件记录",
)
async def direct_upload_register_api(
    body: DirectUploadRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FileRead]:
    item = await register_uploaded_file(
        db,
        storage_key=body.storage_key,
        url=body.url,
        name=body.name,
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        shot_id=body.shot_id,
        usage_kind=body.usage_kind,
        source_ref=body.source_ref,
    )
    return created_response(FileRead.model_validate(item))
