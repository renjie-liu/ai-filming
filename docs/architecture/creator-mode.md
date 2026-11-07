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
| ③ 分镜 | 编辑 | `PATCH shots/{id}`（标题）、`PATCH shot-details/{id}`（`first_frame_prompt`、`duration`、`camera_shot`、`angle`、`movement`、`action_beats`）、`PUT creator/shots/{id}/links`（画面里会用到的角色 / 场景 / 道具）、`shot-dialog-lines` 增删改（对白；新行序号接在现有行之后） |
| ③ 分镜 | 增删镜头 | `POST shots` + `auto-confirm`、`DELETE shots/{id}` |
| ④ 视频 | 开始生成 / 重试 | 每镜 `preview-prompt` → `POST film/tasks/video`。参考方式由 `videoPlan.ts` 按素材自动选：有角色 / 场景形象图 → `reference_mode=reference`（全能参考：形象图 + 关键帧，1–9 张 `images`，`reference_labels` 与之一一对应，提示词开头按 `[Image n]` 点名）；只有关键帧 → `first`；都没有 → `text_only`。Seedance 会拒绝含真人形象的参考图（`InputImageSensitiveContentDetected.PrivacyInformation`，写实风格的 AI 人像也会触发），此时重试按钮改为「改用文字描述重试」并以 `text_only` 重新提交 |
| ④ 视频 | 调整（抽屉） | 参考方式 Segmented（形象参考 / 首帧图 / 仅文字）+ 参考素材勾选（勾选顺序 = `[Image n]`）+ 最终提示词可编辑（改过则按改过的文本提交，后端只补参考块不重写）；「上传自己的视频」→ `uploadVideo`（见下）→ `POST creator/shots/{id}/video-from-file` 设为成片 |
| ⑤ 成片 | 连播 / 下载 | 直接使用 `creator-board` 返回的 `video_url`（对象存储公网地址或 `/files/{id}/download`） |

已在线验证（2026-11-07）：拆分镜 8 s（4 镜）→ 识别 41 s → 自动确认 → 4 张角色形象 → 4 张关键帧 → 4 段视频（1 段首帧参考 + 3 段因真人参考被拒后改文字）全部成功，耗时约 5 分钟。

错误透传：任务失败原因来自 `CreatorTaskRead.error`（后端 `ArkApiError` / `ArkTaskFailedError` 原文），前端经 `utils/errorMessage.ts` 映射为中文；上传超限（413）映射为「图片太大」；对象存储被暂停（`StorageUnavailableError`）映射为「存储已暂停」。

### 视频提示词的组成（`app/services/studio/shot_video_prompt_pack.py` + `generation/video/derive_preview.py`）

```
参考素材（[Image n] 与上传顺序一一对应；…）：     ← reference 模式才有，prepend_reference_block
[Image 1] 角色「雷霆总监」：40岁…
[Image 2] 场景「开放式办公区」
[Image 3] 本镜头关键帧（构图与起始状态）

镜头标题 / 剧本摘录
动作节拍：[0-3s] 三位神走向白板；[3-6s] 雷霆放下马克杯   ← timecoded_beats：多条节拍按时长平均分配
镜头语言：大远景，24mm 超广角；平视机位；镜头缓慢推近…    ← camera_phrase：code → 可执行句式 + 建议焦段
场景 / 角色 / 道具 / 对白摘要 / 连续性要求 / 构图锚点 / 朝向与视线 / 负面约束
```

配置了 DB 视频模板时，模板渲染结果由 `enrich_rendered_video_prompt` 追加「镜头执行」「动作节拍」等约束（模板已写则不重复）。

### 上传（`pages/creator/actions.ts`）

