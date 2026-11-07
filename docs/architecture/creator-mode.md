# 创作模式（Creator Mode）：当前架构

> 本文记录当前真实生效的实现。推进中的计划见 `docs/plans/creator-mode.md`。

## 页面

| 路径 | 页面 | 职责 |
| --- | --- | --- |
| `/works` | 作品列表 `pages/creator/WorksPage.tsx` | 作品卡片（封面 = 第一张关键帧、集数 / 镜头 / 视频计数）；「新建作品」收集作品名、画面、题材、比例后直接进入创作页 |
| `/works/:projectId?chapter=<id>#<step>` | 创作页 `pages/creator/CreatorPage.tsx` | 一页五步：`script` / `cast` / `storyboard` / `video` / `final`；章节用 `?chapter=`，步骤用 hash；首次打开按进度推断步骤 |
| `/models` `/settings` | 模型管理 / 系统设置 | 运维页面，不参与主流程 |
| `/projects/*` | — | 旧路径，重定向到 `/works` |

侧栏只有 作品 / 模型管理 / 系统设置。任务中心（`pages/aiStudio/components/TaskCenter`）保留为通用任务面板，回跳目标改为创作页对应步骤（`taskCenterMeta.ts`）。

## 创作页结构

```
CreatorPage
├─ 顶栏：返回作品 · 作品名 · 集数 Select · StepBar（五步）
├─ 主区：当前步骤组件（steps/*）
├─ DirectorRail（桌面右栏）：当前步骤建议 + 主按钮 / 进行中任务 / 本集用量
└─ 手机：右栏折叠为固定底部操作条（同一 primary）
```

数据来源只有一个：`useCreatorBoard(chapterId)` 轮询 `GET /api/v1/studio/chapters/{id}/creator-board`。
有任务在跑（divide / extract / 形象图 / 首帧提示词 / 首帧图 / 视频）时每 3 秒刷新；发起任务后强制刷新 12 秒。

## 各步骤与后端调用（`pages/creator/actions.ts`）

| 步骤 | 用户操作 | 后端调用（均为 OpenAPI generated client） |
| --- | --- | --- |
| ① 剧本 | 一键拆分镜 | `ensureChapter`（创建 / 更新章节 raw_text）→ `divide-async(write_to_db)` → 轮询 → `extract-async(script_division)` → 轮询 → `POST chapters/{id}/auto-confirm` |
| ① 剧本 | 重新拆分镜 | 先逐个 `DELETE shots/{id}`，再执行上面的链 |
| ② 角色场景 | 生成形象 | 无图片槽位时 `POST entities/{type}/{id}/images`；`render-prompt` → `image-tasks`（character 走 `/characters/{id}/...`，其余走 `/assets/{type}/{id}/...`） |
| ③ 分镜 | 生成关键帧 | 画面描述为空时 `POST film/tasks/shot-frame-prompts(first)` → 轮询 → 读 `shot-details` 的 `first_frame_prompt`；再 `POST image-tasks/shot/{id}/frame-image-tasks`（参考图 = 镜头关联实体的形象图 `image_file_id`，比例 = 作品默认比例） |
| ③ 分镜 | 编辑 / 增删 | `PATCH shots/{id}`、`PATCH shot-details/{id}`（`first_frame_prompt`、`duration`）、`POST shots` + `auto-confirm`、`DELETE shots/{id}` |
| ④ 视频 | 开始生成 / 重试 | 每镜 `preview-prompt` → `POST film/tasks/video`；有关键帧用 `reference_mode=first` + 首帧 file_id，否则 `text_only` |
| ⑤ 成片 | 连播 / 下载 | 直接使用 `creator-board` 返回的 `video_url`（对象存储公网地址或 `/files/{id}/download`） |

错误透传：任务失败原因来自 `CreatorTaskRead.error`（后端 `ArkApiError` / `ArkTaskFailedError` 原文），前端经 `utils/errorMessage.ts` 映射为中文。

## 后端（service 层 `app/services/studio/creator_flow.py`）

- `auto_confirm_chapter`：对章节内 pending 候选，按名称查找 / 创建角色（`Character.project_id + name`）与场景 / 道具 / 服装（优先本项目已关联，其次全局同名），关联到镜头并 `mark_linked`；对白候选全部 `mark_accepted`；从未提取过的镜头 `set_skip_extraction(True)`；最后 `recompute_shot_status`。幂等。
- `build_creator_board`：聚合镜头（细节、对白行、关联实体 ID、首帧图、生成视频）、实体（最佳形象图、出现镜头数）与各资源最近一次任务（按 `GenerationTaskLink.relation_type` + `relation_entity_id`：`chapter_division` / `script_extraction` / `shot_first_frame_prompt` / `shot_frame_image` / `video` / `character_image` / `character` / `{type}_image`）。
- `build_projects_overview`：作品列表计数与封面。

读模型（`app/schemas/studio/creator.py`）使用 `json_schema_serialization_defaults_required=True`，带默认值的字段在响应 schema 中仍为必填，前端类型不再到处可选。

## 状态语义（未改变）

- `shot.status`：信息提取确认状态，`auto-confirm` 只是把达到 `ready` 的操作自动化。
- 运行时状态来自任务系统（`creator-board` 里的 `*_task`）。
- `video-readiness` 仍可用（创作页不再展示，生成失败时以任务错误为准）。

## 已删除的旧页面

项目工作台、章节管理、分镜列表、分镜编辑页、分镜工作室、资产管理、提示词模板、Agents、文件管理、视频剪辑占位页、使用指南页。对应后端接口全部保留，供创作页与任务中心使用。
