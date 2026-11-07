from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.studio import ShotFrameImage, ShotFrameType
from app.services.studio.generation.shared.types import GenerationContext
from app.services.studio.shot_assets_overview import get_shot_assets_overview

REQUIRED_FRAMES_BY_MODE: dict[str, tuple[ShotFrameType, ...]] = {
    "first": (ShotFrameType.first,),
    "last": (ShotFrameType.last,),
    "key": (ShotFrameType.key,),
    "first_last": (ShotFrameType.first, ShotFrameType.last),
    "first_last_key": (ShotFrameType.first, ShotFrameType.last, ShotFrameType.key),
    # 全能参考：不要求固定帧，图片数量 1–MAX_REFERENCE_IMAGES，由 resolve_video_reference_images 单独校验
    "reference": (),
    "text_only": (),
}

REFERENCE_MODE = "reference"
MAX_REFERENCE_IMAGES = 9
KEYFRAME_REFERENCE_LABEL = "本镜头关键帧（构图与起始状态）"
_ENTITY_TYPE_LABEL = {"character": "角色", "scene": "场景", "prop": "道具", "costume": "服装"}
_ENTITY_ORDER = {"character": 0, "scene": 1, "prop": 2, "costume": 3}


class ReferenceCandidate(BaseModel):
    """全能参考模式下一张可用参考图：文件、给提示词用的说明、来源类型。"""

    file_id: str
    label: str
    kind: str


def required_image_count(reference_mode: str) -> int:
    return len(REQUIRED_FRAMES_BY_MODE[reference_mode])


def validate_images_count(reference_mode: str, images: list[str]) -> None:
    """帧模式数量必须精确匹配；全能参考模式 1–MAX_REFERENCE_IMAGES 张。"""
    actual = len(images or [])
    if reference_mode == REFERENCE_MODE:
        if actual < 1 or actual > MAX_REFERENCE_IMAGES:
            raise HTTPException(
                status_code=400,
                detail=f"reference_mode=reference requires 1-{MAX_REFERENCE_IMAGES} images, got {actual}",
            )
        return
    expected = required_image_count(reference_mode)
    if actual != expected:
        raise HTTPException(
            status_code=400,
            detail=f"reference_mode={reference_mode} requires exactly {expected} images, got {actual}",
        )


def entity_reference_label(*, entity_type: str, name: str, description: str | None) -> str:
    """提示词里 [Image n] 后面的说明：类型「名称」：设定（截断，避免提示词过长）。"""
    desc = " ".join(str(description or "").split())
    label = f"{_ENTITY_TYPE_LABEL.get(entity_type, entity_type)}「{name}」"
    return f"{label}：{desc[:60]}" if desc else label


async def collect_reference_candidates(db: AsyncSession, *, shot_id: str) -> list[ReferenceCandidate]:
    """按「角色 → 场景 → 道具 → 服装 → 关键帧」收集镜头可用的参考图（只取有形象图的已关联实体）。

    为什么存在：全能参考模式的默认素材集与 [Image n] 说明都从这里来，预览与提交共用同一规则。
    """
    overview = await get_shot_assets_overview(db, shot_id=shot_id)
    linked = [item for item in overview.items if getattr(item, "is_linked", False) and item.file_id]
    linked.sort(key=lambda item: _ENTITY_ORDER.get(str(item.type), 9))
    out: list[ReferenceCandidate] = []
    seen: set[str] = set()
    for item in linked:
        if item.file_id in seen:
            continue
        seen.add(item.file_id)
        out.append(
            ReferenceCandidate(
                file_id=str(item.file_id),
                label=entity_reference_label(entity_type=str(item.type), name=item.name, description=item.description),
                kind=str(item.type),
            )
        )
    frame_stmt = select(ShotFrameImage).where(ShotFrameImage.shot_detail_id == shot_id, ShotFrameImage.frame_type == ShotFrameType.first).limit(1)
    frame = (await db.execute(frame_stmt)).scalars().first()
    if frame is not None and frame.file_id and frame.file_id not in seen:
        out.append(ReferenceCandidate(file_id=str(frame.file_id), label=KEYFRAME_REFERENCE_LABEL, kind="keyframe"))
    return out[:MAX_REFERENCE_IMAGES]


async def resolve_video_reference_images(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    images: list[str] | None = None,
) -> list[str]:
    normalized = [str(item).strip() for item in (images or []) if str(item).strip()]
    if normalized:
        validate_images_count(reference_mode, normalized)
        return normalized

    if reference_mode == REFERENCE_MODE:
        candidates = await collect_reference_candidates(db, shot_id=shot_id)
        if not candidates:
            raise HTTPException(
                status_code=400,
                detail="No reference images available: generate a character portrait or keyframe first, or use text_only",
            )
        return [item.file_id for item in candidates]

    required_frames = REQUIRED_FRAMES_BY_MODE[reference_mode]
    if not required_frames:
        return []

    stmt = select(ShotFrameImage).where(
        ShotFrameImage.shot_detail_id == shot_id,
        ShotFrameImage.frame_type.in_(required_frames),
    )
    rows = (await db.execute(stmt)).scalars().all()
    frame_map = {row.frame_type: row for row in rows}

    missing: list[ShotFrameType] = []
    ordered_images: list[str] = []
    for frame_type in required_frames:
        row = frame_map.get(frame_type)
        if row is None or not row.file_id:
            missing.append(frame_type)
            continue
        ordered_images.append(str(row.file_id))

    if missing:
        missing_name = ",".join(item.value for item in missing)
        raise HTTPException(
            status_code=400,
            detail=f"Required frame image is missing: {missing_name}; please generate it first",
        )
    return ordered_images


async def resolve_reference_labels(
    db: AsyncSession,
    *,
    shot_id: str,
    images: list[str],
    labels: list[str] | None,
) -> list[str]:
    """给 reference 模式的每张图一条说明：优先用调用方传的，否则按文件 ID 从候选里找，再退化为「参考图 n」。"""
    provided = [str(item).strip() for item in (labels or [])]
    if provided and len(provided) == len(images) and all(provided):
        return provided
    by_file = {item.file_id: item.label for item in await collect_reference_candidates(db, shot_id=shot_id)}
    out: list[str] = []
    for index, file_id in enumerate(images):
        given = provided[index] if index < len(provided) else ""
        out.append(given or by_file.get(file_id) or f"参考图 {index + 1}")
    return out


class VideoGenerationContext(GenerationContext):
    """视频生成的动态上下文。"""

    kind: str = "video"
    shot_id: str
    reference_mode: str
    images: list[str]
    reference_labels: list[str] = []
    audio_file_id: str | None = None
    template_id: str | None = None


async def build_video_context(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    images: list[str] | None,
    reference_labels: list[str] | None = None,
    audio_file_id: str | None = None,
    template_id: str | None = None,
) -> VideoGenerationContext:
    resolved_images = await resolve_video_reference_images(
        db,
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=images,
    )
    labels: list[str] = []
    if reference_mode == REFERENCE_MODE:
        labels = await resolve_reference_labels(db, shot_id=shot_id, images=resolved_images, labels=reference_labels)
    return VideoGenerationContext(
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=resolved_images,
        reference_labels=labels,
        audio_file_id=(audio_file_id or "").strip() or None,
        template_id=template_id,
    )
