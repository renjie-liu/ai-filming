"""一句话起草剧本 Agent：ScriptDrafterAgent

为什么存在：很多用户没有现成剧本，只有一句想法（LibTV / 即梦「一句话出剧本」是它们的起点）。
这里把想法 + 作品题材 / 画面风格 / 目标时长变成一集可直接「一键拆分镜」的剧本：
格式与分镜 / 提取 Agent 的期望一致（场景行、动作句、「角色：台词」、角色首次出场带外貌），
所以起草后的文本不需要用户再整理。
"""

from __future__ import annotations

from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase
from app.schemas.skills.script_processing import ScriptDraftResult

_SCRIPT_DRAFTER_SYSTEM_PROMPT = """\
你是短剧编剧。根据用户的一句话创意写一集可直接拍摄的竖屏短剧剧本。

写法要求（必须遵守，后续程序会按这个格式拆镜头、识别角色场景）：
- 第一行：【第N集】标题
- 场景切换用单独一行写「地点，时间。」例如：开放式办公区，清晨。
- 角色第一次出场时在括号里写年龄、外貌、服装、标志性物件，例如：雷霆总监（40岁，西装外套套在T恤外，手里攥着闪电形状的马克杯）
- 对白一行一句，格式「角色名：台词」；不要用引号包住台词
- 动作用短句描述画面里看得见的事（谁、做什么、在哪、拿着什么），不写心理活动、不写无法拍出来的内容
- 节奏：短剧，前 10 秒要有冲突或悬念，结尾留钩子；每个场景 1–3 个动作 + 1–3 句对白
- 篇幅按目标时长：大约每 5 秒一个镜头，每个镜头对应 1–2 行动作或对白；60 秒约 10–12 个镜头、300–500 字
- 角色不超过 4 个，场景不超过 3 个，角色名要稳定（全篇同一个称呼）
- 语言：简体中文，口语化，贴合题材与画面风格

输出 ScriptDraftResult（JSON）：
- title：本集标题
- logline：一句话梗概
- outline：3–6 条分段大纲（按时间顺序，每条一句）
- script_text：完整剧本正文（按上面的格式，用换行分隔）
- notes：给创作者的一句提示（可选，例如哪些角色需要先定形象）

只输出 JSON。
"""

SCRIPT_DRAFTER_PROMPT = PromptTemplate(
    input_variables=["idea", "style", "visual_style", "target_seconds", "episode_index", "context"],
    template=(
        "## 创意\n{idea}\n\n"
        "## 作品设定\n题材：{style}\n画面：{visual_style}\n这是第 {episode_index} 集\n目标时长：约 {target_seconds} 秒\n\n"
        "## 前情 / 补充要求（可能为空）\n{context}\n\n"
        "## 输出\n"
    ),
)


class ScriptDrafterAgent(AgentBase[ScriptDraftResult]):
    """一句话 → 一集剧本。输入创意与作品设定，输出可直接拆分镜的剧本。"""

    @property
    def system_prompt(self) -> str:
        return _SCRIPT_DRAFTER_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return SCRIPT_DRAFTER_PROMPT

    @property
    def output_model(self) -> type[ScriptDraftResult]:
        return ScriptDraftResult

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """兼容模型常见偏差：正文字段名不同、outline 是字符串、整体被包了一层。"""
        data = dict(data)
        if "ScriptDraftResult" in data and isinstance(data["ScriptDraftResult"], dict):
            data = dict(data["ScriptDraftResult"])
        if "script_text" not in data:
            for key in ("script", "screenplay", "text", "content"):
                if key in data:
                    data["script_text"] = str(data.pop(key) or "")
                    break
        outline = data.get("outline")
        if isinstance(outline, str):
            data["outline"] = [line.strip("-• ").strip() for line in outline.splitlines() if line.strip()]
        elif isinstance(outline, list):
            data["outline"] = [str(item).strip() for item in outline if str(item).strip()]
        data.setdefault("title", "")
        data.setdefault("logline", "")
        return data

    def draft(
        self,
        *,
        idea: str,
        style: str,
        visual_style: str,
        target_seconds: int,
        episode_index: int,
        context: str | None,
    ) -> ScriptDraftResult:
        return self.extract(
            idea=idea,
            style=style or "未指定",
            visual_style=visual_style or "未指定",
            target_seconds=max(15, int(target_seconds or 60)),
            episode_index=max(1, int(episode_index or 1)),
            context=(context or "").strip() or "无",
        )
