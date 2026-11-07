from __future__ import annotations

from app.schemas.studio.shots import ShotVideoPromptPackRead, ShotVideoPromptPreviewRead
from app.services.studio.generation.shared.types import GenerationDerivedPreview
from app.services.studio.generation.video.build_base import VideoBaseDraft
from app.services.studio.generation.video.build_context import VideoGenerationContext
from app.services.studio.shot_video_prompt_pack import (
    _fallback_video_prompt,
    _pack_variables,
    _render_template,
    _resolve_video_prompt_template,
    build_shot_video_prompt_pack,
    enrich_rendered_video_prompt,
)


class VideoDerivedPreview(GenerationDerivedPreview):
    """视频生成预览结果。"""

    kind: str = "video"
    shot_id: str
    reference_mode: str
    rendered_prompt: str
    images: list[str]
    pack: ShotVideoPromptPackRead
    template_id: str | None = None
    template_name: str | None = None


REFERENCE_BLOCK_HEADER = "参考素材（[Image n] 与上传顺序一一对应；人物脸型、发型、服装与场景布局必须与参考一致）："
AUDIO_REFERENCE_LINE = "[Audio 1] 配音 / 配乐参考：按它的节奏、情绪与声音特征生成，台词口型与之对齐"


def build_reference_block(labels: list[str], *, audio: bool = False) -> str:
    """全能参考模式的提示词开头：逐行列出 [Image n] 对应的角色 / 场景 / 关键帧说明，可附 [Audio 1] 行。"""
    if not labels and not audio:
        return ""
    lines = [REFERENCE_BLOCK_HEADER] + [f"[Image {index + 1}] {label}" for index, label in enumerate(labels)]
    if audio:
        lines.append(AUDIO_REFERENCE_LINE)
    return "\n".join(lines)


def prepend_reference_block(prompt: str, labels: list[str], *, audio: bool = False) -> str:
    """把参考素材块放到提示词最前面；用户改过的提示词里已有 [Image 1] / [Audio 1] 则不重复加。"""
    text = (prompt or "").strip()
    block = build_reference_block(labels, audio=audio)
    if not block or "[Image 1]" in text or "[Audio 1]" in text:
        return text
    return f"{block}\n\n{text}".strip() if text else block


async def derive_video_preview(
    db,
    *,
    base: VideoBaseDraft,
    context: VideoGenerationContext,
) -> VideoDerivedPreview:
    pack = await build_shot_video_prompt_pack(db, shot_id=base.shot_id)
    if base.prompt:
        rendered_prompt = enrich_rendered_video_prompt(
            rendered_prompt=base.prompt,
            pack=pack,
        )
        rendered_prompt = prepend_reference_block(rendered_prompt, context.reference_labels, audio=bool(context.audio_file_id))
        return VideoDerivedPreview(
            shot_id=base.shot_id,
            reference_mode=context.reference_mode,
            rendered_prompt=rendered_prompt,
            images=context.images,
            pack=pack,
            template_id=context.template_id,
            template_name=None,
            warnings=[],
        )

    template = await _resolve_video_prompt_template(db, template_id=context.template_id)
    warnings: list[str] = []
    if template is None:
        warnings.append("未配置视频提示词模板，已使用系统默认拼装提示词")
        rendered_prompt = _fallback_video_prompt(pack)
    else:
        rendered_prompt = _render_template(template.content, _pack_variables(pack))
        if not rendered_prompt:
            warnings.append("视频提示词模板渲染结果为空，已使用系统默认拼装提示词")
            rendered_prompt = _fallback_video_prompt(pack)
        else:
            rendered_prompt = enrich_rendered_video_prompt(
                rendered_prompt=rendered_prompt,
                pack=pack,
            )

    return VideoDerivedPreview(
        shot_id=base.shot_id,
        reference_mode=context.reference_mode,
        rendered_prompt=prepend_reference_block(rendered_prompt, context.reference_labels, audio=bool(context.audio_file_id)),
        images=context.images,
        pack=pack,
        template_id=template.id if template else None,
        template_name=template.name if template else None,
        warnings=warnings,
    )


def to_shot_video_prompt_preview_read(
    *,
    derived: VideoDerivedPreview,
) -> ShotVideoPromptPreviewRead:
    return ShotVideoPromptPreviewRead(
        shot_id=derived.shot_id,
        template_id=derived.template_id,
        template_name=derived.template_name,
        rendered_prompt=derived.rendered_prompt,
        pack=derived.pack,
        warnings=derived.warnings,
    )
