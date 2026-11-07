"""创作模式（Creator Mode）读模型。

为什么存在：创作页是单页五步流程，需要一次请求拿到章节下全部镜头、实体与最近任务状态，
而不是在前端拼十几个接口；这里定义的都是只读聚合结构，不引入新的状态语义。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ReadModel(BaseModel):
    """只读聚合模型基类：带默认值的字段在响应 schema 中仍标记为必填，前端 generated types 不再到处可选。"""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class CreatorTaskRead(_ReadModel):
    """某个资源最近一次生成任务的轻量状态（供卡片展示进度 / 失败原因）。"""

    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="pending / running / streaming / succeeded / failed / cancelled")
    progress: int = Field(0, description="进度 0-100")
    error: str | None = Field(None, description="失败原因（原文，前端负责中文映射）")


class CreatorDialogueLineRead(_ReadModel):
    """镜头对白行（已确认）；带行 ID 以便在分镜卡里直接增删改。"""

    id: int = Field(..., description="对白行 ID（ShotDialogLine.id）")
    speaker: str = Field("", description="说话角色名；旁白为空")
    speaker_character_id: str | None = Field(None, description="说话角色 ID（已关联到角色时）")
    text: str = Field(..., description="台词")


class CreatorImageCandidateRead(_ReadModel):
    """一张可「采用」的图片：历史生成结果或上传图；is_current 表示当前正在用的那张。"""

    file_id: str
    url: str = ""
    task_id: str | None = Field(None, description="来自哪次生成任务；上传图为空")
    created_at: str | None = None
    is_current: bool = False


class CreatorEntityViewRead(_ReadModel):
    """角色的一个视角形象（侧面 / 背面 …），用于多视图参考。"""

    view_angle: str = Field(..., description="LEFT / RIGHT / BACK / THREE_QUARTER …")
    image_id: int
    file_id: str | None = None
    url: str = ""
    task: CreatorTaskRead | None = None


class CreatorShotRead(_ReadModel):
    """创作页分镜卡所需的镜头信息。"""

    id: str
    index: int
    title: str
    script_excerpt: str = ""
    status: str = Field(..., description="shot.status：pending / ready（信息确认状态）")
    duration: int = Field(0, description="时长（秒）")
    camera_shot: str = Field("", description="景别 code（ECU / CU / MCU / MS / MLS / LS / ELS）")
    angle: str = Field("", description="机位角度 code（EYE_LEVEL / HIGH_ANGLE / LOW_ANGLE / BIRD_EYE / DUTCH / OVER_SHOULDER）")
    movement: str = Field("", description="运镜 code（STATIC / PAN / DOLLY_IN …）")
    action_beats: list[str] = Field(default_factory=list, description="动作节拍（按时长平均分配时间码写进视频提示词）")
    description: str = Field("", description="画面描述（首帧提示词；AI 生成后可编辑）")
    dialogue: list[CreatorDialogueLineRead] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    scene_ids: list[str] = Field(default_factory=list)
    prop_ids: list[str] = Field(default_factory=list)
    keyframe_file_id: str | None = Field(None, description="首帧图片文件 ID")
    keyframe_url: str | None = Field(None, description="首帧图片地址")
    keyframe_prompt_task: CreatorTaskRead | None = Field(None, description="最近一次首帧提示词任务")
    keyframe_image_task: CreatorTaskRead | None = Field(None, description="最近一次首帧图片任务")
    keyframe_candidates: list[CreatorImageCandidateRead] = Field(default_factory=list, description="关键帧候选 / 历史（当前在前，最多 8 张）")
    preview_grid_url: str | None = Field(None, description="预演四宫格图片地址")
    preview_grid_task: CreatorTaskRead | None = Field(None, description="最近一次预演四宫格任务")
    audio_file_id: str | None = Field(None, description="配音 / 配乐参考文件 ID")
    audio_url: str | None = Field(None, description="配音 / 配乐参考地址")
    video_file_id: str | None = Field(None, description="生成视频文件 ID")
    video_url: str | None = Field(None, description="生成视频地址")
    video_task: CreatorTaskRead | None = Field(None, description="最近一次视频任务")


class CreatorEntityRead(_ReadModel):
    """创作页角色 / 场景 / 道具 / 服装卡。"""

    type: Literal["character", "scene", "prop", "costume"]
    id: str
    name: str
    description: str = ""
    thumbnail: str = Field("", description="形象 / 参考图地址；无图为空")
    image_id: int | None = Field(None, description="形象图行 ID（创建图片任务时使用）")
    image_file_id: str | None = Field(None, description="形象图文件 ID（作为关键帧 / 视频的参考图）")
    image_task: CreatorTaskRead | None = Field(None, description="最近一次形象图任务")
    shot_count: int = Field(0, description="本章节内出现的镜头数；0 表示本集尚未用到（可能沿用自其它集）")
    shot_ids: list[str] = Field(default_factory=list, description="本章节内出现的镜头 ID")
    image_candidates: list[CreatorImageCandidateRead] = Field(default_factory=list, description="形象 / 参考图候选与历史（当前在前，最多 8 张）")
    views: list[CreatorEntityViewRead] = Field(default_factory=list, description="角色的其它视角形象（侧面 / 背面）")


class CreatorProjectRead(_ReadModel):
    id: str
    name: str
    style: str
    visual_style: str
    default_video_ratio: str | None = None


class CreatorChapterRead(_ReadModel):
    id: str
    index: int
    title: str
    raw_text: str = ""
    status: str


class CreatorSummaryRead(_ReadModel):
    shot_count: int = 0
    ready_shot_count: int = Field(0, description="信息确认完成的镜头数")
    keyframe_count: int = 0
    video_done_count: int = 0
    total_seconds: int = 0


class CreatorBoardRead(_ReadModel):
    """创作页聚合读模型。"""

    project: CreatorProjectRead
    chapter: CreatorChapterRead
    shots: list[CreatorShotRead] = Field(default_factory=list)
    entities: list[CreatorEntityRead] = Field(default_factory=list)
    summary: CreatorSummaryRead
    divide_task: CreatorTaskRead | None = Field(None, description="最近一次拆分镜任务")
    extract_task: CreatorTaskRead | None = Field(None, description="最近一次角色场景提取任务")


class AutoConfirmResultRead(_ReadModel):
    """自动确认结果汇总。"""

    shot_count: int = 0
    linked_candidates: int = Field(0, description="已关联的资产候选数")
    accepted_dialogues: int = Field(0, description="已接受的对白候选数")
    created_entities: int = Field(0, description="新建的实体数")
    skipped_shots: int = Field(0, description="因没有提取结果而标记为无需提取的镜头数")
    ready_shots: int = Field(0, description="处理后处于 ready 的镜头数")


# ---------------------------------------------------------------------------
# 创作页编辑动作（写模型）
# ---------------------------------------------------------------------------

CreatorEntityType = Literal["character", "scene", "prop", "costume"]


class ShotEntityLinksWrite(BaseModel):
    """按类型整体替换镜头「画面里会用到」的实体；为 None 的类型保持不变。"""

    character_ids: list[str] | None = Field(None, description="角色 ID 列表（按画面内顺序）")
    scene_ids: list[str] | None = None
    prop_ids: list[str] | None = None
    costume_ids: list[str] | None = None


class EntityShotsWrite(BaseModel):
    """设置某个实体在本章节内出现的镜头集合（不在列表里的镜头会解除关联）。"""

    shot_ids: list[str] = Field(default_factory=list)


class CreatorEntityCreate(BaseModel):
    """创作页手动新增角色 / 场景 / 道具 / 服装，并可直接挂到若干镜头。"""

    type: CreatorEntityType
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", description="设定描述；会作为形象图提示词的素材")
    shot_ids: list[str] = Field(default_factory=list)


class FileAttachRequest(BaseModel):
    """把已上传的文件（`POST /studio/files/upload` 返回的 id）挂到某个资源上。"""

    file_id: str


class CreatorEntityCreatedRead(_ReadModel):
    type: str
    id: str
    reused: bool = Field(False, description="同名实体已存在（角色按作品、场景 / 道具 / 服装全局唯一），本次沿用而非新建")


class AttachedImageRead(_ReadModel):
    """上传图挂载结果：图片行 ID 与文件 ID。"""

    image_id: int
    file_id: str


class AttachedVideoRead(_ReadModel):
    """上传视频设为镜头成片的结果。"""

    shot_id: str
    file_id: str


class CharacterViewsRequest(BaseModel):
    """派生角色多视图：以当前正面形象为参考生成其它视角。"""

    views: list[Literal["left", "right", "back", "three_quarter"]] = Field(default_factory=lambda: ["left", "back"])


class TaskIdsRead(_ReadModel):
    task_ids: list[str] = Field(default_factory=list)


class TaskIdRead(_ReadModel):
    task_id: str


class PreviewGridRequest(BaseModel):
    """预演四宫格：一张 2×2 图看四个节拍的构图与连续性，比生成视频便宜得多。"""

    ratio: str | None = Field(None, description="图片比例；默认 1:1")


class ShotAudioRead(_ReadModel):
    """镜头的配音 / 配乐参考。"""

    shot_id: str
    file_id: str | None = None


class ProjectOverviewRead(_ReadModel):
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
