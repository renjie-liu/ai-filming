"""Project CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.dependencies import get_db
from app.models.studio import Project
from app.models.types import ProjectStyle, ProjectVisualStyle
from app.schemas.common import ApiResponse, PaginatedData, created_response, empty_response, paginated_response, success_response
from app.services.common import (
    create_and_refresh,
    delete_if_exists,
    entity_already_exists,
    entity_not_found,
    ensure_not_exists,
    flush_and_refresh,
    get_or_404,
    patch_model,
)
from app.schemas.studio.creator import ProjectOverviewRead
from app.services.studio.creator_flow import build_projects_overview
from app.schemas.studio.projects import (
    ProjectCreate,
    ProjectRead,
    ProjectStyleOptionsRead,
    ProjectUpdate,
    StyleOption,
    StylePresetRead,
)
from app.services.studio.style_presets import (
    STYLE_GROUPS,
    default_style_preset_key,
    get_style_preset,
    list_style_presets,
)

router = APIRouter()

PROJECT_ORDER_FIELDS = {"name", "created_at", "updated_at", "progress"}


def _build_project_style_options() -> tuple[dict[ProjectVisualStyle, list[ProjectStyle]], dict[ProjectVisualStyle, ProjectStyle]]:
    """按画面表现形式（现实 / 动漫）归类题材粗分桶：`real_people_*` 归现实，其余（动漫、国漫、水墨、艺术化）归动漫。"""
    mapping: dict[ProjectVisualStyle, list[ProjectStyle]] = {key: [] for key in ProjectVisualStyle}
    for item in ProjectStyle:
        if item.name.startswith("real_people_"):
            mapping[ProjectVisualStyle.live_action].append(item)
            continue
        if item.name.startswith("anime_") or item.name in {"guoman", "ink_wash", "art_stylized"}:
            mapping[ProjectVisualStyle.anime].append(item)
            continue
    defaults: dict[ProjectVisualStyle, ProjectStyle] = {
        visual: styles[0]
        for visual, styles in mapping.items()
        if styles
    }
    return mapping, defaults


def _apply_style_preset(update_data: dict) -> None:
    """请求里带 `style_preset` 时校验 key 并用预设的粗分桶覆盖 `visual_style` / `style`，保证三者一致。

    未知 key 抛 ValueError（由路由转成 400）；`style_preset=None` 表示清除预设，不改动其它字段。
    """
    if "style_preset" not in update_data:
        return
    key = update_data.get("style_preset")
    if key is None:
        return
    preset = get_style_preset(key)
    if preset is None:
        raise ValueError(f"unknown style_preset: {key}")
    update_data["style_preset"] = preset.key
    update_data["visual_style"] = preset.visual_style
    update_data["style"] = preset.style


def _validate_project_style_combo(*, visual_style: ProjectVisualStyle, style: ProjectStyle) -> None:
    mapping, _defaults = _build_project_style_options()
    allowed = mapping.get(visual_style, [])
    if style not in allowed:
        raise ValueError(
            f"style is not allowed for visual_style: visual_style={visual_style.value}, "
            f"style={style.value}, allowed={[item.value for item in allowed]}"
        )


@router.get(
    "/overview",
    response_model=ApiResponse[list[ProjectOverviewRead]],
    summary="创作模式：作品列表（含章节 / 镜头 / 关键帧 / 视频计数与封面）",
)
async def list_projects_overview(db: AsyncSession = Depends(get_db)) -> ApiResponse[list[ProjectOverviewRead]]:
    return success_response(await build_projects_overview(db))


@router.get(
    "/style-options",
    response_model=ApiResponse[ProjectStyleOptionsRead],
    summary="获取项目风格候选项",
)
async def get_project_style_options(
) -> ApiResponse[ProjectStyleOptionsRead]:
    mapping, defaults = _build_project_style_options()
    data = ProjectStyleOptionsRead(
        preset_groups=list(STYLE_GROUPS),
        presets=[
            StylePresetRead(
                key=item.key,
                label=item.label,
                group=item.group,
                visual_style=item.visual_style.value,
                style=item.style.value,
                prompt=item.prompt,
                blurb=item.blurb,
                tags=list(item.tags),
            )
            for item in list_style_presets()
        ],
        default_preset=default_style_preset_key(),
        visual_styles=[StyleOption(value=x.value, label=x.value) for x in ProjectVisualStyle],
        styles_by_visual_style={
            visual.value: [StyleOption(value=style.value, label=style.value) for style in styles]
            for visual, styles in mapping.items()
        },
        default_style_by_visual_style={visual.value: style.value for visual, style in defaults.items()},
    )
    return success_response(data)


@router.get(
    "",
    response_model=ApiResponse[PaginatedData[ProjectRead]],
    summary="项目列表（分页）",
)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ProjectRead]]:
    stmt = select(Project)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Project.name, Project.description])
    stmt = apply_order(stmt, model=Project, order=order, is_desc=is_desc, allow_fields=PROJECT_ORDER_FIELDS, default="created_at")
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response([ProjectRead.model_validate(x) for x in items], page=page, page_size=page_size, total=total)


@router.post(
    "",
    response_model=ApiResponse[ProjectRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建项目",
)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectRead]:
    await ensure_not_exists(
        db,
        Project,
        body.id,
        detail=entity_already_exists("Project"),
    )
    data = body.model_dump()
    try:
        _apply_style_preset(data)
        _validate_project_style_combo(visual_style=data["visual_style"], style=data["style"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    obj = await create_and_refresh(db, Project(**data))
    return created_response(ProjectRead.model_validate(obj))


@router.get(
    "/{project_id}",
    response_model=ApiResponse[ProjectRead],
    summary="获取项目",
)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectRead]:
    obj = await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    return success_response(ProjectRead.model_validate(obj))


@router.patch(
    "/{project_id}",
    response_model=ApiResponse[ProjectRead],
    summary="更新项目",
)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectRead]:
    obj = await get_or_404(db, Project, project_id, detail=entity_not_found("Project"))
    update_data = body.model_dump(exclude_unset=True)
    try:
        _apply_style_preset(update_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    visual_style = update_data.get("visual_style", obj.visual_style)
    style = update_data.get("style", obj.style)
    if visual_style is not None and style is not None:
        try:
            _validate_project_style_combo(visual_style=visual_style, style=style)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    patch_model(obj, update_data)
    await flush_and_refresh(db, obj)
    return success_response(ProjectRead.model_validate(obj))


@router.delete(
    "/{project_id}",
    response_model=ApiResponse[None],
    summary="删除项目",
)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await delete_if_exists(db, Project, project_id)
    return empty_response()
