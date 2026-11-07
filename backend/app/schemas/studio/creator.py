"""创作模式（Creator Mode）读模型。

为什么存在：创作页是单页五步流程，需要一次请求拿到章节下全部镜头、实体与最近任务状态，
而不是在前端拼十几个接口；这里定义的都是只读聚合结构，不引入新的状态语义。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CreatorTaskRead(BaseModel):
    """某个资源最近一次生成任务的轻量状态（供卡片展示进度 / 失败原因）。"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="pending / running / streaming / succeeded / failed / cancelled")
    progress: int = Field(0, description="进度 0-100")
    error: str | None = Field(None, description="失败原因（原文，前端负责中文映射）")


class CreatorDialogueLineRead(BaseModel):
    """镜头对白行（已确认）。"""

    speaker: str = Field("", description="说话角色名；旁白为空")
    text: str = Field(..., description="台词")


class CreatorShotRead(BaseModel):
    """创作页分镜卡所需的镜头信息。"""

    id: str
    index: int
    title: str
    script_excerpt: str = ""
    status: str = Field(..., description="shot.status：pending / ready（信息确认状态）")
    duration: int = Field(0, description="时长（秒）")
    description: str = Field("", description="画面描述（首帧提示词；AI 生成后可编辑）")
    dialogue: list[CreatorDialogueLineRead] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    scene_ids: list[str] = Field(default_factory=list)
    prop_ids: list[str] = Field(default_factory=list)
    keyframe_file_id: str | None = Field(None, description="首帧图片文件 ID")
    keyframe_url: str | None = Field(None, description="首帧图片地址")
    keyframe_prompt_task: CreatorTaskRead | None = Field(None, description="最近一次首帧提示词任务")
    keyframe_image_task: CreatorTaskRead | None = Field(None, description="最近一次首帧图片任务")
    video_file_id: str | None = Field(None, description="生成视频文件 ID")
    video_url: str | None = Field(None, description="生成视频地址")
    video_task: CreatorTaskRead | None = Field(None, description="最近一次视频任务")


class CreatorEntityRead(BaseModel):
    """创作页角色 / 场景 / 道具 / 服装卡。"""

    type: Literal["character", "scene", "prop", "costume"]
    id: str
    name: str
    description: str = ""
    thumbnail: str = Field("", description="形象 / 参考图地址；无图为空")
    image_id: int | None = Field(None, description="形象图行 ID（创建图片任务时使用）")
    image_task: CreatorTaskRead | None = Field(None, description="最近一次形象图任务")
    shot_count: int = Field(0, description="本章节内出现的镜头数")


class CreatorProjectRead(BaseModel):
    id: str
    name: str
    style: str
    visual_style: str
    default_video_ratio: str | None = None


class CreatorChapterRead(BaseModel):
    id: str
    index: int
    title: str
    raw_text: str = ""
    status: str


class CreatorSummaryRead(BaseModel):
    shot_count: int = 0
    ready_shot_count: int = Field(0, description="信息确认完成的镜头数")
    keyframe_count: int = 0
    video_done_count: int = 0
    total_seconds: int = 0


class CreatorBoardRead(BaseModel):
    """创作页聚合读模型。"""

    project: CreatorProjectRead
    chapter: CreatorChapterRead
    shots: list[CreatorShotRead] = Field(default_factory=list)
    entities: list[CreatorEntityRead] = Field(default_factory=list)
    summary: CreatorSummaryRead
    divide_task: CreatorTaskRead | None = Field(None, description="最近一次拆分镜任务")
    extract_task: CreatorTaskRead | None = Field(None, description="最近一次角色场景提取任务")


class AutoConfirmResultRead(BaseModel):
    """自动确认结果汇总。"""

    shot_count: int = 0
    linked_candidates: int = Field(0, description="已关联的资产候选数")
    accepted_dialogues: int = Field(0, description="已接受的对白候选数")
    created_entities: int = Field(0, description="新建的实体数")
    skipped_shots: int = Field(0, description="因没有提取结果而标记为无需提取的镜头数")
    ready_shots: int = Field(0, description="处理后处于 ready 的镜头数")


class ProjectOverviewRead(BaseModel):
    """作品列表卡片。"""

    id: str
    name: str
    description: str = ""
    style: str
    visual_style: str
    default_video_ratio: str | None = None
    chapter_count: int = 0
    shot_count: int = 0
    keyframe_count: int = 0
    video_count: int = 0
    cover_url: str | None = Field(None, description="封面：第一张关键帧")
    latest_chapter_id: str | None = Field(None, description="最近编辑的章节，进入创作页时默认打开")
    updated_at: str | None = None
