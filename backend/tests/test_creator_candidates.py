"""P2-c 创作页能力：多候选 / 历史回退、角色三视图、预演四宫格、配音 / 配乐参考。

历史候选来自任务关联表（每次图片任务成功落盘的 file_id），不新建表；三视图与四宫格只创建图片任务，
这里把 `create_image_task_and_link` 换成假实现，验证槽位、提示词与关联关系。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.contracts.video_generation import VideoGenerationInput
from app.core.integrations.volcengine.video_payload import build_content
from app.models.studio import (
    CharacterImage,
    FileItem,
    FileType,
    ShotFrameImage,
    ShotFrameType,
)
from app.models.studio_file_usages import FileUsage
from app.models.task import GenerationTask
from app.models.task_links import GenerationTaskLink
from app.schemas.studio.shots import ShotPromptCameraInfo, ShotVideoPromptPackRead
from app.services.film.generated_video import preview_prompt_and_images
from app.services.studio import creator_flow
from app.services.studio.creator_flow import (
    MAX_IMAGE_CANDIDATES,
    CreatorInputError,
    _candidate_rows,
    attach_entity_image,
    attach_shot_audio,
    attach_shot_keyframe,
    auto_confirm_chapter,
    build_creator_board,
    generate_character_views,
    generate_preview_grid,
)
from app.services.studio.generation.video import REFERENCE_MODE
from app.services.studio.generation.video.derive_preview import AUDIO_REFERENCE_LINE
from app.services.studio.shot_video_prompt_pack import build_preview_grid_prompt
from tests.test_creator_flow import _build_session, _seed


def _file(file_id: str, *, kind: FileType = FileType.image, name: str = "x.png") -> FileItem:
    return FileItem(id=file_id, type=kind, name=name, thumbnail=f"https://blob/{file_id}", tags=[], storage_key=f"files/{file_id}")


async def _record_task(db, *, task_id: str, relation_type: str, entity_id: str, file_id: str | None, created_at: datetime, status: str = "succeeded") -> None:
    """模拟一次已完成的图片任务：任务行 + 关联行（file_id 即结果文件）。"""
    db.add(GenerationTask(id=task_id, mode="async_polling", task_kind="image_generation", status=status, progress=100, payload={}, result=None, error="", created_at=created_at))
    await db.flush()
    db.add(GenerationTaskLink(task_id=task_id, resource_type="image", relation_type=relation_type, relation_entity_id=entity_id, file_id=file_id))
    await db.flush()


def test_candidate_rows_put_current_first_then_history_then_uploads() -> None:
    history = [("f3", "t3", "2026-01-03"), ("f2", "t2", "2026-01-02"), ("f1", "t1", "2026-01-01")]
    rows = _candidate_rows("f2", history, ["f9", "f1"])
    assert [(f, cur) for f, _t, _c, cur in rows] == [("f2", True), ("f3", False), ("f1", False), ("f9", False)]
    assert rows[0][1] == "t2"  # 当前图也带上生成它的任务
    # 当前图来自上传（历史里没有）：task_id 为空；超出上限截断
    many = [(f"h{i}", f"t{i}", None) for i in range(20)]
    rows = _candidate_rows("up", many)
    assert rows[0] == ("up", None, None, True) and len(rows) == MAX_IMAGE_CANDIDATES
    assert _candidate_rows(None, [], []) == []


@pytest.mark.asyncio
async def test_board_lists_candidates_from_task_history_and_adopts_one() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        db.add_all([_file("f-old"), _file("f-new"), _file("f-k1"), _file("f-k2")])
        await db.flush()

        # 角色：两次角色级生成任务（旧 → 新），当前主图是新的那张（任务表 created_at 为 naive，与线上一致）
        base = datetime(2026, 1, 1)  # noqa: DTZ001
        await _record_task(db, task_id="t-old", relation_type="character", entity_id=character.id, file_id="f-old", created_at=base)
        await _record_task(db, task_id="t-new", relation_type="character", entity_id=character.id, file_id="f-new", created_at=base + timedelta(minutes=1))
        await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f-new")
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        assert [(c.file_id, c.is_current, c.task_id) for c in character.image_candidates] == [("f-new", True, "t-new"), ("f-old", False, "t-old")]
        assert character.image_candidates[1].url == "https://blob/f-old"

        # 「采用」历史那张：正面行按 (精度, 角度) 唯一，所以是覆盖当前正面行而不是新插一行；历史仍完整
        before = len((await db.execute(select(CharacterImage).where(CharacterImage.character_id == character.id))).scalars().all())
        assert before == 1
        await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f-old")
        after_rows = (await db.execute(select(CharacterImage).where(CharacterImage.character_id == character.id))).scalars().all()
        assert len(after_rows) == 1 and after_rows[0].file_id == "f-old" and after_rows[0].is_primary
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        assert character.image_file_id == "f-old" and character.image_candidates[0].file_id == "f-old"
        assert [c.file_id for c in character.image_candidates] == ["f-old", "f-new"]
        await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f-new")
        assert len((await db.execute(select(CharacterImage).where(CharacterImage.character_id == character.id))).scalars().all()) == 1

        # 关键帧：帧槽位上的两次任务，当前文件是 f-k2，候选含 f-k1
        frame_id = await attach_shot_keyframe(db, shot_id="s1", file_id="f-k2")
        await _record_task(db, task_id="t-k1", relation_type="shot_frame_image", entity_id=str(frame_id), file_id="f-k1", created_at=base)
        await _record_task(db, task_id="t-k2", relation_type="shot_frame_image", entity_id=str(frame_id), file_id="f-k2", created_at=base + timedelta(minutes=2))
        board = await build_creator_board(db, chapter_id="c1")
        assert [(c.file_id, c.is_current) for c in board.shots[0].keyframe_candidates] == [("f-k2", True), ("f-k1", False)]
        assert board.shots[0].keyframe_image_task is not None and board.shots[0].keyframe_image_task.task_id == "t-k2"
        assert board.shots[1].keyframe_candidates == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_generate_character_views_creates_slots_and_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")

        with pytest.raises(CreatorInputError):
            await generate_character_views(db, character_id=character.id, views=["left"])  # 还没有正面形象

        db.add(_file("f-face", name="face.jpg"))
        await db.flush()
        await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f-face")

        calls: list[dict] = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            task_id = f"task-{len(calls)}"
            db_ = kwargs["db"]
            db_.add(GenerationTask(id=task_id, mode="async_polling", task_kind="image_generation", status="running", progress=20, payload={}, result=None, error=""))
            await db_.flush()
            db_.add(GenerationTaskLink(task_id=task_id, resource_type="image", relation_type=kwargs["relation_type"], relation_entity_id=kwargs["relation_entity_id"], file_id=None))
            await db_.flush()
            return task_id

        async def fake_refs(db, *, file_ids):
            return [{"file_id": fid, "url": f"https://blob/{fid}"} for fid in file_ids]

        monkeypatch.setattr(creator_flow, "create_image_task_and_link", fake_create)
        monkeypatch.setattr(creator_flow, "resolve_reference_image_refs_by_file_ids", fake_refs)

        task_ids = await generate_character_views(db, character_id=character.id, views=["left", "back"])
        assert task_ids == ["task-1", "task-2"]
        rows = (await db.execute(select(CharacterImage).where(CharacterImage.character_id == character.id))).scalars().all()
        angles = sorted(str(getattr(r.view_angle, "value", r.view_angle)) for r in rows)
        assert angles == ["BACK", "FRONT", "LEFT"]
        assert all(not r.is_primary for r in rows if str(getattr(r.view_angle, "value", r.view_angle)) != "FRONT")
        assert calls[0]["relation_type"] == "character_image" and calls[0]["purpose"] == "character_view"
        assert "面向画面左侧" in calls[0]["prompt"] and "同一个人" in calls[0]["prompt"] and "背面" in calls[1]["prompt"]
        assert calls[0]["images"] == [{"file_id": "f-face", "url": "https://blob/f-face"}]

        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        assert [(v.view_angle, v.file_id) for v in character.views] == [("LEFT", None), ("BACK", None)]
        assert character.views[0].task is not None and character.views[0].task.status == "running"
        assert character.image_file_id == "f-face"  # 主图不受视图槽位影响
        assert [c.file_id for c in character.image_candidates] == ["f-face"]

        # 再次生成同一视角：复用槽位，不新增行
        await generate_character_views(db, character_id=character.id, views=["left"])
        assert len((await db.execute(select(CharacterImage).where(CharacterImage.character_id == character.id))).scalars().all()) == 3
        with pytest.raises(CreatorInputError):
            await generate_character_views(db, character_id=character.id, views=["top"])
    await engine.dispose()


def test_build_preview_grid_prompt_uses_beats_camera_and_cast() -> None:
    pack = ShotVideoPromptPackRead(
        shot_id="s1",
        title="雷霆自我介绍",
        script_excerpt="雷霆走向白板",
        action_beats=["推门进来", "环视众人", "走到白板前"],
        camera=ShotPromptCameraInfo(camera_shot="MS", angle="EYE_LEVEL", movement="STATIC"),
        visual_style="真人实拍",
        style="都市",
    )
    prompt = build_preview_grid_prompt(pack)
    assert prompt.startswith("一张 2×2 四格连续分镜图")
    assert "第 1 格：推门进来" in prompt and "第 3 格：走到白板前" in prompt and "第 4–4 格" in prompt
    assert "镜头语言：" in prompt and "50mm" in prompt and "画面风格：真人实拍，都市" in prompt
    # 没有节拍时退回剧本摘录；节拍超过四个只取前四
    assert "第 1 格：雷霆走向白板" in build_preview_grid_prompt(pack.model_copy(update={"action_beats": []}))
    many = build_preview_grid_prompt(pack.model_copy(update={"action_beats": ["a", "b", "c", "d", "e"]}))
    assert "第 4 格：d" in many and "e" not in many.split("第 4 格：d")[1].split("\n")[0]


@pytest.mark.asyncio
async def test_generate_preview_grid_targets_key_frame_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")
        calls: list[dict] = []

        async def fake_create(**kwargs):
            calls.append(kwargs)
            task_id = f"grid-{len(calls)}"
            db_ = kwargs["db"]
            db_.add(GenerationTask(id=task_id, mode="async_polling", task_kind="image_generation", status="pending", progress=0, payload={}, result=None, error=""))
            await db_.flush()
            db_.add(GenerationTaskLink(task_id=task_id, resource_type="image", relation_type=kwargs["relation_type"], relation_entity_id=kwargs["relation_entity_id"], file_id=None))
            await db_.flush()
            return task_id

        monkeypatch.setattr(creator_flow, "create_image_task_and_link", fake_create)

        task_id = await generate_preview_grid(db, shot_id="s1")
        assert task_id == "grid-1"
        grid = (await db.execute(select(ShotFrameImage).where(ShotFrameImage.shot_detail_id == "s1", ShotFrameImage.frame_type == ShotFrameType.key))).scalars().one()
        assert grid.file_id is None
        assert calls[0]["relation_type"] == "shot_frame_image" and calls[0]["relation_entity_id"] == str(grid.id)
        assert calls[0]["target_ratio"] == "1:1" and calls[0]["purpose"] == "storyboard_preview"
        assert "四格连续分镜图" in calls[0]["prompt"]

        board = await build_creator_board(db, chapter_id="c1")
        assert board.shots[0].preview_grid_url is None
        assert board.shots[0].preview_grid_task is not None and board.shots[0].preview_grid_task.task_id == "grid-1"
        assert board.shots[0].keyframe_file_id is None and board.summary.keyframe_count == 0  # key 帧不算关键帧

        # 再次生成复用同一槽位；比例按调用方
        await generate_preview_grid(db, shot_id="s1", ratio="9:16")
        assert len((await db.execute(select(ShotFrameImage).where(ShotFrameImage.shot_detail_id == "s1"))).scalars().all()) == 1
        assert calls[1]["target_ratio"] == "9:16"
        with pytest.raises(ValueError):
            await generate_preview_grid(db, shot_id="missing")
    await engine.dispose()


@pytest.mark.asyncio
async def test_shot_audio_reference_round_trip() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        await auto_confirm_chapter(db, chapter_id="c1")
        board = await build_creator_board(db, chapter_id="c1")
        character = next(e for e in board.entities if e.type == "character")
        db.add_all([_file("f-face"), _file("f-voice", kind=FileType.audio, name="voice.mp3"), _file("f-voice2", kind=FileType.audio, name="bgm.wav")])
        await db.flush()
        await attach_entity_image(db, entity_type="character", entity_id=character.id, file_id="f-face")

        with pytest.raises(CreatorInputError):
            await attach_shot_audio(db, shot_id="s1", file_id="f-face")  # 不是音频
        assert await attach_shot_audio(db, shot_id="s1", file_id="f-voice") == "f-voice"
        usages = (await db.execute(select(FileUsage).where(FileUsage.shot_id == "s1"))).scalars().all()
        assert [(u.file_id, u.usage_kind) for u in usages] == [("f-voice", "reference_audio")]
        board = await build_creator_board(db, chapter_id="c1")
        assert board.shots[0].audio_file_id == "f-voice" and board.shots[0].audio_url == "https://blob/f-voice"
        assert board.shots[1].audio_file_id is None

        # 换一条：只保留最新；全能参考模式的提示词带 [Audio 1] 行；帧模式也带
        await attach_shot_audio(db, shot_id="s1", file_id="f-voice2")
        usages = (await db.execute(select(FileUsage).where(FileUsage.shot_id == "s1"))).scalars().all()
        assert [u.file_id for u in usages] == ["f-voice2"]
        prompt, images, _pack, labels = await preview_prompt_and_images(db, shot_id="s1", reference_mode=REFERENCE_MODE, prompt=None, audio_file_id="f-voice2")
        assert images == ["f-face"] and labels and AUDIO_REFERENCE_LINE in prompt
        prompt_text_only, images_t, _p, _l = await preview_prompt_and_images(db, shot_id="s1", reference_mode="text_only", prompt="旁白", audio_file_id="f-voice2")
        assert images_t == [] and prompt_text_only.startswith("参考素材") and "[Audio 1]" in prompt_text_only and "旁白" in prompt_text_only

        # 清除
        assert await attach_shot_audio(db, shot_id="s1", file_id=None) is None
        assert (await db.execute(select(FileUsage).where(FileUsage.shot_id == "s1"))).scalars().all() == []
        board = await build_creator_board(db, chapter_id="c1")
        assert board.shots[0].audio_file_id is None
    await engine.dispose()


def test_video_contract_and_payload_carry_reference_audio() -> None:
    input_ = VideoGenerationInput(
        prompt="[Image 1] 雷霆说话\n[Audio 1] 按配音节奏",
        reference_images=["https://blob/face.png"],
        reference_audio="https://blob/voice.mp3",
        model="dreamina-seedance-2-5-260628",
        ratio="9:16",
        seconds=5,
    )
    content = build_content(input_)
    audio_items = [item for item in content if item.get("role") == "reference_audio"]
    assert audio_items == [{"type": "audio_url", "role": "reference_audio", "audio_url": {"url": "https://blob/voice.mp3"}}]
    assert content.index(audio_items[0]) > 0  # 文本在前
    assert "reference_audio" not in str(build_content(VideoGenerationInput(prompt="x", ratio="9:16")))
