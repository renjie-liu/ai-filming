# 创作模式（Creator Mode）：当前架构

> 本文记录当前真实生效的实现。推进中的计划见 `docs/plans/creator-mode.md`；对照其它短剧平台的旅程调研见 `docs/reference/short-drama-platform-journeys.md`。

## 页面

| 路径 | 页面 | 职责 |
| --- | --- | --- |
| `/works` | 作品列表 `pages/creator/WorksPage.tsx` | 作品卡片（封面 = 第一张关键帧、集数 / 镜头 / 视频计数、删除需二次确认）；「新建作品」收集作品名、画面、题材、比例后直接进入创作页 |
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
└─ 手机：右栏折叠为固定底部操作条（同一 primary）；编辑抽屉全宽
```

数据来源只有一个：`useCreatorBoard(chapterId)` 轮询 `GET /api/v1/studio/chapters/{id}/creator-board`。
有任务在跑（divide / extract / 形象图 / 首帧提示词 / 首帧图 / 视频）时每 3 秒刷新；发起任务后强制刷新 12 秒；编辑动作完成后由步骤组件调用 `refresh()`。

## 各步骤与后端调用（`pages/creator/actions.ts`）

| 步骤 | 用户操作 | 后端调用（均为 OpenAPI generated client） |
| --- | --- | --- |
| ① 剧本 | 一键拆分镜 | `ensureChapter`（创建 / 更新章节 raw_text）→ `divide-async(write_to_db)` → 轮询 → `extract-async(script_division)` → 轮询 → `POST chapters/{id}/auto-confirm` |
| ① 剧本 | 重新拆分镜 | 先逐个 `DELETE shots/{id}`，再执行上面的链 |
| ② 角色场景 | 生成形象 / 换一张 | 角色：`render-prompt` / `image-tasks` 允许 `image_id` 为空，按角色级任务（`relation_type=character`）执行，完成后由执行器创建首张正面 `CharacterImage`；场景 / 道具 / 服装：无槽位时先 `POST entities/{type}/{id}/images`，再 `render-prompt` → `image-tasks` |
| ② 角色场景 | 查看 / 修改提示词再生成 | `render-prompt` 的结果显示在抽屉里，用户改过后以该文本调用 `image-tasks`（`generateEntityImage(entity, prompt)`） |
| ② 角色场景 | 上传自己的图 | 浏览器先缩到 ≤2048px JPEG（`utils/imageResize.ts`，避开 Vercel 4.5 MB 请求体上限）→ `POST files/upload`（multipart，带 `usage_kind`）→ `POST creator/entities/{type}/{id}/image-from-file` |
| ② 角色场景 | 改名称 / 设定、选出现镜头、删除 | `PATCH entities/{type}/{id}`；`PUT creator/chapters/{cid}/entities/{type}/{id}/shots`；`DELETE entities/{type}/{id}` |
| ② 角色场景 | 新增角色 / 场景 / 道具 | `POST creator/chapters/{cid}/entities`（沿用作品题材 / 画面风格，可直接挂到若干镜头） |
| ③ 分镜 | 生成关键帧 | 画面描述为空时 `POST film/tasks/shot-frame-prompts(first)` → 轮询 → 读 `shot-details` 的 `first_frame_prompt`；再 `POST image-tasks/shot/{id}/frame-image-tasks`（参考图 = 镜头关联实体的形象图 `image_file_id`，比例 = 作品默认比例）。抽屉里的「保存并生成」先写回编辑内容再生成 |
| ③ 分镜 | 上传关键帧 | 同上缩图 → `POST files/upload` → `POST creator/shots/{id}/keyframe-from-file`（覆盖 first 槽位） |
| ③ 分镜 | 编辑 | `PATCH shots/{id}`（标题）、`PATCH shot-details/{id}`（`first_frame_prompt`、`duration`、`camera_shot`、`movement`）、`PUT creator/shots/{id}/links`（画面里会用到的角色 / 场景 / 道具）、`shot-dialog-lines` 增删改（对白；新行序号接在现有行之后） |
| ③ 分镜 | 增删镜头 | `POST shots` + `auto-confirm`、`DELETE shots/{id}` |
| ④ 视频 | 开始生成 / 重试 | 每镜 `preview-prompt` → `POST film/tasks/video`；有关键帧用 `reference_mode=first` + 首帧 file_id，否则 `text_only`。Seedance 会拒绝含真人形象的参考图（`InputImageSensitiveContentDetected.PrivacyInformation`，写实风格的 AI 人像也会触发），此时重试按钮改为「改用文字描述重试」并以 `text_only` 重新提交 |
| ⑤ 成片 | 连播 / 下载 | 直接使用 `creator-board` 返回的 `video_url`（对象存储公网地址或 `/files/{id}/download`） |

已在线验证（2026-11-07）：拆分镜 8 s（4 镜）→ 识别 41 s → 自动确认 → 4 张角色形象 → 4 张关键帧 → 4 段视频（1 段首帧参考 + 3 段因真人参考被拒后改文字）全部成功，耗时约 5 分钟。

错误透传：任务失败原因来自 `CreatorTaskRead.error`（后端 `ArkApiError` / `ArkTaskFailedError` 原文），前端经 `utils/errorMessage.ts` 映射为中文；上传超限（413）映射为「图片太大」。

## 后端

### service 层 `app/services/studio/creator_flow.py`

- `auto_confirm_chapter`：对章节内 pending 候选，按名称查找 / 创建角色（`Character.project_id + name`）与场景 / 道具 / 服装（优先本项目已关联，其次全局同名），关联到镜头并 `mark_linked`；对白候选全部 `mark_accepted`；从未提取过的镜头 `set_skip_extraction(True)`；最后 `recompute_shot_status`。幂等。
- `build_creator_board`：聚合镜头（细节含 `camera_shot` / `movement`、对白行含 `id` / `speaker_character_id`、关联实体 ID、首帧图、生成视频）、实体（最佳形象图、`shot_count` 与 `shot_ids`）与各资源最近一次任务（按 `GenerationTaskLink.relation_type` + `relation_entity_id`）。实体范围 = 本章节镜头关联到的 + **项目级已建档的**（其它集的角色、挂到项目的场景 / 道具），后者 `shot_count=0`，排在同类末尾，供沿用。
- `set_shot_entity_links(shot_id, type, ids)`：整体替换镜头某类关联。新增的把同名提取候选 `mark_linked_by_name`；移除的把同名候选标记为 `ignored`（否则下次 auto-confirm 会按名字挂回）；角色先删后建以重排 index。
- `set_entity_shots(chapter_id, type, id, shot_ids)`：按实体设置出现镜头，逐镜调用上面的函数；资产一个镜头都不选时仍保留项目级关联。
- `create_chapter_entity`：复用 `entity_crud.create_entity`（沿用作品 style / visual_style），再挂镜头。
- `attach_entity_image(type, id, file_id)`：角色新建正面 `CharacterImage` 并设为唯一主图；资产图片行按 (实体, 精度, 角度) 唯一，直接写进当前展示那一行。
- `attach_shot_keyframe(shot_id, file_id)`：覆盖 / 新建 `ShotFrameImage(first)`。
- `build_projects_overview`：作品列表计数与封面。

### api 层

- `app/api/v1/routes/studio/chapters.py`：`POST /{id}/auto-confirm`、`GET /{id}/creator-board`。
- `app/api/v1/routes/studio/projects.py`：`GET /overview`。
- `app/api/v1/routes/studio/creator.py`（前缀 `/studio/creator`）：`PUT /shots/{id}/links`、`PUT /chapters/{cid}/entities/{type}/{id}/shots`、`POST /chapters/{cid}/entities`、`POST /entities/{type}/{id}/image-from-file`、`POST /shots/{id}/keyframe-from-file`。service 抛 `CreatorInputError` → 400，其它 `ValueError`（not found）→ 404。

读模型（`app/schemas/studio/creator.py`）使用 `json_schema_serialization_defaults_required=True`，带默认值的字段在响应 schema 中仍为必填，前端类型不再到处可选。

## 状态语义（未改变）

- `shot.status`：信息提取确认状态，`auto-confirm` 只是把达到 `ready` 的操作自动化；用户在创作页解除关联时候选变为 `ignored`，仍属「已处理」。
- 运行时状态来自任务系统（`creator-board` 里的 `*_task`）。
- `video-readiness` 仍可用（创作页不再展示，生成失败时以任务错误为准）。

## 已删除的旧页面

项目工作台、章节管理、分镜列表、分镜编辑页、分镜工作室、资产管理、提示词模板、Agents、文件管理、视频剪辑占位页、使用指南页。对应后端接口全部保留，供创作页与任务中心使用。
