from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from sqlalchemy import select

from app.models.studio import (
    AssetQualityLevel,
    Actor,
    ActorImage,
    AssetViewAngle,
    Character,
    Costume,
    CostumeImage,
    Project,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    PromptCategory,
    Prop,
    PropImage,
    Scene,
    SceneImage,
)
from app.services.common import entity_not_found
from app.services.studio.generation.shared.types import GenerationBaseDraft
from app.services.studio.image_task_references import (
    pick_front_ref_file_id,
    pick_ordered_ref_file_ids,
)
from app.services.studio.image_task_validation import (
    validate_actor_image,
    validate_asset_image_and_relation_type,
    validate_character_image,
)
from app.services.studio.image_tasks import (
    asset_prompt_category,
    build_prompt_with_template,
    is_front_view,
    map_view_angle_for_prompt,
)
from app.services.studio.style_presets import resolve_style_text


class AssetImageBaseDraft(GenerationBaseDraft):
    """资产图片生成的基础真值。"""

    kind: str = "asset_image"
    entity_type: str
    entity_id: str
    image_id: int | None
    relation_type: str
    relation_entity_id: str
    prompt: str
    default_images: list[str]


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


_ASSET_LINK_MODELS: dict[str, tuple[Any, str]] = {
    "scene": (ProjectSceneLink, "scene_id"),
    "prop": (ProjectPropLink, "prop_id"),
    "costume": (ProjectCostumeLink, "costume_id"),
}


async def _project_style_text(db, *, project_id: str | None) -> str | None:
    """按项目 ID 取作品的画面风格文字（预设提示词 + 自定义补充）；无项目或项目无预设时返回 None，让调用方回退实体自身的 style。"""
    if not project_id:
        return None
    project = await db.get(Project, project_id)
    if project is None or (not project.style_preset and not (project.style_prompt or "").strip()):
        return None
    return resolve_style_text(project)


async def _asset_project_style_text(db, *, asset_type: str, asset_id: str) -> str | None:
    """场景 / 道具 / 服装没有 project_id 列，经项目关联表找到首个所属作品后取其风格文字。"""
    spec = _ASSET_LINK_MODELS.get(asset_type)
    if spec is None:
        return None
    link_model, id_field = spec
    project_id = (
        await db.execute(
            select(link_model.project_id).where(getattr(link_model, id_field) == asset_id).order_by(link_model.id.asc()).limit(1)
        )
    ).scalar_one_or_none()
    return await _project_style_text(db, project_id=project_id)


async def _build_asset_prompt(
    db,
    *,
    relation_type: str,
    name: str,
    description: str,
    tags: list[str] | None,
    visual_style: Any,
    style: Any,
    image_row: Any,
    style_text: str | None = None,
) -> str:
    """资产图片提示词：`style_text`（作品预设风格）优先于实体自身的粗分桶 `style`。"""
    category = asset_prompt_category(
        relation_type=relation_type,
        is_front_view=is_front_view(image_row.view_angle),
    )
    return await build_prompt_with_template(
        db,
        category=category,
        variables={
            "name": name,
            "description": description,
            "tags": ", ".join(tags or []),
            "visual_style": _enum_value(visual_style),
            "style": style_text or _enum_value(style),
            "view_angle": map_view_angle_for_prompt(image_row.view_angle),
            "quality_level": image_row.quality_level,
            "format": image_row.format,
        },
        fallback_prompt=description,
        not_found_msg=f"{relation_type}.description is empty",
    )


async def _resolve_front_ref(
    db,
    *,
    image_model,
    parent_field_name: str,
    parent_id: str,
    preferred_quality_level: str | None,
) -> list[str]:
    file_id = await pick_front_ref_file_id(
        db,
        image_model=image_model,
        parent_field_name=parent_field_name,
        parent_id=parent_id,
        preferred_quality_level=preferred_quality_level,
    )
    return [file_id] if file_id else []


async def build_actor_image_base_draft(
    db,
    *,
    actor_id: str,
    image_id: int | None,
) -> AssetImageBaseDraft:
    actor = await db.get(Actor, actor_id)
    if actor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Actor"))
    image_row = await validate_actor_image(db, actor_id=actor_id, image_id=image_id)
    prompt = await _build_asset_prompt(
        db,
        relation_type="actor_image",
        name=actor.name,
        description=actor.description,
        tags=actor.tags,
        visual_style=actor.visual_style,
        style=actor.style,
        image_row=image_row,
    )
    refs = []
    if not is_front_view(image_row.view_angle):
        refs = await _resolve_front_ref(
            db,
            image_model=ActorImage,
            parent_field_name="actor_id",
            parent_id=actor_id,
            preferred_quality_level=image_row.quality_level,
        )
    return AssetImageBaseDraft(
        entity_type="actor",
        entity_id=actor_id,
        image_id=image_row.id,
        relation_type="actor_image",
        relation_entity_id=str(image_row.id),
        prompt=prompt,
        default_images=refs,
    )


