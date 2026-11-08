from __future__ import annotations

import base64
import mimetypes
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import (
    VideoGenerationInput,
    VideoGenerationResult,
)
from app.core.db import async_session_maker
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import TaskStatus
from app.core.tasks import VideoGenerationTask
from app.models.llm import Model, ModelCategoryKey, ModelSettings
from app.models.studio import FileItem, Shot, ShotDetail, ShotFrameType
from app.models.task_links import GenerationTaskLink
from app.models.types import FileUsageKind
from app.services.common import entity_not_found
from app.services.llm.provider_resolver import resolve_provider_config_by_model
from app.services.studio.file_usages import sync_usage_from_shot_context
from app.services.studio.generation.video import (
    REFERENCE_MODE,
    REQUIRED_FRAMES_BY_MODE,
    build_video_base_draft,
    build_video_context,
    build_video_submission_payload,
    validate_images_count,
)
from app.services.studio.shot_status import recompute_shot_status
from app.services.worker.async_task_support import cancel_if_requested_async
from app.services.worker.task_logging import log_task_event, log_task_failure
from app.utils.files import create_file_from_url_or_b64


async def validate_shot_and_duration(db: AsyncSession, shot_id: str) -> ShotDetail:
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail=entity_not_found("Shot"))
    shot_detail = await db.get(ShotDetail, shot_id)
    if shot_detail is None:
        raise HTTPException(status_code=404, detail=entity_not_found("ShotDetail"))
    if shot_detail.duration is None or shot_detail.duration <= 0:
        raise HTTPException(status_code=400, detail="Shot duration is not configured; please set shot duration first")
    return shot_detail


async def file_id_to_data_url(db: AsyncSession, *, file_id: str) -> str:
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None or not file_obj.storage_key:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")
    try:
        content = await storage.download_file(key=file_obj.storage_key)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}") from None
    if not content:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")

    content_type: str | None = None
    try:
        info = await storage.get_file_info(key=file_obj.storage_key)
        content_type = (info.content_type or "").strip().lower() or None
    except Exception:
        content_type = None
    if not content_type:
        guessed_type, _ = mimetypes.guess_type(file_obj.storage_key)
        content_type = (guessed_type or "").strip().lower() or None
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")

    image_format = content_type.split("/", 1)[1].split(";", 1)[0].strip().lower() or "png"
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/{image_format};base64,{encoded}"


async def file_id_to_image_url(db: AsyncSession, *, file_id: str) -> str:
    """参考图取值：对象存储公网地址优先（方舟直接拉取，不占请求体），没有公网地址时退回 data URL。"""
    file_obj = await db.get(FileItem, file_id)
    thumbnail = str(getattr(file_obj, "thumbnail", "") or "").strip() if file_obj is not None else ""
    if thumbnail.startswith("http://") or thumbnail.startswith("https://"):
        return thumbnail
    return await file_id_to_data_url(db, file_id=file_id)


async def file_id_to_audio_url(db: AsyncSession, *, file_id: str) -> str:
    """配音 / 配乐参考：必须是音频文件且有对象存储公网地址（方舟按 URL 拉取，不支持内联）。"""
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None:
        raise HTTPException(status_code=400, detail=f"Invalid audio file_id: {file_id}")
    if str(getattr(file_obj.type, "value", file_obj.type) or "") != "audio":
        raise HTTPException(status_code=400, detail=f"File is not audio: {file_id}")
    url = str(file_obj.thumbnail or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Audio reference needs a public URL; re-upload the audio file")
    return url


async def preview_prompt_and_images(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    prompt: str | None,
    images: list[str] | None = None,
    reference_labels: list[str] | None = None,
    audio_file_id: str | None = None,
) -> tuple[str, list[str], dict | None, list[str]]:
    """渲染最终提示词，并返回参考图 file_id 列表、提示词上下文包与 reference 模式的 [Image n] 说明。"""
    await validate_shot_and_duration(db, shot_id)
    base = build_video_base_draft(shot_id=shot_id, prompt=prompt)
    context = await build_video_context(
        db,
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=images,
        reference_labels=reference_labels,
        audio_file_id=audio_file_id,
    )
    submission = await build_video_submission_payload(db, base=base, context=context)
    if not submission.prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    prompt_preview_payload = submission.extra.get("prompt_preview")
    pack = prompt_preview_payload.get("pack") if isinstance(prompt_preview_payload, dict) else None
    return submission.prompt, submission.images, pack if isinstance(pack, dict) else None, list(context.reference_labels)


async def resolve_default_video_model(db: AsyncSession) -> Model:
    settings_row = await db.get(ModelSettings, 1)
    model_id = settings_row.default_video_model_id if settings_row else None
    if not model_id:
        raise HTTPException(
            status_code=503,
            detail="No default video model configured; please set ModelSettings.default_video_model_id first",
        )
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=503, detail=f"Configured default video model not found: {model_id}")
    if model.category != ModelCategoryKey.video:
        raise HTTPException(
            status_code=503,
            detail=f"Configured default video model is not video category: {model_id} (category={model.category})",
        )
    return model


