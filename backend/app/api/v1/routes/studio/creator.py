"""创作模式（Creator Mode）编辑接口：镜头 ↔ 实体关联、手动建档、上传图挂为形象 / 关键帧。

api 层只负责收参、错误映射与提交事务；规则全部在 `app.services.studio.creator_flow`。
聚合读取（creator-board / auto-confirm / overview）仍挂在 chapters / projects 路由下。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.common import (
    ApiResponse,
    created_response,
    empty_response,
    success_response,
)
from app.schemas.studio.creator import (
    AttachedImageRead,
    AttachedVideoRead,
    CreatorEntityCreate,
    CreatorEntityCreatedRead,
    EntityShotsWrite,
    FileAttachRequest,
    ShotEntityLinksWrite,
)
from app.services.studio.creator_flow import (
    CreatorInputError,
    attach_entity_image,
    attach_shot_keyframe,
    attach_shot_video,
    create_chapter_entity,
    set_entity_shots,
    set_shot_entity_links,
)

router = APIRouter()


def _http_error(exc: ValueError) -> HTTPException:
    """服务层 ValueError → HTTP：输入不合法 400，资源不存在 404。"""
    code = status.HTTP_400_BAD_REQUEST if isinstance(exc, CreatorInputError) else status.HTTP_404_NOT_FOUND
    return HTTPException(status_code=code, detail=str(exc))


@router.put(
    "/shots/{shot_id}/links",
    response_model=ApiResponse[None],
    summary="创作模式：整体替换镜头「画面里会用到」的角色 / 场景 / 道具 / 服装",
)
async def set_shot_links_api(
    shot_id: str,
    body: ShotEntityLinksWrite,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """为 None 的类型保持不变；移除的实体会把同名提取候选标记为 ignored，避免被自动确认挂回。"""
    try:
        for entity_type, ids in (
            ("character", body.character_ids),
            ("scene", body.scene_ids),
            ("prop", body.prop_ids),
            ("costume", body.costume_ids),
        ):
            if ids is not None:
                await set_shot_entity_links(db, shot_id=shot_id, entity_type=entity_type, entity_ids=ids)
    except ValueError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return empty_response()


@router.put(
    "/chapters/{chapter_id}/entities/{entity_type}/{entity_id}/shots",
    response_model=ApiResponse[EntityShotsWrite],
    summary="创作模式：设置实体在本章节内出现的镜头集合",
)
async def set_entity_shots_api(
    chapter_id: str,
    entity_type: str,
    entity_id: str,
    body: EntityShotsWrite,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[EntityShotsWrite]:
    try:
        shot_ids = await set_entity_shots(db, chapter_id=chapter_id, entity_type=entity_type, entity_id=entity_id, shot_ids=body.shot_ids)
    except ValueError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return success_response(EntityShotsWrite(shot_ids=shot_ids))


@router.post(
    "/chapters/{chapter_id}/entities",
    response_model=ApiResponse[CreatorEntityCreatedRead],
    status_code=status.HTTP_201_CREATED,
    summary="创作模式：手动新增角色 / 场景 / 道具 / 服装并挂到镜头",
)
async def create_chapter_entity_api(
    chapter_id: str,
    body: CreatorEntityCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CreatorEntityCreatedRead]:
    try:
        entity_id, reused = await create_chapter_entity(
            db, chapter_id=chapter_id, entity_type=body.type, name=body.name, description=body.description, shot_ids=body.shot_ids
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return created_response(CreatorEntityCreatedRead(type=body.type, id=entity_id, reused=reused))


@router.post(
    "/entities/{entity_type}/{entity_id}/image-from-file",
    response_model=ApiResponse[AttachedImageRead],
    summary="创作模式：把上传的图片设为角色形象 / 场景道具参考图",
)
async def attach_entity_image_api(
    entity_type: str,
    entity_id: str,
    body: FileAttachRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AttachedImageRead]:
    try:
        image_id = await attach_entity_image(db, entity_type=entity_type, entity_id=entity_id, file_id=body.file_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return success_response(AttachedImageRead(image_id=image_id, file_id=body.file_id))


@router.post(
    "/shots/{shot_id}/keyframe-from-file",
    response_model=ApiResponse[AttachedImageRead],
    summary="创作模式：把上传的图片设为镜头关键帧（首帧）",
)
async def attach_shot_keyframe_api(
    shot_id: str,
    body: FileAttachRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AttachedImageRead]:
    try:
        image_id = await attach_shot_keyframe(db, shot_id=shot_id, file_id=body.file_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return success_response(AttachedImageRead(image_id=image_id, file_id=body.file_id))


@router.post(
    "/shots/{shot_id}/video-from-file",
    response_model=ApiResponse[AttachedVideoRead],
    summary="创作模式：把上传的视频设为镜头成片",
)
async def attach_shot_video_api(
    shot_id: str,
    body: FileAttachRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AttachedVideoRead]:
    try:
        file_id = await attach_shot_video(db, shot_id=shot_id, file_id=body.file_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return success_response(AttachedVideoRead(shot_id=shot_id, file_id=file_id))