async def build_asset_image_base_draft(
    db,
    *,
    asset_type: str,
    asset_id: str,
    image_id: int | None,
) -> AssetImageBaseDraft:
    relation_entity_id, relation_type = await validate_asset_image_and_relation_type(
        db,
        asset_type=asset_type,
        asset_id=asset_id,
        image_id=image_id,
    )
    asset_type_norm = asset_type.strip().lower()
    refs: list[str] = []
    if asset_type_norm == "prop":
        asset = await db.get(Prop, asset_id)
        image_row = await db.get(PropImage, relation_entity_id)
        image_model = PropImage
        parent_field_name = "prop_id"
    elif asset_type_norm == "scene":
        asset = await db.get(Scene, asset_id)
        image_row = await db.get(SceneImage, relation_entity_id)
        image_model = SceneImage
        parent_field_name = "scene_id"
    else:
        asset = await db.get(Costume, asset_id)
        image_row = await db.get(CostumeImage, relation_entity_id)
        image_model = CostumeImage
        parent_field_name = "costume_id"
    if asset is None or image_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("AssetImage"))
    prompt = await _build_asset_prompt(
        db,
        relation_type=relation_type,
        name=asset.name,
        description=asset.description,
        tags=asset.tags,
        visual_style=asset.visual_style,
        style=asset.style,
        image_row=image_row,
        style_text=await _asset_project_style_text(db, asset_type=asset_type_norm, asset_id=asset_id),
    )
    if not is_front_view(image_row.view_angle):
        refs = await _resolve_front_ref(
            db,
            image_model=image_model,
            parent_field_name=parent_field_name,
            parent_id=asset_id,
            preferred_quality_level=image_row.quality_level,
        )
    return AssetImageBaseDraft(
        entity_type=asset_type.strip().lower(),
        entity_id=asset_id,
        image_id=relation_entity_id,
        relation_type=relation_type,
        relation_entity_id=str(relation_entity_id),
        prompt=prompt,
        default_images=refs,
    )


async def build_character_image_base_draft(
    db,
    *,
    character_id: str,
    image_id: int | None,
) -> AssetImageBaseDraft:
    character = await db.get(Character, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Character"))
    # image_id 为空时按「角色级」生成：不要求预先存在 CharacterImage 槽位（CharacterImage.file_id 非空，
    # 无法先建空槽位），任务以 relation_type="character" 落库，执行器会在生成完成后创建首张正面形象图。
    image_row = await validate_character_image(db, character_id=character_id, image_id=image_id) if image_id is not None else None
    view_angle = image_row.view_angle if image_row is not None else AssetViewAngle.front
    quality_level = image_row.quality_level if image_row is not None else AssetQualityLevel.low
    image_format = (image_row.format if image_row is not None else None) or "png"
    project_style_text = await _project_style_text(db, project_id=getattr(character, "project_id", None))
    prompt = await build_prompt_with_template(
        db,
        category=PromptCategory.combined,
        variables={
            "name": character.name,
            "description": character.description,
            "visual_style": _enum_value(character.visual_style),
            "style": project_style_text or _enum_value(character.style),
            "view_angle": map_view_angle_for_prompt(view_angle),
            "quality_level": quality_level,
            "format": image_format,
        },
        fallback_prompt=character.description,
        not_found_msg="Character.description is empty",
    )
    refs: list[str] = []
    default_view_angles: tuple[AssetViewAngle, ...] = (
        AssetViewAngle.front,
        AssetViewAngle.left,
        AssetViewAngle.right,
        AssetViewAngle.back,
    )
    if character.actor_id:
        refs.extend(
            await pick_ordered_ref_file_ids(
                db,
                image_model=ActorImage,
                parent_field_name="actor_id",
                parent_id=character.actor_id,
                view_angles=default_view_angles,
            )
        )
    if character.costume_id:
        refs.extend(
            await pick_ordered_ref_file_ids(
                db,
                image_model=CostumeImage,
                parent_field_name="costume_id",
                parent_id=character.costume_id,
                view_angles=default_view_angles,
            )
        )
    return AssetImageBaseDraft(
        entity_type="character",
        entity_id=character_id,
        image_id=image_row.id if image_row is not None else None,
        relation_type="character_image" if image_row is not None else "character",
        relation_entity_id=str(image_row.id) if image_row is not None else character_id,
        prompt=prompt,
        default_images=refs,
    )