async def load_provider_config_by_model(db: AsyncSession, model: Model) -> ProviderConfig:
    resolved = await resolve_provider_config_by_model(db, model=model)
    return ProviderConfig(
        provider=resolved.provider_key,  # type: ignore[arg-type]
        api_key=resolved.api_key,
        base_url=resolved.base_url,
    )


def _normalize_optional_text(value: str | None) -> str | None:
    """归一化可选文本参数：空字符串视为未设置。"""
    normalized = (value or "").strip()
    return normalized or None


async def resolve_effective_video_options(
    requested_ratio: str | None,
) -> str:
    """解析视频比例：请求参数为唯一主参数。"""
    req_ratio = _normalize_optional_text(requested_ratio)
    if not req_ratio:
        raise HTTPException(status_code=400, detail="ratio is required")
    return req_ratio


async def build_run_args(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    prompt: str | None,
    images: list[str],
    ratio: str | None,
    reference_labels: list[str] | None = None,
    audio_file_id: str | None = None,
) -> dict:
    """组装视频任务的运行参数：帧模式把帧图转 data URL；全能参考模式把参考图按公网 URL 透传；音频参考只接受公网 URL。"""
    model = await resolve_default_video_model(db)
    provider_cfg = await load_provider_config_by_model(db, model)
    shot_detail = await validate_shot_and_duration(db, shot_id)
    resolved_ratio = await resolve_effective_video_options(requested_ratio=ratio)
    base = build_video_base_draft(shot_id=shot_id, prompt=prompt)
    context = await build_video_context(
        db,
        shot_id=shot_id,
        reference_mode=reference_mode,
        images=images,
        reference_labels=reference_labels,
        audio_file_id=audio_file_id,
    )
    submission = await build_video_submission_payload(db, base=base, context=context)
    validate_images_count(reference_mode, submission.images)
    reference_audio = await file_id_to_audio_url(db, file_id=context.audio_file_id) if context.audio_file_id else None

    final_prompt = submission.prompt.strip()
    if not final_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    frame_map: dict[ShotFrameType, str] = {}
    reference_images: list[str] = []
    if reference_mode == REFERENCE_MODE:
        reference_images = [await file_id_to_image_url(db, file_id=file_id) for file_id in submission.images]
    else:
        required_frames = tuple(ShotFrameType(item) for item in REQUIRED_FRAMES_BY_MODE[reference_mode])
        frame_data_urls = [await file_id_to_data_url(db, file_id=file_id) for file_id in submission.images]
        frame_map = {ft: frame_data_urls[i] for i, ft in enumerate(required_frames)}

    run_args = {
        "shot_id": shot_id,
        "provider": provider_cfg.provider,
        "api_key": provider_cfg.api_key,
        "base_url": provider_cfg.base_url,
        "input": {
            "prompt": final_prompt,
            "first_frame_base64": frame_map.get(ShotFrameType.first),
            "last_frame_base64": frame_map.get(ShotFrameType.last),
            "key_frame_base64": frame_map.get(ShotFrameType.key),
            "reference_images": reference_images,
            "reference_audio": reference_audio,
            "model": model.name,
            "ratio": resolved_ratio,
            "seconds": shot_detail.duration,
        },
    }
    prompt_preview_payload = submission.extra.get("prompt_preview")
    if isinstance(prompt_preview_payload, dict):
        run_args["prompt_preview"] = prompt_preview_payload
    return run_args


async def persist_generated_video_to_shot(
    session: AsyncSession,
    *,
    task_id: str,
    shot_id: str,
    result: VideoGenerationResult,
    provider: str,
    api_key: str,
) -> FileItem:
    url = (result.url or "").strip()
    if not url:
        raise RuntimeError("Video generation result has no download url")

    url_headers: dict[str, str] | None = None
    if provider == "openai":
        url_headers = {"Authorization": f"Bearer {api_key}"}

    file_obj = await create_file_from_url_or_b64(
        session,
        url=url,
        name=f"shot-{shot_id}-video",
        prefix=f"generated-videos/shots/{shot_id}",
        url_request_headers=url_headers,
        httpx_timeout=600.0,
    )

    link_stmt = (
        select(GenerationTaskLink)
        .where(
            GenerationTaskLink.task_id == task_id,
            GenerationTaskLink.resource_type == "video",
            GenerationTaskLink.relation_type == "video",
            GenerationTaskLink.relation_entity_id == shot_id,
        )
        .limit(1)
    )
    link_row = (await session.execute(link_stmt)).scalars().first()
    if link_row is not None:
        link_row.file_id = file_obj.id

    shot = await session.get(Shot, shot_id)
    if shot is not None:
        shot.generated_video_file_id = file_obj.id

    await sync_usage_from_shot_context(
        session,
        file_id=file_obj.id,
        shot_id=shot_id,
        usage_kind=FileUsageKind.generated_video,
        source_ref=f"shot:{shot_id}:generated_video",
    )

    return file_obj


