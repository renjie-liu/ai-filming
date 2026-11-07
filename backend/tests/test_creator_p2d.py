"""P2-d：一句话起草剧本（Agent 输出规范化 + 任务创建）、章节镜头重排。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.chains.agents.script_drafter_agent import ScriptDrafterAgent
from app.models.studio import Shot
from app.models.task import GenerationTask
from app.schemas.skills.script_processing import ScriptDraftResult
from app.services.script_processing_tasks import SCRIPT_DRAFT_RELATION_TYPE, SCRIPT_DRAFT_TASK_KIND, create_script_draft_task
from app.services.studio.creator_flow import CreatorInputError, auto_confirm_chapter, build_creator_board, reorder_chapter_shots
from app.services.studio.shot_detail_defaults import build_default_shot_detail
from tests.test_creator_flow import _build_session, _seed


class _DummyModel:
    """AgentBase 只在构造时调用 model.bind；format_output 不触碰模型。"""

    def bind(self, **_kwargs):
        return self


def test_script_drafter_normalizes_common_output_shapes() -> None:
    agent = ScriptDrafterAgent(_DummyModel())  # type: ignore[arg-type]
    raw = '```json\n{"ScriptDraftResult": {"title": "花果山日志", "logline": "退休猴王的第一天", "outline": "- 清晨醒来\\n- 徒弟来访", "script": "【第1集】花果山日志\\n花果山，清晨。\\n孙悟空：又是一天。"}}\n```'
    result = agent.format_output(raw)
    assert isinstance(result, ScriptDraftResult)
    assert result.title == "花果山日志" and result.outline == ["清晨醒来", "徒弟来访"]
    assert result.script_text.startswith("【第1集】") and "孙悟空：又是一天。" in result.script_text
    # 正文缺失时校验失败（script_text 必填）
    with pytest.raises(Exception):
        agent.format_output('{"title": "x"}')
    rendered = agent.render_prompt(idea="退休猴王", style="真人都市", visual_style="现实", target_seconds=60, episode_index=2, context="无")
    assert "退休猴王" in rendered and "第 2 集" in rendered and "60 秒" in rendered and "角色名：台词" in rendered


@pytest.mark.asyncio
async def test_create_script_draft_task_carries_project_settings_and_reuses_active() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        info = await create_script_draft_task(db, project_id="p1", chapter_id="c1", idea="孙悟空退休后的生活", target_seconds=90, context=None)
        assert info.reused is False and info.relation_type == SCRIPT_DRAFT_RELATION_TYPE and info.relation_entity_id == "c1"
        task = await db.get(GenerationTask, info.task_id)
        assert task is not None and task.task_kind == SCRIPT_DRAFT_TASK_KIND
        run_args = task.payload["run_args"]
        assert run_args["idea"] == "孙悟空退休后的生活" and run_args["target_seconds"] == 90 and run_args["episode_index"] == 1
        assert run_args["style"] == "真人都市" and run_args["visual_style"] == "现实" and run_args["context"] is None
        # 同一章节已有起草任务在跑 → 复用
        again = await create_script_draft_task(db, project_id="p1", chapter_id="c1", idea="另一个想法", target_seconds=60, context="")
        assert again.reused is True and again.task_id == info.task_id
        # 不带章节：关联到作品
        by_project = await create_script_draft_task(db, project_id="p1", chapter_id=None, idea="想法", target_seconds=60, context=None)
        assert by_project.relation_entity_id == "p1" and by_project.reused is False
        with pytest.raises(HTTPException):
            await create_script_draft_task(db, project_id="missing", chapter_id=None, idea="x", target_seconds=60, context=None)
        with pytest.raises(HTTPException):
            await create_script_draft_task(db, project_id="p1", chapter_id="wrong", idea="x", target_seconds=60, context=None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_reorder_chapter_shots_two_pass_and_validation() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed(db)
        db.add(Shot(id="s3", chapter_id="c1", index=3, title="第三镜"))
        await db.flush()
        db.add(build_default_shot_detail("s3"))
        await db.flush()
        await auto_confirm_chapter(db, chapter_id="c1")

        assert await reorder_chapter_shots(db, chapter_id="c1", shot_ids=["s3", "s1", "s2"]) == ["s3", "s1", "s2"]
        rows = (await db.execute(select(Shot).where(Shot.chapter_id == "c1").order_by(Shot.index))).scalars().all()
        assert [(r.id, r.index) for r in rows] == [("s3", 1), ("s1", 2), ("s2", 3)]
        board = await build_creator_board(db, chapter_id="c1")
        assert [s.id for s in board.shots] == ["s3", "s1", "s2"] and [s.index for s in board.shots] == [1, 2, 3]

        # 交换相邻两个（上移 / 下移）
        await reorder_chapter_shots(db, chapter_id="c1", shot_ids=["s1", "s3", "s2"])
        board = await build_creator_board(db, chapter_id="c1")
        assert [s.id for s in board.shots] == ["s1", "s3", "s2"]

        for bad in (["s1", "s2"], ["s1", "s2", "s3", "s3"], ["s1", "s2", "sX"]):
            with pytest.raises(CreatorInputError):
                await reorder_chapter_shots(db, chapter_id="c1", shot_ids=bad)
        with pytest.raises(ValueError):
            await reorder_chapter_shots(db, chapter_id="missing", shot_ids=["s1"])
    await engine.dispose()
