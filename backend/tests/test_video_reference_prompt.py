"""全能参考视频模式：提示词组装（镜头语言、时间码节拍、[Image n] 参考块）、方舟 payload、参考图收集。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.contracts.video_generation import VideoGenerationInput
from app.core.integrations.volcengine.video_payload import (
    build_content,
    to_image_url_value,
)
from app.models.studio import FileItem, FileType
from app.schemas.studio.shots import ShotPromptCameraInfo
from app.services.film.generated_video import preview_prompt_and_images
from app.services.studio.creator_flow import (
    attach_entity_image,
    attach_shot_keyframe,
    auto_confirm_chapter,
    build_creator_board,
)
from app.services.studio.generation.video import (
    REFERENCE_MODE,
    collect_reference_candidates,
    resolve_video_reference_images,
    validate_images_count,
)
from app.services.studio.generation.video.derive_preview import (
    REFERENCE_BLOCK_HEADER,
    prepend_reference_block,
)
from app.services.studio.shot_video_prompt_pack import camera_phrase, timecoded_beats
from tests.test_creator_flow import _build_session, _seed


def test_camera_phrase_translates_codes_with_lens_hint() -> None:
    phrase = camera_phrase(ShotPromptCameraInfo(camera_shot="ELS", angle="EYE_LEVEL", movement="DOLLY_IN"))
    assert "24mm" in phrase and "平视" in phrase and "推近" in phrase
    assert camera_phrase(ShotPromptCameraInfo()) == ""
    assert camera_phrase(ShotPromptCameraInfo(camera_shot="WEIRD")) == "WEIRD"


def test_timecoded_beats_split_duration_evenly() -> None:
    assert timecoded_beats(["a", "b", "c"], 6) == ["[0-2s] a", "[2-4s] b", "[4-6s] c"]
    assert timecoded_beats(["a", " b "], 5) == ["[0-2s] a", "[2-5s] b"]
    assert timecoded_beats(["only"], 8) == ["only"]
    assert timecoded_beats(["a", "b"], None) == ["a", "b"]
    # 时长放不下的段落不加时间码（round 采用银行家舍入：边界 0,0,0,1,1）
    assert timecoded_beats(["a", "b", "c", "d"], 1) == ["a", "b", "[0-1s] c", "d"]


def test_reference_block_is_prepended_once() -> None:
    labels = ["角色「雷霆总监」：40岁", "本镜头关键帧（构图与起始状态）"]
    text = prepend_reference_block("镜头描述", labels)
    assert text.startswith(REFERENCE_BLOCK_HEADER)
    assert "[Image 1] 角色「雷霆总监」：40岁" in text and "[Image 2] 本镜头关键帧" in text and text.endswith("镜头描述")
    assert prepend_reference_block(text, labels) == text  # 用户改过的提示词里已有 [Image 1]，不重复加
    assert prepend_reference_block("x", []) == "x"


def test_build_content_emits_reference_images_with_url_passthrough() -> None:
    input_ = VideoGenerationInput(
        prompt="[Image 1] 雷霆总监走向白板",
        reference_images=["https://blob.example/face.png", "iVBORw0KGgo="],
        model="dreamina-seedance-2-5-260628",
        ratio="9:16",
        seconds=5,
    )
    content = build_content(input_)
    assert content[0] == {"type": "text", "text": "[Image 1] 雷霆总监走向白板"}
    refs = [item for item in content if item.get("role") == "reference_image"]
    assert [item["image_url"]["url"] for item in refs] == ["https://blob.example/face.png", "data:image/png;base64,iVBORw0KGgo="]
    assert to_image_url_value("http://x/y.jpg") == "http://x/y.jpg"


def test_contract_rejects_reference_images_with_first_frame() -> None:
    with pytest.raises(ValueError):
        VideoGenerationInput(prompt="x", first_frame_base64="abc", reference_images=["https://a/b.png"], ratio="9:16")
    with pytest.raises(ValueError):
        VideoGenerationInput(reference_images=[f"https://a/{i}.png" for i in range(10)], ratio="9:16")
    assert VideoGenerationInput(reference_images=["https://a/b.png"], ratio="9:16").prompt is None


def test_validate_images_count_for_reference_mode() -> None:
    with pytest.raises(HTTPException):
        validate_images_count(REFERENCE_MODE, [])
    with pytest.raises(HTTPException):
        validate_images_count(REFERENCE_MODE, [str(i) for i in range(10)])
    validate_images_count(REFERENCE_MODE, ["a"])
    validate_images_count("first", ["a"])


@pytest.mark.asyncio
async def test_reference_candidates_and_preview_prompt() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        scene = next(e for e in board.entities if e.type == "scene")

        # 没有任何形象图时 reference 模式直接报错，提示先生成形象
        with pytest.raises(HTTPException):
            await resolve_video_reference_images(db, shot_id="s1", reference_mode=REFERENCE_MODE, images=None)

        db.add_all(
            [
                FileItem(id="f-face", type=FileType.image, name="face.jpg", thumbnail="https://blob/face.jpg", tags=[], storage_key="files/a/face.jpg"),
                FileItem(id="f-scene", type=FileType.image, name="office.png", thumbnail="https://blob/office.png", tags=[], storage_key="files/b/office.png"),
                FileItem(id="f-frame", type=FileType.image, name="frame.png", thumbnail="https://blob/frame.png", tags=[], storage_key="files/c/frame.png"),
            ]
        )
        await db.flush()
        await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f-face")
        await attach_entity_image(db, entity_type="scene", entity_id=scene.id, file_id="f-scene")
        await attach_shot_keyframe(db, shot_id="s1", file_id="f-frame")

        candidates = await collect_reference_candidates(db, shot_id="s1")
        assert [c.file_id for c in candidates] == ["f-face", "f-scene", "f-frame"]
        assert candidates[0].label.startswith("角色「雷霆总监」") and candidates[1].label.startswith("场景「开放式办公区」")
        assert candidates[2].kind == "keyframe"

        prompt, images, pack, labels = await preview_prompt_and_images(db, shot_id="s1", reference_mode=REFERENCE_MODE, prompt=None)
        assert images == ["f-face", "f-scene", "f-frame"] and len(labels) == 3
        assert prompt.startswith(REFERENCE_BLOCK_HEADER) and "[Image 3] 本镜头关键帧" in prompt
        assert "镜头语言：" in prompt and "50mm" in prompt and pack is not None  # 默认中景 → 带焦段的镜头语言

        # 调用方只选两张并自带说明：顺序与说明都按调用方的来
        prompt2, images2, _pack, labels2 = await preview_prompt_and_images(
            db, shot_id="s1", reference_mode=REFERENCE_MODE, prompt=None, images=["f-frame", "f-face"], reference_labels=["关键帧", "主角"]
        )
        assert images2 == ["f-frame", "f-face"] and labels2 == ["关键帧", "主角"] and "[Image 1] 关键帧" in prompt2

        # 用户改过的提示词：原样保留，只在前面补参考块
        prompt3, _i, _p, _l = await preview_prompt_and_images(db, shot_id="s1", reference_mode=REFERENCE_MODE, prompt="自定义描述")
        assert prompt3.startswith(REFERENCE_BLOCK_HEADER) and "自定义描述" in prompt3

        # 帧模式不受影响
        prompt4, images4, _p4, labels4 = await preview_prompt_and_images(db, shot_id="s1", reference_mode="first", prompt=None)
        assert images4 == ["f-frame"] and labels4 == [] and "[Image 1]" not in prompt4
    await engine.dispose()