# 方舟输入审核拒绝某张图时的错误：`InputImageSensitiveContentDetected.PrivacyInformation: ... 'content[k]' may contain real person`
_REJECTED_INPUT_IMAGE_RE = re.compile(r"InputImageSensitiveContentDetected\.\w+.*?'content\[(\d+)\]'", re.S)
_IMAGE_TAG_RE = re.compile(r"\[Image (\d+)\]")
_FRAME_FIELDS = ("first_frame_base64", "last_frame_base64", "key_frame_base64")
# 最多自动去掉几张被拒的图再重试（每次被拒都在生成前发生，不计费）
MAX_REJECTED_IMAGE_RETRIES = 4


def content_layout(input_dict: dict) -> list[str]:
    """按方舟请求 content 数组的真实顺序列出每一项的含义，用来把错误里的 `content[k]` 对回我们的输入。

    顺序与 `volcengine.video_payload.build_content` 一致：text → first_frame → last_frame → key_frame →
    reference_images（按序）→ audio；缺省项不占位。
    """
    layout: list[str] = []
    if (input_dict.get("prompt") or "").strip():
        layout.append("text")
    for field, kind in (("first_frame_base64", "first_frame"), ("last_frame_base64", "last_frame"), ("key_frame_base64", "key_frame")):
        if (input_dict.get(field) or "").strip():
            layout.append(kind)
    for index, value in enumerate(input_dict.get("reference_images") or []):
        if str(value or "").strip():
            layout.append(f"reference:{index}")
    if (input_dict.get("reference_audio") or "").strip():
        layout.append("audio")
    return layout


