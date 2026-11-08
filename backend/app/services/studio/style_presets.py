"""画面风格预设目录。

为什么存在：
- 新建作品时只有「现实 / 动漫」两个画面选项和七个粗粒度题材，远少于主流短剧生成平台（Dreamina、
  可灵、Vidu、海螺等在开头都给十几到几十种可直接套用的「风格 / 滤镜」）。
- 过去风格只以两个枚举值（`visual_style`、`style`）进入提示词，模型拿到的只是「现实，真人都市」这类
  词，画面质感无法稳定；预设把每种风格展开成一段描述介质、镜头、光线、色彩与质感的中文提示词。

职责：
- 维护预设目录（key → 标签 / 分组 / 对应粗分桶 / 风格提示词 / 一句话说明 / 标签）。
- 把作品（`Project`）解析成提示词里用的「画面风格」文字（`resolve_style_text`）与展示用标签
  （`style_label`），所有图片 / 视频 / 剧本提示词统一经此取值。

约束：
- 每个预设都对应一组合法的 `(visual_style, style)` 粗分桶，这样老模板里的 `{{ visual_style }}` 与
  实体表上的 `style` 列继续有值；预设本身只影响提示词与展示，不改变状态语义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.types import ProjectStyle, ProjectVisualStyle

STYLE_GROUP_LIVE = "真人实拍"
STYLE_GROUP_ANIME = "动画"
STYLE_GROUP_ART = "艺术"

STYLE_GROUPS: tuple[str, ...] = (STYLE_GROUP_LIVE, STYLE_GROUP_ANIME, STYLE_GROUP_ART)


@dataclass(frozen=True)
class StylePreset:
    """一个可直接套用的画面风格。

    - `key`：稳定的英文标识，存在 `Project.style_preset`。
    - `visual_style` / `style`：预设对应的粗分桶，创建作品时写回 `Project.visual_style` / `Project.style`。
    - `prompt`：进入提示词的风格描述（介质、镜头、光线、色彩、质感），不含剧情。
    - `blurb`：卡片上的一句话说明；`tags`：卡片上的小标签。
    """

    key: str
    label: str
    group: str
    visual_style: ProjectVisualStyle
    style: ProjectStyle
    prompt: str
    blurb: str
    tags: tuple[str, ...] = field(default_factory=tuple)


_LIVE = ProjectVisualStyle.live_action
_ANIME = ProjectVisualStyle.anime

STYLE_PRESETS: tuple[StylePreset, ...] = (
    # ---------------------------------------------------------------- 真人实拍
    StylePreset(
        key="cinematic_film",
        label="电影胶片",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="真人实拍电影感，35mm 胶片颗粒，浅景深定焦镜头，自然光与现场实用光源混合，低饱和暖调，柔和高光与细腻暗部，电影级调色",
        blurb="最通用的「像电影」质感，适合情感、剧情类短剧。",
        tags=("胶片", "浅景深", "暖调"),
    ),
    StylePreset(
        key="urban_romance",
        label="都市偶像剧",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="现代都市偶像剧质感，明亮通透的高调光，干净柔和的肤色，粉彩与高级灰配色，大光圈浅景深，精致妆造与当季时装，精装公寓与咖啡馆街景",
        blurb="甜宠、霸总、职场恋爱：明亮、干净、好看。",
        tags=("甜宠", "明亮", "时装"),
    ),
    StylePreset(
        key="urban_realism",
        label="都市现实",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="现实主义都市剧，手持跟拍，自然光不补光，真实的生活场景与生活化道具，中性偏冷色调，克制的后期调色，人物肤色真实",
        blurb="家庭、逆袭、社会题材，强调真实感。",
        tags=("手持", "自然光", "真实"),
    ),
    StylePreset(
        key="suspense_noir",
        label="悬疑黑色",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="悬疑黑色电影质感，高对比低调光，深邃的阴影与冷青色调，雨夜街灯与霓虹倒影，百叶窗光影，带压迫感的构图与大量负空间",
        blurb="悬疑、罪案、复仇：暗、冷、有压迫感。",
        tags=("高对比", "冷青", "雨夜"),
    ),
    StylePreset(
        key="ancient_costume",
        label="古装正剧",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_ancient,
        prompt="真人古装正剧，考究的服饰纹样与器物，宫殿庭院与山水实景，柔和逆光与烛光，低饱和、带水墨意味的配色，庄重对称的构图",
        blurb="宫斗、权谋、历史：讲究、庄重。",
        tags=("宫廷", "烛光", "庄重"),
    ),
    StylePreset(
        key="xianxia_fantasy",
        label="仙侠奇幻",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_ancient,
        prompt="真人仙侠奇幻，飘逸的长衫与长发，云海仙山、浮空殿宇、灵光粒子与法术光效，冷暖对撞的梦幻色调，柔焦与体积光",
        blurb="修仙、神话、玄幻：唯美、飘逸、有特效。",
        tags=("仙气", "特效", "梦幻"),
    ),
    StylePreset(
        key="scifi_cyber",
        label="赛博科幻",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_scifi,
        prompt="真人赛博朋克科幻，霓虹青紫与橙红对撞，雨夜高密度都市与全息广告，金属与玻璃反光，电影级暗部与镜头光晕",
        blurb="赛博都市、黑客、未来犯罪。",
        tags=("霓虹", "雨夜", "全息"),
    ),
    StylePreset(
        key="scifi_clean",
        label="近未来科幻",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_scifi,
        prompt="真人近未来科幻，极简冷白色空间与弧形界面，干净的硬光与柔和漫射光结合，科技蓝与银灰配色，精确对称的构图",
        blurb="实验室、太空站、AI 题材：干净、理性。",
        tags=("极简", "冷白", "对称"),
    ),
    StylePreset(
        key="period_retro",
        label="年代复古",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="八九十年代年代剧，暖黄胶片色调与轻微褪色，复古家具、老式街景与年代服装，柔和钨丝灯光，细腻颗粒，怀旧氛围",
        blurb="年代、怀旧、重生回到过去。",
        tags=("怀旧", "暖黄", "褪色"),
    ),
    StylePreset(
        key="documentary",
        label="纪实手持",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="纪录片式真人实拍，手持轻微晃动，完全自然光，生活化场景与非职业演员般的真实感，真实肤色，几乎不做后期调色",
        blurb="伪纪录、vlog 式叙事、社会观察。",
        tags=("纪实", "手持", "无滤镜"),
    ),
    StylePreset(
        key="horror_thriller",
        label="恐怖惊悚",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="恐怖惊悚片质感，极低照度与单一光源（手电、烛火、冷色屏幕光），冷绿或暗红色调，粗颗粒，倾斜与失衡的构图，大量黑暗区域",
        blurb="惊悚、灵异、密室。",
        tags=("低照度", "冷绿", "不安"),
    ),
    StylePreset(
        key="comedy_bright",
        label="轻喜剧",
        group=STYLE_GROUP_LIVE,
        visual_style=_LIVE,
        style=ProjectStyle.real_people_city,
        prompt="轻喜剧风格真人实拍，明亮饱满的色彩，均匀柔和的影棚式布光，活泼的场景布置与撞色服装，清晰干净的画面",
        blurb="搞笑、日常、情景喜剧：明快、饱和。",
        tags=("明快", "饱和", "撞色"),
    ),
    # ---------------------------------------------------------------- 动画
    StylePreset(
        key="anime_2d_daily",
        label="日系二维",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.anime_daily,
        prompt="日系二维动画，干净的线稿与赛璐璐平涂上色，柔和的日光与天空渐变背景，清新明快的配色，角色表情细腻、比例修长",
        blurb="校园、日常、恋爱番的清新二维。",
        tags=("二维", "赛璐璐", "清新"),
    ),
    StylePreset(
        key="anime_action",
        label="热血战斗",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.anime_daily,
        prompt="热血战斗动画，高对比的强阴影与锐利线条，速度线与冲击特效，饱和强烈的色彩，动态夸张的透视与构图",
        blurb="格斗、冒险、少年热血。",
        tags=("热血", "速度线", "高对比"),
    ),
    StylePreset(
        key="anime_ancient",
        label="古风仙侠动画",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.anime_ancient,
        prompt="古风仙侠动画，飘逸的衣袂与长发，云雾仙山与灵光特效，冷暖交织的梦幻色彩，唯美柔光，精致的发饰与服饰纹样",
        blurb="修仙、古风、国风玄幻的二维动画。",
        tags=("古风", "仙侠", "唯美"),
    ),
    StylePreset(
        key="guoman_2d",
        label="国风二维",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.guoman,
        prompt="国风二维动画，工笔线条与水彩晕染融合，雅致低饱和的配色，留白的构图，传统纹样、园林与古建筑元素",
        blurb="雅致、传统、带东方韵味的二维。",
        tags=("国风", "工笔", "留白"),
    ),
    StylePreset(
        key="guoman_3d",
        label="国漫 3D",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.anime_3d,
        prompt="国漫三维动画，写实比例的角色，PBR 材质与电影级布光，细腻的皮肤与布料质感，东方建筑与山水场景，景深与体积光",
        blurb="《凡人修仙传》式的写实三维国漫。",
        tags=("三维", "写实", "东方"),
    ),
    StylePreset(
        key="pixar_3d",
        label="欧美 3D 卡通",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.anime_3d,
        prompt="欧美三维卡通动画，圆润夸张的角色造型与大眼睛，明亮饱和的色彩，柔和的全局光照与次表面散射，温暖幽默的氛围",
        blurb="合家欢、童趣、幽默的三维卡通。",
        tags=("卡通", "圆润", "温暖"),
    ),
    StylePreset(
        key="anime_scifi_mecha",
        label="科幻机甲动画",
        group=STYLE_GROUP_ANIME,
        visual_style=_ANIME,
        style=ProjectStyle.anime_scifi,
        prompt="科幻机甲动画，硬朗的机械线条与金属质感，霓虹与冷蓝光效，宏大的未来都市与宇宙场景，动感的仰拍与倾斜构图",
        blurb="机甲、星际、未来战争。",
        tags=("机甲", "冷蓝", "宏大"),
    ),
    # ---------------------------------------------------------------- 艺术
    StylePreset(
        key="ink_wash",
        label="水墨写意",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.ink_wash,
        prompt="中国水墨写意，墨色浓淡干湿的变化，大量留白，宣纸纹理，点睛的朱砂或青绿淡彩，写意的山水与人物",
        blurb="水墨动画、禅意、山水。",
        tags=("水墨", "留白", "宣纸"),
    ),
    StylePreset(
        key="watercolor_storybook",
        label="水彩绘本",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.art_stylized,
        prompt="手绘水彩绘本风格，湿画法的晕染与纸张纹理，柔和透明的色彩，铅笔底稿痕迹，温暖童趣的造型",
        blurb="童话、治愈、儿童向。",
        tags=("水彩", "绘本", "治愈"),
    ),
    StylePreset(
        key="claymation",
        label="黏土定格",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.art_stylized,
        prompt="黏土定格动画，手工黏土质感与细微指纹痕迹，微缩布景与手工道具，影棚柔光，略带跳帧的定格感",
        blurb="手作感、怪趣、定格动画。",
        tags=("黏土", "定格", "手作"),
    ),
    StylePreset(
        key="pixel_art",
        label="像素复古",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.art_stylized,
        prompt="16 位像素艺术，有限调色板与清晰的像素颗粒，复古游戏画面感，平面化的透视与抖动渐变",
        blurb="复古游戏、怀旧、二次元梗。",
        tags=("像素", "复古", "游戏"),
    ),
    StylePreset(
        key="paper_cut",
        label="剪纸皮影",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.art_stylized,
        prompt="中国剪纸与皮影戏风格，镂空的平面剪影与红纸质感，背光投影的暖光，装饰性的传统纹样，侧面剪影式的人物",
        blurb="民间故事、非遗、节庆。",
        tags=("剪纸", "皮影", "民俗"),
    ),
    StylePreset(
        key="comic_ink",
        label="美式漫画",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.art_stylized,
        prompt="美式漫画风格，粗黑描边与网点阴影，高饱和的分色上色，带分格感的动态构图与夸张透视",
        blurb="超英、街头、强视觉冲击。",
        tags=("漫画", "描边", "网点"),
    ),
    StylePreset(
        key="oil_painting",
        label="油画印象",
        group=STYLE_GROUP_ART,
        visual_style=_ANIME,
        style=ProjectStyle.art_stylized,
        prompt="油画印象派风格，厚涂的可见笔触与颜料肌理，温暖的光影与色彩颤动，古典的构图与柔和边缘",
        blurb="艺术短片、名画感、文艺。",
        tags=("油画", "笔触", "文艺"),
    ),
)

_PRESETS_BY_KEY: dict[str, StylePreset] = {item.key: item for item in STYLE_PRESETS}


def list_style_presets() -> list[StylePreset]:
    """按目录顺序返回全部预设（分组内顺序即展示顺序）。"""
    return list(STYLE_PRESETS)


def get_style_preset(key: str | None) -> StylePreset | None:
    """按 key 查预设；空值或未知 key 返回 None，由调用方决定是报错还是回退粗分桶。"""
    if not key:
        return None
    return _PRESETS_BY_KEY.get(str(key).strip())


def default_style_preset_key() -> str:
    """新建作品弹窗默认选中的预设：目录第一项（电影胶片）。"""
    return STYLE_PRESETS[0].key


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def resolve_style_text(project: Any) -> str:
    """把作品解析成提示词里的「画面风格」文字，供 `{{ style }}` 等模板变量与兜底提示词使用。

    优先级：预设提示词 + 用户自定义补充（用「；」拼接）> 仅自定义补充 > 旧的粗分桶 `style` 枚举值。
    没有预设也没有补充的老作品，返回值与改造前完全一致（例如「真人都市」），老模板不受影响。
    """
    if project is None:
        return ""
    preset = get_style_preset(getattr(project, "style_preset", None))
    extra = str(getattr(project, "style_prompt", None) or "").strip()
    parts = [part for part in (preset.prompt if preset else "", extra) if part]
    if parts:
        return "；".join(parts)
    return _enum_value(getattr(project, "style", None))


def style_label(project: Any) -> str:
    """展示用的风格名：有预设用预设名（如「电影胶片」），否则用旧题材值（如「真人都市」）。"""
    if project is None:
        return ""
    preset = get_style_preset(getattr(project, "style_preset", None))
    if preset is not None:
        return preset.label
    return _enum_value(getattr(project, "style", None))
