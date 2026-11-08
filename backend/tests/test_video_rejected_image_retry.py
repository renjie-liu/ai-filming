"""方舟输入审核拒绝某张参考图（InputImageSensitiveContentDetected）时：自动去掉那张图并重编号后重试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import DeliveryMode
from app.models.task import GenerationTask, GenerationTaskStatus
from app.services.film import generated_video as gv

REJECTED = (
    "Ark API 400 InputImageSensitiveContentDetected.PrivacyInformation: The request failed because the input image "
    "'content[{index}]' may contain real person. Request id: 0217941181471239e89f26b858b9d25ce524a85522bfdaf949d25"
)
PROMPT = (
    "参考素材（[Image n] 与上传顺序一一对应；人物脸型、发型、服装与场景布局必须与参考一致）：\n"
    "[Image 1] 角色「孙悟空」：民宿经营者\n[Image 2] 角色「林晓」：住店客人\n[Image 3] 场景「花果山民宿小院」\n"
    "[Image 4] 本镜头关键帧（构图与起始状态）\n\n中景平视，[Image 1] 挠头，[Image 2] 抬脚往里走，构图参考 [Image 4]。"
)


def test_content_layout_mirrors_ark_content_order() -> None:
    assert gv.content_layout({"prompt": "p", "reference_images": ["a", "b"]}) == ["text", "reference:0", "reference:1"]
    assert gv.content_layout({"prompt": "p", "first_frame_base64": "x", "reference_audio": "https://a/b.mp3"}) == ["text", "first_frame", "audio"]
    assert gv.content_layout({"prompt": "", "reference_images": ["a"]}) == ["reference:0"]


def test_drop_rejected_reference_renumbers_prompt() -> None:
    input_dict = {"prompt": PROMPT, "reference_images": ["u1", "u2", "u3", "u4-keyframe"], "ratio": "9:16"}
    adjusted = gv.drop_rejected_input_image(input_dict, REJECTED.format(index=4))
    assert adjusted is not None
    new_input, record = adjusted
    assert new_input["reference_images"] == ["u1", "u2", "u3"]
    assert record["kind"] == "reference:3" and record["content_index"] == 4 and record["label"] == "本镜头关键帧（构图与起始状态）"
    assert "[Image 4]" not in new_input["prompt"] and "关键帧" not in new_input["prompt"]
    assert new_input["prompt"].endswith("中景平视，[Image 1] 挠头，[Image 2] 抬脚往里走，构图参考 。") or "构图参考" in new_input["prompt"]
    # 原输入不被改动
    assert len(input_dict["reference_images"]) == 4

    # 去掉中间一张：后面的编号前移
    adjusted2 = gv.drop_rejected_input_image(input_dict, REJECTED.format(index=2))
    assert adjusted2 is not None
    new2, record2 = adjusted2
    assert new2["reference_images"] == ["u1", "u3", "u4-keyframe"]
    assert record2["label"].startswith("角色「林晓」")
    assert "[Image 2] 场景「花果山民宿小院」" in new2["prompt"] and "[Image 3] 本镜头关键帧" in new2["prompt"]
    assert "[Image 4]" not in new2["prompt"] and "构图参考 [Image 3]" in new2["prompt"]


def test_drop_rejected_frame_falls_back_to_text_and_remaining_references() -> None:
    input_dict = {"prompt": "首帧模式", "first_frame_base64": "data:image/png;base64,AAAA", "reference_images": [], "ratio": "9:16"}
    adjusted = gv.drop_rejected_input_image(input_dict, REJECTED.format(index=1))
    assert adjusted is not None
    new_input, record = adjusted
    assert new_input["first_frame_base64"] is None and record["kind"] == "first_frame"
    # 没有提示词也没有任何参考 → 无法重试
    assert gv.drop_rejected_input_image({"prompt": "", "first_frame_base64": "x", "reference_images": []}, REJECTED.format(index=0)) is None
    # 不是人脸拒绝 → 不处理
    assert gv.drop_rejected_input_image(input_dict, "Ark API 400 InvalidParameter: ratio") is None
    # 索引越界 → 不处理
    assert gv.drop_rejected_input_image(input_dict, REJECTED.format(index=7)) is None


class _FakeVideoTask:
    """前 N 次按脚本返回拒绝错误，之后成功；记录每次收到的参考图数量。"""

    script: list[str] = []
    seen_inputs: list[dict] = []

    def __init__(self, *, provider_config, input_):  # noqa: ANN001
        self._input = input_
        self._result = None
        self._error = ""

    async def run(self):
        type(self).seen_inputs.append(self._input.model_dump())
        if type(self).script:
            self._error = type(self).script.pop(0)
            return None
        from app.core.contracts.video_generation import VideoGenerationResult

        self._result = VideoGenerationResult(url="https://example.com/v.mp4", file_id=None, provider_task_id="cgt-1", provider="volcengine", status="succeeded")
        return None

    async def get_result(self):
        return self._result

    async def status(self):
        return {"error": self._error}


@pytest.mark.asyncio
async def test_run_video_generation_task_retries_without_rejected_image(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "video-retry.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_local() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.create(payload={"task_kind": "video_generation"}, mode=DeliveryMode.async_polling, task_kind="video_generation")
        await db.commit()

    _FakeVideoTask.script = [REJECTED.format(index=4)]
    _FakeVideoTask.seen_inputs = []
    monkeypatch.setattr(gv, "VideoGenerationTask", _FakeVideoTask)
    monkeypatch.setattr(gv, "async_session_maker", session_local)

    class _File:
        id = "file-video-1"

    async def _fake_persist(session, **kwargs):  # noqa: ANN001
        return _File()

    monkeypatch.setattr(gv, "persist_generated_video_to_shot", _fake_persist)

    async def _noop_recompute(session, *, shot_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(gv, "recompute_shot_status", _noop_recompute)

    run_args = {
        "shot_id": "shot-1",
        "provider": "volcengine",
        "api_key": "k",
        "base_url": "https://ark.example/api/v3",
        "input": {"prompt": PROMPT, "reference_images": ["u1", "u2", "u3", "u4-keyframe"], "ratio": "9:16", "seconds": 4, "model": "dreamina-seedance-2-5-260628"},
    }
    await gv.run_video_generation_task(task_id=task.id, run_args=run_args)

    assert len(_FakeVideoTask.seen_inputs) == 2
    assert _FakeVideoTask.seen_inputs[1]["reference_images"] == ["u1", "u2", "u3"]
    assert "[Image 4]" not in _FakeVideoTask.seen_inputs[1]["prompt"]
    async with session_local() as db:
        row = await db.get(GenerationTask, task.id)
        assert row is not None and row.status == GenerationTaskStatus.succeeded
        result = row.result if isinstance(row.result, dict) else __import__("json").loads(row.result or "{}")
        assert result["file_id"] == "file-video-1"
        assert result["dropped_references"][0]["label"] == "本镜头关键帧（构图与起始状态）"
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_video_generation_task_fails_when_rejection_cannot_be_resolved(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "video-retry-fail.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_local() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.create(payload={"task_kind": "video_generation"}, mode=DeliveryMode.async_polling, task_kind="video_generation")
        await db.commit()

    _FakeVideoTask.script = ["Ark API 400 InvalidParameter: duration must be between 4 and 30"]
    _FakeVideoTask.seen_inputs = []
    monkeypatch.setattr(gv, "VideoGenerationTask", _FakeVideoTask)
    monkeypatch.setattr(gv, "async_session_maker", session_local)

    async def _noop_recompute(session, *, shot_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(gv, "recompute_shot_status", _noop_recompute)
    await gv.run_video_generation_task(
        task_id=task.id,
        run_args={"shot_id": "shot-1", "provider": "volcengine", "api_key": "k", "base_url": None, "input": {"prompt": "p", "reference_images": ["u1"], "ratio": "9:16"}},
    )
    assert len(_FakeVideoTask.seen_inputs) == 1
    async with session_local() as db:
        row = await db.get(GenerationTask, task.id)
        assert row is not None and row.status == GenerationTaskStatus.failed and "InvalidParameter" in (row.error or "")
    await engine.dispose()