def renumber_image_references(prompt: str, *, dropped: int) -> tuple[str, str]:
    """去掉提示词里第 `dropped` 张图（1 起）的 `[Image n]` 说明行，并把后面的编号前移一位。

    返回 (新提示词, 被去掉那行的说明文字)。参考块之外的 `[Image n]` 引用同样重编号；对被去掉那张图的
    其它引用直接删掉标签，避免模型去找一张不存在的图。
    """
    label = ""
    kept: list[str] = []
    for line in (prompt or "").splitlines():
        match = _IMAGE_TAG_RE.match(line.strip())
        if match and int(match.group(1)) == dropped:
            label = line.strip()[match.end():].strip()
            continue
        kept.append(line)

    def _shift(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if n == dropped:
            return ""
        return f"[Image {n - 1}]" if n > dropped else match.group(0)

    text = "\n".join(kept)
    text = _IMAGE_TAG_RE.sub(_shift, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip(), label


def drop_rejected_input_image(input_dict: dict, error: str) -> tuple[dict, dict] | None:
    """若 `error` 是方舟「输入图含真人」拒绝，返回去掉那张图后的新输入与记录；否则返回 None。

    为什么存在：Seedance 2.x 只信任同账号 Seedream 5.0 文生图的人脸原图，关键帧（图生图）、用户上传的照片等
    一旦含有清晰人脸就会整条请求被拒。拒绝发生在生成之前、不计费，所以最划算的做法是把被点名的那张图
    去掉后立刻重试，保留其余（受信的）形象图，而不是直接失败让用户手动改成纯文字。
    - 被拒的是全能参考里的某张图：删掉它并重编号提示词里的 [Image n]；
    - 被拒的是首帧 / 尾帧 / 关键帧：去掉所有帧图，退回「纯文字 + 剩余参考图」；
    - 去掉后既没有提示词也没有任何参考时返回 None（无法再重试）。
    """
    match = _REJECTED_INPUT_IMAGE_RE.search(error or "")
    if not match:
        return None
    index = int(match.group(1))
    layout = content_layout(input_dict)
    if index < 0 or index >= len(layout):
        return None
    kind = layout[index]
    new_input = dict(input_dict)
    new_input["reference_images"] = list(input_dict.get("reference_images") or [])
    record: dict = {"content_index": index, "kind": kind, "error": (error or "")[:300]}
    if kind.startswith("reference:"):
        ref_index = int(kind.split(":", 1)[1])
        record["image"] = str(new_input["reference_images"][ref_index])[:300]
        del new_input["reference_images"][ref_index]
        new_input["prompt"], record["label"] = renumber_image_references(new_input.get("prompt") or "", dropped=ref_index + 1)
    elif kind in ("first_frame", "last_frame", "key_frame"):
        for field in _FRAME_FIELDS:
            new_input[field] = None
    else:
        return None
    has_prompt = bool((new_input.get("prompt") or "").strip())
    has_reference = bool(new_input["reference_images"]) or any((new_input.get(f) or "").strip() for f in _FRAME_FIELDS) or bool(
        (new_input.get("reference_audio") or "").strip()
    )
    if not has_prompt and not has_reference:
        return None
    return new_input, record


async def _run_provider_with_rejection_retries(
    *,
    task_id: str,
    provider: str,
    api_key: str,
    base_url: str | None,
    input_dict: dict,
) -> tuple[VideoGenerationResult, list[dict]]:
    """调用供应商生成视频；输入图被方舟人脸审核拒绝时自动去掉那张图重试，返回 (结果, 被去掉的图记录)。"""
    dropped: list[dict] = []
    current = dict(input_dict)
    for attempt in range(MAX_REJECTED_IMAGE_RETRIES + 1):
        task = VideoGenerationTask(
            provider_config=ProviderConfig(
                provider=provider,  # type: ignore[arg-type]
                api_key=api_key,
                base_url=base_url,
            ),
            input_=VideoGenerationInput.model_validate(current),
        )
        await task.run()
        result = await task.get_result()
        if result is not None:
            return result, dropped
        status_dict = await task.status()
        detailed_error = str(status_dict.get("error") or "") if isinstance(status_dict, dict) else ""
        msg = detailed_error or "Video generation task returned no result"
        adjusted = drop_rejected_input_image(current, msg) if attempt < MAX_REJECTED_IMAGE_RETRIES else None
        if adjusted is None:
            raise RuntimeError(msg)
        current, record = adjusted
        dropped.append(record)
        log_task_event("video_generation", task_id, "retry_without_rejected_image", kind=record["kind"], content_index=record["content_index"])
    raise RuntimeError("Video generation exhausted rejected-image retries")


async def run_video_generation_task(
    task_id: str,
    run_args: dict,
) -> None:
    async with async_session_maker() as session:
        try:
            store = SqlAlchemyTaskStore(session)
            await store.set_status(task_id, TaskStatus.running)
            await store.set_progress(task_id, 10)
            await session.commit()
            log_task_event("video_generation", task_id, "running")
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("video_generation", task_id, "cancelled", stage="before_execute")
                return

            provider = str(run_args.get("provider") or "")
            api_key = str(run_args.get("api_key") or "")
            base_url = run_args.get("base_url")
            input_dict = dict(run_args.get("input") or {})

            result, dropped_references = await _run_provider_with_rejection_retries(
                task_id=task_id,
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                input_dict=input_dict,
            )
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("video_generation", task_id, "cancelled", stage="after_execute")
                return

            shot_id = str(run_args.get("shot_id") or "")
            if not shot_id:
                raise RuntimeError("run_args missing shot_id for video persistence")

            file_obj = await persist_generated_video_to_shot(
                session,
                task_id=task_id,
                shot_id=shot_id,
                result=result,
                provider=provider,
                api_key=api_key,
            )

            result_payload = result.model_dump()
            result_payload["file_id"] = file_obj.id
            if dropped_references:
                # 记录被方舟人脸审核拒绝、已自动去掉的参考图，供界面提示「这一镜没有用到关键帧」
                result_payload["dropped_references"] = dropped_references
            await store.set_result(task_id, result_payload)
            if await cancel_if_requested_async(store=store, task_id=task_id, session=session):
                log_task_event("video_generation", task_id, "cancelled", stage="after_persist")
                return
            await store.set_progress(task_id, 100)
            await store.set_status(task_id, TaskStatus.succeeded)
            await recompute_shot_status(session, shot_id=shot_id)
            await session.commit()
            log_task_event("video_generation", task_id, "succeeded")
        except Exception as exc:
            await session.rollback()
            async with async_session_maker() as s2:
                store = SqlAlchemyTaskStore(s2)
                await store.set_error(task_id, str(exc))
                await store.set_status(task_id, TaskStatus.failed)
                shot_id = str(run_args.get("shot_id") or "")
                if shot_id:
                    await recompute_shot_status(s2, shot_id=shot_id)
                await s2.commit()
            log_task_failure("video_generation", task_id, str(exc))
