"""Project/Chapter 的请求响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.studio import ChapterStatus, ProjectStyle, ProjectVisualStyle
from app.services.studio.style_presets import style_label


PROJECT_STYLE_EXAMPLES = [x.value for x in ProjectStyle]


class ProjectBase(BaseModel):
    name: str = Field(..., description="项目名称")
    description: str = Field("", description="项目简介")
    style: ProjectStyle = Field(..., description="题材/风格", examples=PROJECT_STYLE_EXAMPLES)
    visual_style: ProjectVisualStyle = Field(ProjectVisualStyle.live_action, description="画面表现形式")
    seed: int = Field(0, description="随机种子")
    unify_style: bool = Field(True, description="是否统一风格")
    progress: int = Field(0, description="进度百分比（0-100）")
    default_video_ratio: str | None = Field(None, description="项目级默认视频比例；分镜未覆盖时生效")
    style_preset: str | None = Field(
        None,
        description="画面风格预设 key（见 /projects/style-options 的 presets）；给出时 visual_style / style 以预设为准",
    )
    style_prompt: str | None = Field(None, description="自定义风格补充描述，拼在预设提示词之后进入所有提示词")
    stats: dict[str, Any] = Field(default_factory=dict, description="聚合统计（JSON）")


class ProjectCreate(ProjectBase):
    id: str = Field(..., description="项目 ID")


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    style: ProjectStyle | None = Field(None, description="题材/风格", examples=PROJECT_STYLE_EXAMPLES)
    visual_style: ProjectVisualStyle | None = None
    seed: int | None = None
    unify_style: bool | None = None
    progress: int | None = None
    default_video_ratio: str | None = None
    style_preset: str | None = None
    style_prompt: str | None = None
    stats: dict[str, Any] | None = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str

    @computed_field(description="展示用风格名：预设名（如「电影胶片」）或旧题材值（如「真人都市」）")  # type: ignore[prop-decorator]
    @property
    def style_label(self) -> str:
        """页面上只显示风格名，不显示预设 key；与创作板 / 作品列表的 `style_label` 口径一致。"""
        return style_label(self)


class ChapterBase(BaseModel):
    project_id: str = Field(..., description="所属项目 ID")
    index: int = Field(..., description="章节序号（项目内唯一）")
    title: str = Field(..., description="章节标题")
    summary: str = Field("", description="章节摘要")
    raw_text: str = Field("", description="章节原文")
    condensed_text: str = Field("", description="精简原文")
    storyboard_count: int = Field(0, description="分镜数量")
    status: ChapterStatus = Field(ChapterStatus.draft, description="章节状态")


class ChapterCreate(ChapterBase):
    id: str = Field(..., description="章节 ID")


class ChapterUpdate(BaseModel):
    project_id: str | None = None
    index: int | None = None
    title: str | None = None
    summary: str | None = None
    raw_text: str | None = None
    condensed_text: str | None = None
    storyboard_count: int | None = None
    status: ChapterStatus | None = None


class ChapterRead(ChapterBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shot_count: int = Field(0, description="分镜数（shots 条数聚合）")


class StyleOption(BaseModel):
    """通用下拉选项。"""

    value: str = Field(..., description="选项值")
    label: str = Field(..., description="选项展示文案")


class StylePresetRead(BaseModel):
    """一个可直接套用的画面风格预设（新建作品时的风格卡片）。"""

    key: str = Field(..., description="预设 key，写入 Project.style_preset")
    label: str = Field(..., description="卡片标题")
    group: str = Field(..., description="分组：真人实拍 / 动画 / 艺术")
    visual_style: str = Field(..., description="预设对应的画面表现形式（现实 / 动漫）")
    style: str = Field(..., description="预设对应的题材粗分桶")
    prompt: str = Field(..., description="进入提示词的风格描述")
    blurb: str = Field("", description="一句话说明")
    tags: list[str] = Field(default_factory=list, description="卡片小标签")


class ProjectStyleOptionsRead(BaseModel):
    """项目风格候选项。"""

    preset_groups: list[str] = Field(default_factory=list, description="预设分组顺序")
    presets: list[StylePresetRead] = Field(default_factory=list, description="画面风格预设目录")
    default_preset: str | None = Field(None, description="新建作品默认选中的预设 key")
    visual_styles: list[StyleOption] = Field(default_factory=list, description="视觉风格可选项")
    styles_by_visual_style: dict[str, list[StyleOption]] = Field(
        default_factory=dict,
        description="按视觉风格分组的视频风格选项",
    )
    default_style_by_visual_style: dict[str, str] = Field(
        default_factory=dict,
        description="各视觉风格默认视频风格",
    )