- 图片：浏览器缩到 ≤2048px JPEG → `POST files/upload`（经函数，≤4.5 MB）。
- 视频：`GET files/direct-upload/capabilities` → 存储为 Vercel Blob 时走浏览器直传：`POST files/direct-upload/prepare` 拿 `storage_key` / `pathname` → `@vercel/blob/client` 的 `upload()`（`handleUploadUrl=/files/client-upload`，后端按 `@vercel/blob` 的 `generateClientTokenFromReadWriteToken` 同算法签发客户端令牌，已与 node 实现逐字节比对）→ `POST files/direct-upload/register` 登记为 FileItem；S3 模式退回 `files/upload` 并限制 4 MB。

## 后端

### service 层 `app/services/studio/creator_flow.py`

- `auto_confirm_chapter`：对章节内 pending 候选，按名称查找 / 创建角色（`Character.project_id + name`）与场景 / 道具 / 服装（优先本项目已关联，其次全局同名），关联到镜头并 `mark_linked`；对白候选全部 `mark_accepted`；从未提取过的镜头 `set_skip_extraction(True)`；最后 `recompute_shot_status`。幂等。
- `build_creator_board`：聚合镜头（细节含 `camera_shot` / `movement`、对白行含 `id` / `speaker_character_id`、关联实体 ID、首帧图、生成视频）、实体（最佳形象图、`shot_count` 与 `shot_ids`）与各资源最近一次任务（按 `GenerationTaskLink.relation_type` + `relation_entity_id`）。实体范围 = 本章节镜头关联到的 + **项目级已建档的**（其它集的角色、挂到项目的场景 / 道具），后者 `shot_count=0`，排在同类末尾，供沿用。
- `set_shot_entity_links(shot_id, type, ids)`：整体替换镜头某类关联。新增的把同名提取候选 `mark_linked_by_name`；移除的把同名候选标记为 `ignored`（否则下次 auto-confirm 会按名字挂回）；角色先删后建以重排 index。
- `set_entity_shots(chapter_id, type, id, shot_ids)`：按实体设置出现镜头，逐镜调用上面的函数；资产一个镜头都不选时仍保留项目级关联。
- `create_chapter_entity`：名称规则与自动确认一致（角色按作品唯一，场景 / 道具 / 服装全局唯一 `uq_*_name`），同名已存在则沿用并返回 `reused=true`；否则复用 `entity_crud.create_entity`（沿用作品 style / visual_style）；最后挂镜头。
- `attach_entity_image(type, id, file_id)`：角色新建正面 `CharacterImage` 并设为唯一主图；资产图片行按 (实体, 精度, 角度) 唯一，直接写进当前展示那一行。
- `attach_shot_keyframe(shot_id, file_id)`：覆盖 / 新建 `ShotFrameImage(first)`。
- `attach_shot_video(shot_id, file_id)`：上传的视频设为 `shot.generated_video_file_id`（成片页照常连播）。
- `build_projects_overview`：作品列表计数与封面。

### 视频生成（`app/services/film/generated_video.py` + `generation/video/build_context.py`）

- `reference_mode=reference`：`collect_reference_candidates` 按「角色 → 场景 → 道具 → 服装 → 关键帧」收集有形象图的关联实体（≤9），给每张一条 `[Image n]` 说明；`build_run_args` 把 file_id 转成对象存储公网 URL 放进 `VideoGenerationInput.reference_images`，方舟 payload 里是 `role=reference_image`（URL 直传，不占 64 MB 请求体）。首帧 / 首尾帧与全能参考互斥（契约校验）。
- 其它模式不变：帧图仍以 data URL 传 `first_frame` / `last_frame`。

### 浏览器直传（`app/services/studio/direct_upload.py`，路由 `routes/studio/uploads.py`）

`GET /files/direct-upload/capabilities`、`POST /files/direct-upload/prepare`、`POST /files/client-upload`（`@vercel/blob` handleUpload 协议，裸 JSON 响应）、`POST /files/direct-upload/register`。令牌只对本服务生成的 `uploads/<uuid>/<name>` 路径签发，登记时校验 URL 指向同一路径。

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
