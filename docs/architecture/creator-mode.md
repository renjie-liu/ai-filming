# 创作模式（Creator Mode）：当前架构

> 本文记录当前真实生效的实现。推进中的计划见 `docs/plans/creator-mode.md`；对照其它短剧平台的旅程调研见 `docs/reference/short-drama-platform-journeys.md`。

## 页面

| 路径 | 页面 | 职责 |
| --- | --- | --- |
| `/works` | 作品列表 `pages/creator/WorksPage.tsx` | 作品卡片（封面 = 第一张关键帧、风格名、集数 / 镜头 / 视频计数、删除需二次确认）；「新建作品」收集作品名、画面风格（`StylePresetPicker`：按「真人实拍 / 动画 / 艺术」分组的预设卡片 + 可选的「风格补充」一句话）、比例后直接进入创作页；提交时把预设的 `key` / `visual_style` / `style` 一起写入 |
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
有任务在跑（divide / extract / 形象图 / 角色视图 / 首帧提示词 / 首帧图 / 预演四宫格 / 视频）时每 3 秒刷新；发起任务后强制刷新 12 秒；编辑动作完成后由步骤组件调用 `refresh()`。

## 各步骤与后端调用（`pages/creator/actions.ts`）

| 步骤 | 用户操作 | 后端调用（均为 OpenAPI generated client） |
| --- | --- | --- |
| ① 剧本 | 一句话起草剧本 | `POST script-processing/draft-script-async`（`project_id` / 可选 `chapter_id` / `idea` / `target_seconds`）→ 轮询 → 任务结果 `ScriptDraftResult{title, logline, outline, script_text, notes}` 填进剧本框（`draftScript`）；只写文本，不动已有镜头 |
| ① 剧本 | 一键拆分镜 | `ensureChapter`（创建 / 更新章节 raw_text）→ `divide-async(write_to_db)` → 轮询 → `extract-async(script_division)` → 轮询 → `POST chapters/{id}/auto-confirm` |
| ① 剧本 | 重新拆分镜 | 先逐个 `DELETE shots/{id}`，再执行上面的链 |
| ② 角色场景 | 生成形象 / 换一张 | 角色：`render-prompt` / `image-tasks` 允许 `image_id` 为空，按角色级任务（`relation_type=character`）执行，完成后由执行器创建首张正面 `CharacterImage`；场景 / 道具 / 服装：无槽位时先 `POST entities/{type}/{id}/images`，再 `render-prompt` → `image-tasks` |
| ② 角色场景 | 查看 / 修改提示词再生成 | `render-prompt` 的结果显示在抽屉里，用户改过后以该文本调用 `image-tasks`（`generateEntityImage(entity, prompt)`） |
| ② 角色场景 | 一次生成 1 / 2 / 4 张候选 | `generateEntityImages`：提示词只渲染一次，连发 N 个 `image-tasks`；每个任务落盘的 `GenerationTaskLink.file_id` 就是历史候选，聚合里按「当前 → 新 → 旧 → 上传」给出 `image_candidates`（≤8） |
| ② 角色场景 | 历史候选「采用」/ 回退 | 抽屉里的候选条（`ui.tsx` `CandidateStrip`）点一张 → `POST creator/entities/{type}/{id}/image-from-file`（同 `file_id` 的正面行设主图，否则覆盖当前正面行，不新插行） |
| ② 角色场景 | 生成三视图 | `POST creator/entities/character/{id}/views`（默认 `["left","back"]`）→ 每个视角一个图片任务，以当前正面形象为参考图；结果落在对应 `view_angle` 的 `CharacterImage` 行，聚合为 `views`，抽屉里单独一条显示 |
| ② 角色场景 | 上传自己的图 | 浏览器先缩到 ≤2048px JPEG（`utils/imageResize.ts`，避开 Vercel 4.5 MB 请求体上限）→ `POST files/upload`（multipart，带 `usage_kind`）→ `POST creator/entities/{type}/{id}/image-from-file` |
| ② 角色场景 | 改名称 / 设定、选出现镜头、删除 | `PATCH entities/{type}/{id}`；`PUT creator/chapters/{cid}/entities/{type}/{id}/shots`；`DELETE entities/{type}/{id}` |
| ② 角色场景 | 新增角色 / 场景 / 道具 | `POST creator/chapters/{cid}/entities`（沿用作品题材 / 画面风格，可直接挂到若干镜头） |
| ③ 分镜 | 生成关键帧 | 画面描述为空时 `POST film/tasks/shot-frame-prompts(first)` → 轮询 → 读 `shot-details` 的 `first_frame_prompt`；再 `POST image-tasks/shot/{id}/frame-image-tasks`（参考图 = 镜头关联实体的形象图 `image_file_id`，比例 = 作品默认比例）。抽屉里的「保存并生成」先写回编辑内容再生成 |
| ③ 分镜 | 上传关键帧 | 同上缩图 → `POST files/upload` → `POST creator/shots/{id}/keyframe-from-file`（覆盖 first 槽位） |
| ③ 分镜 | 关键帧历史候选 | 每次首帧图任务的结果都留在任务关联里，聚合为 `keyframe_candidates`；候选条点一张 → `keyframe-from-file` 切回 |
| ③ 分镜 | 预演四宫格 | 抽屉「生成四宫格」先写回节拍 / 镜头语言，再 `POST creator/shots/{id}/preview-grid`（`ratio` = 作品比例）→ 一个图片任务，提示词由 `build_preview_grid_prompt` 按前四条动作节拍 + 镜头语言 + 风格 + 场景 / 角色拼成「2×2 四格连续分镜」，参考图 = 关联实体形象图；结果落在 `ShotFrameImage(key)`，聚合为 `preview_grid_url` / `preview_grid_task`（不计入关键帧数） |
| ③ 分镜 | 编辑 | `PATCH shots/{id}`（标题）、`PATCH shot-details/{id}`（`first_frame_prompt`、`duration`、`camera_shot`、`angle`、`movement`、`action_beats`）、`PUT creator/shots/{id}/links`（画面里会用到的角色 / 场景 / 道具）、`shot-dialog-lines` 增删改（对白；新行序号接在现有行之后） |
| ③ 分镜 | 增删镜头 | `POST shots` + `auto-confirm`、`DELETE shots/{id}` |
| ③ 分镜 | 调整顺序 | 桌面端拖动卡片（HTML5 drag & drop，`reorderIds` 算新顺序）或抽屉里「上移 / 下移」→ `PUT creator/chapters/{cid}/shot-order`（整张顺序表）→ `refresh()` |
| ④ 视频 | 开始生成 / 重试 | 每镜 `preview-prompt` → `POST film/tasks/video`。参考方式由 `videoPlan.ts` 按素材自动选：有角色 / 场景形象图 → `reference_mode=reference`（全能参考：形象图 + 关键帧，1–9 张 `images`，`reference_labels` 与之一一对应，提示词开头按 `[Image n]` 点名）；只有关键帧 → `first`；都没有 → `text_only`。Seedance 会拒绝含真人形象的参考图（`InputImageSensitiveContentDetected.PrivacyInformation`，写实风格的 AI 人像也会触发），此时重试按钮改为「改用文字描述重试」并以 `text_only` 重新提交。例外是方舟的「信任模型产物」规则：同账号近 30 天内由 Seedream 5.0 文生图得到的含人脸原图可直接作为参考图，因此自动配置的默认图片模型优先 Seedream 5.0（`ark_autoconfig`），形象图经本服务原样转存到对象存储后仍被放行（2026-11-08 在生产环境以 R2 上的 Seedream 5.0 形象图 + 全能参考模式实测通过）。关键帧是以形象图为参考的图生图，不在受信范围，中近景里人脸清晰时仍会被拒（错误里给出 `content[k]`）；`run_video_generation_task` 会按方舟 content 顺序找到被点名的那张图自动去掉（参考图则重编号 `[Image n]`，帧图则退回纯文字 + 剩余参考图）后立即重试，最多 4 次，被拒发生在生成前不计费；成功后把去掉的图记在任务结果 `dropped_references`，创作板 `video_task.note` 显示「视频平台拒绝了含真人形象的参考图（本镜头关键帧），已自动去掉后生成」 |
| ④ 视频 | 调整（抽屉） | 参考方式 Segmented（形象参考 / 首帧图 / 仅文字）+ 参考素材勾选（勾选顺序 = `[Image n]`；角色的侧面 / 背面视图紧跟其正面之后列出，标「同一人」）+ 最终提示词可编辑（改过则按改过的文本提交，后端只补参考块不重写）；「上传自己的视频」→ `uploadVideo`（见下）→ `POST creator/shots/{id}/video-from-file` 设为成片 |
| ④ 视频 | 配音 / 配乐参考 | 「上传配音 / 配乐」→ `uploadMedia`（与视频同一条直传路径，`usage_kind=reference_audio`）→ `POST creator/shots/{id}/audio-from-file`；镜头有音频时确认单标「+ 音频」，预览 / 提交都带 `audio_file_id`，提示词参考块多一行 `[Audio 1] 配音 / 配乐参考…`，payload 多一项 `role=reference_audio`（公网 URL）；「移除」→ `DELETE creator/shots/{id}/audio` |
| ④ 视频 | 承接上一镜 / 逐镜串行 | 确认单上的「承接上一镜」开关（默认开）：`startSequential` 按镜头顺序一镜一镜提交，每镜 `preview-prompt` → `tasks/video` → `pollTask`（4 s 轮询、单镜 12 分钟上限）→ 重新拉创作板再排下一镜，头部显示「第 n / N 镜：标题」；`videoPlan.ts` 把上一镜的 `last_frame_url` 作为一条 `kind=continuity` 的参考图插在关键帧之前（说明文字 `CONTINUITY_REFERENCE_LABEL`：承接光线、时间、场景布置与人物站位，本镜按新的景别与运镜重新构图），有它时参考方式为 `reference`。关掉开关回到原来的并发提交且不带承接参考（`planFor(..., continuity=false)`）。单镜「重试」也带承接参考 |
| ⑤ 成片 | 连播 / 下载 | 直接使用 `creator-board` 返回的 `video_url`（对象存储公网地址或 `/files/{id}/download`）；默认逐镜连播并预加载下一段 |
| ⑤ 成片 | 合成预览 | 「合成预览」用与导出相同的 ffmpeg.wasm 流程拼成一个 Blob（不下载），播放器切到整集连续播放；字幕由 `buildVtt` 把对白按镜头时长排成 WebVTT，以 `<track kind="subtitles" default>` 挂在 `<video crossOrigin="anonymous">` 上。镜头顺序 / 视频文件变化时（`clipsKey`）预览自动失效需重新合成；「下载整集 mp4」直接复用该 Blob，不再二次拼接；「逐镜播放」/「回到整集预览」切换两种播放方式 |
| ⑤ 成片 | 合成导出 | 纯前端（`pages/creator/exportEpisode.ts`）：ffmpeg.wasm 内核从本站 `/ffmpeg/`（构建时由 `vite-plugin-static-copy` 从 `@ffmpeg/core/dist/esm` 复制，约 31 MB；必须用 ESM 版，Vite 把 `@ffmpeg/ffmpeg` 的 worker 打成 module worker，`importScripts` 不可用）加载 → `fetchFile` 逐段下载（Vercel Blob 带 `access-control-allow-origin: *`）→ `concat` demuxer `-c copy` 拼接（参数不一致时退回 libx264 重编码）→ 浏览器下载 `<作品>-第N集.mp4`。「字幕 .srt」按镜头时长把各镜对白平均分配时间码（`buildSrt`），不烧进视频 |

已在线验证（2026-11-07）：拆分镜 8 s（4 镜）→ 识别 41 s → 自动确认 → 4 张角色形象 → 4 张关键帧 → 4 段视频（1 段首帧参考 + 3 段因真人参考被拒后改文字）全部成功，耗时约 5 分钟。

错误透传：任务失败原因来自 `CreatorTaskRead.error`（后端 `ArkApiError` / `ArkTaskFailedError` 原文），前端经 `utils/errorMessage.ts` 映射为中文；上传超限（413）映射为「图片太大」；对象存储被暂停（`StorageUnavailableError`）映射为「存储已暂停」。

### 视频提示词的组成（`app/services/studio/shot_video_prompt_pack.py` + `generation/video/derive_preview.py`）

```
参考素材（[Image n] 与上传顺序一一对应；…）：     ← reference 模式或带音频时才有，prepend_reference_block
[Image 1] 角色「雷霆总监」：40岁…
[Image 2] 角色「雷霆总监」左侧面（同一人）          ← 前端把角色视图一并点名
[Image 3] 场景「开放式办公区」
[Image 4] 本镜头关键帧（构图与起始状态）
[Audio 1] 配音 / 配乐参考：按它的节奏、情绪与声音特征生成，台词口型与之对齐   ← 有 audio_file_id 时

镜头标题 / 剧本摘录
动作节拍：[0-3s] 三位神走向白板；[3-6s] 雷霆放下马克杯   ← timecoded_beats：多条节拍按时长平均分配
镜头语言：大远景，24mm 超广角；平视机位；镜头缓慢推近…    ← camera_phrase：code → 可执行句式 + 建议焦段
场景 / 角色 / 道具 / 对白摘要 / 连续性要求 / 构图锚点 / 朝向与视线 / 负面约束
```

配置了 DB 视频模板时，模板渲染结果由 `enrich_rendered_video_prompt` 追加「镜头执行」「动作节拍」等约束（模板已写则不重复）。

### 上传（`pages/creator/actions.ts`）

- 图片：浏览器缩到 ≤2048px JPEG → `POST files/upload`（经函数，≤4.5 MB）。
- 视频 / 音频（`uploadMedia`）：`GET files/direct-upload/capabilities` 返回 `direct = vercel_blob | s3 | null` → `POST files/direct-upload/prepare`（带 `filename` / `content_type`）拿 `storage_key` / `pathname`：
  - `vercel_blob`：`@vercel/blob/client` 的 `upload()`（`handleUploadUrl=/files/client-upload`，后端按 `@vercel/blob` 的 `generateClientTokenFromReadWriteToken` 同算法签发客户端令牌，已与 node 实现逐字节比对）；
  - `s3`（Cloudflare R2 / AWS / MinIO）：prepare 额外返回预签名 `upload_url`（boto3 本地签名，1 小时有效，Content-Type 参与签名）与 `public_url`，浏览器 `fetch(upload_url, PUT)` 直接写桶，桶需允许跨域 PUT（启动时 `ensure_storage_ready` 尽力写入 CORS 规则）；
  - 之后 `POST files/direct-upload/register` 登记为 FileItem（按扩展名判定 image / video / audio；音频为 mp3 / wav / m4a / aac）。Blob 模式校验 URL 指向 blob.vercel-storage.com 上同一路径；S3 模式校验 URL 等于后端计算的公网 URL 并 HeadObject 确认对象已上传。无直传后端时退回 `files/upload` 并限制 4 MB。

## 后端

### service 层 `app/services/studio/creator_flow.py`

- `auto_confirm_chapter`：对章节内 pending 候选，按名称查找 / 创建角色（`Character.project_id + name`）与场景 / 道具 / 服装（优先本项目已关联，其次全局同名），关联到镜头并 `mark_linked`；对白候选全部 `mark_accepted`；从未提取过的镜头 `set_skip_extraction(True)`；最后 `recompute_shot_status`。幂等。
- `build_creator_board`：聚合镜头（细节含 `camera_shot` / `movement`、对白行含 `id` / `speaker_character_id`、关联实体 ID、首帧图、生成视频）、实体（最佳形象图、`shot_count` 与 `shot_ids`）与各资源最近一次任务（按 `GenerationTaskLink.relation_type` + `relation_entity_id`）。实体范围 = 本章节镜头关联到的 + **项目级已建档的**（其它集的角色、挂到项目的场景 / 道具），后者 `shot_count=0`，排在同类末尾，供沿用。
  - **历史候选**（`_task_files` + `_candidate_rows`）：不新建表，直接读任务关联里 `file_id` 非空的行。角色取 `relation_type=character`（角色级任务）与正面行的 `character_image` 任务；资产取 `{type}_image`；关键帧取 first 帧行的 `shot_frame_image`。顺序：当前用的那张（`is_current`）→ 历史新 → 旧 → 其它图片行里的上传图，最多 8 张。
  - **角色视图**：非正面角度的 `CharacterImage` 行聚合为 `views`（`view_angle` 大写 code、`file_id`、该行最近任务），不参与「最佳形象图」的挑选。
  - **预演四宫格**：`ShotFrameImage(key)` 行 → `preview_grid_url` / `preview_grid_task`；不计入 `keyframe_count`。
  - **音频参考**：`FileUsage.usage_kind=reference_audio` 的最近一条 → `audio_file_id` / `audio_url`（镜头表本身没有音频字段，用途表即关联）。
- `set_shot_entity_links(shot_id, type, ids)`：整体替换镜头某类关联。新增的把同名提取候选 `mark_linked_by_name`；移除的把同名候选标记为 `ignored`（否则下次 auto-confirm 会按名字挂回）；角色先删后建以重排 index。
- `set_entity_shots(chapter_id, type, id, shot_ids)`：按实体设置出现镜头，逐镜调用上面的函数；资产一个镜头都不选时仍保留项目级关联。
- `create_chapter_entity`：名称规则与自动确认一致（角色按作品唯一，场景 / 道具 / 服装全局唯一 `uq_*_name`），同名已存在则沿用并返回 `reused=true`；否则复用 `entity_crud.create_entity`（沿用作品 style / visual_style）；最后挂镜头。
- `attach_entity_image(type, id, file_id)`：所有图片表都按 (实体, 精度, 角度) 唯一（`uq_*_images_quality_angle`），所以不会为同一角度插第二行：角色已有同文件的正面行 → 设主图（「采用」历史候选）；否则把文件写进当前正面行并设主图；没有正面行才新建。资产直接写进当前展示那一行。历史文件仍在任务关联里，覆盖不丢候选。
- `attach_shot_keyframe(shot_id, file_id)`：覆盖 / 新建 `ShotFrameImage(first)`（也是关键帧「采用」历史候选的入口）。
- `attach_shot_video(shot_id, file_id)`：上传的视频设为 `shot.generated_video_file_id`（成片页照常连播）。
- `generate_character_views(character_id, views)`：要求已有正面形象（否则 `CreatorInputError`）；以角色级提示词（`build_character_image_base_draft` + `derive_asset_image_preview`）加「视角要求：…与参考图是同一个人」为提示词、正面图为参考图，每个视角一个 `create_image_task_and_link(relation_type=character_image, purpose=character_view)`，槽位为对应 `view_angle` 的 `CharacterImage`（`file_id` 可空，已有则复用）。
- `generate_preview_grid(shot_id, ratio)`：`build_shot_video_prompt_pack` → `build_preview_grid_prompt`；参考图 = `get_shot_assets_overview` 里已关联且有图的实体；复用 `generation/frame` 的 base / context / submission 组装；槽位 `ShotFrameImage(key)`；任务 `purpose=storyboard_preview`，默认 `1:1`。
- `attach_shot_audio(shot_id, file_id | None)`：删掉镜头已有的 `reference_audio` 用途记录；传入文件必须是 `FileType.audio`，再写一条 `sync_usage_from_shot_context(usage_kind=reference_audio)`；`None` 即清除。
- `reorder_chapter_shots(chapter_id, shot_ids)`：`shot_ids` 必须恰好是本章节全部镜头各一次（否则 `CreatorInputError`）；序号在章节内唯一（`uq_shots_chapter_index`），先全部写成负数再按新顺序写 1..n，两次 flush，避免中途撞唯一约束。

### 一句话起草剧本（`app/chains/agents/script_drafter_agent.py` + `script_processing_tasks.py` / `script_processing_worker.py`）

- `ScriptDrafterAgent`：系统提示词规定输出格式与分镜 / 提取 Agent 的期望一致（首行 `【第N集】标题`、「地点，时间。」场景行、角色首次出场括号里写外貌服装、「角色名：台词」一行一句、动作只写看得见的事、按目标时长控制篇幅），输出 `ScriptDraftResult`；`_normalize` 兼容包裹层、`script` 等别名字段与字符串大纲。
- 任务：`task_kind=script_draft`、`relation_type=script_draft`、关联到章节（无章节时关联作品）；`create_script_draft_task` 在创建时把作品 `style` / `visual_style` 与章节集数放进 `run_args`，worker（`ScriptDraftTaskExecutor`，thinking 模型）不再回查；同一关联上有活动任务时复用。结果只放在任务 `result` 里，由前端填入剧本框，不写章节 `raw_text`（用户改完点拆分镜时才写）。
- `build_projects_overview`：作品列表计数与封面。

### 视频生成（`app/services/film/generated_video.py` + `generation/video/build_context.py`）

- `reference_mode=reference`：`collect_reference_candidates` 按「角色 → 场景 → 道具 → 服装 → 关键帧」收集有形象图的关联实体（≤9），给每张一条 `[Image n]` 说明；`build_run_args` 把 file_id 转成对象存储公网 URL 放进 `VideoGenerationInput.reference_images`，方舟 payload 里是 `role=reference_image`（URL 直传，不占 64 MB 请求体）。首帧 / 首尾帧与全能参考互斥（契约校验）。
- `audio_file_id`：任一模式都可带。`build_video_context` 记录到 `VideoGenerationContext.audio_file_id`，`prepend_reference_block(audio=True)` 在参考块末尾加 `[Audio 1]` 行（用户改过的提示词里已有 `[Audio 1]` 则不加）；`file_id_to_audio_url` 要求文件类型为 audio 且有公网 URL，放进 `VideoGenerationInput.reference_audio`，方舟 payload 为 `{"type":"audio_url","role":"reference_audio","audio_url":{"url":…}}`。该 payload 形状来自 Seedance 2.x 文档 / CLI，尚未用真实任务验证（Blob 存储恢复后补）。
- 其它模式不变：帧图仍以 data URL 传 `first_frame` / `last_frame`。
- **镜头衔接（承接上一镜）**：`video_payload.supports_last_frame(model)` 对支持的 Seedance 模型在 payload 里带 `return_last_frame: true`；`video_generation_tasks` 轮询到成功时把 `content.last_frame_url`（方舟给的 24 小时有效 jpeg，无水印）放进 `VideoGenerationResult.last_frame_url`；`persist_generated_video_to_shot` 随后调 `persist_last_frame_to_shot` 原样转存到对象存储（`generated-images/shot_last_frame/{shot_id}`）并写入 / 覆盖 `ShotFrameImage(frame_type=last)`（用途 `shot_frame`），转存失败只记日志，不影响视频落库。`build_context.collect_reference_candidates(include_continuity=True)` 在「角色 → 场景 → 道具 → 服装」之后、关键帧之前插入 `previous_shot_last_frame_file_id`（同章节 `index-1` 镜头的 last 帧），说明文字 `CONTINUITY_REFERENCE_LABEL`。创作板给每个镜头带 `last_frame_file_id` / `last_frame_url`，前端 `videoPlan.ts` 用同样的顺序构建参考清单，两边一致。方舟把同账号近 30 天内 Seedance 视频的尾帧视为受信产物，含人脸的尾帧作参考图不触发 `PrivacyInformation`。

### 画面风格预设（`app/services/studio/style_presets.py`）

- 目录 `STYLE_PRESETS`：26 个预设分三组（真人实拍 12 / 动画 7 / 艺术 7），每个带 `key`、标签、分组、粗分桶 `(visual_style, style)`、风格提示词（介质、镜头、光线、色彩、质感，不含剧情）、一句话说明与标签。`ProjectStyle` 为此新增 `动漫日常` / `动漫古风` / `艺术风格` 三个粗分桶，`_build_project_style_options` 把它们归到「动漫」。
- `Project` 新增 `style_preset`（key，可空）与 `style_prompt`（用户补充，可空）。`resolve_style_text(project)`：预设提示词 +「；」+ 补充 → 仅补充 → 旧 `style` 枚举值；没有预设也没有补充的老作品输出与改造前完全一致。`style_label(project)`：预设名或旧题材值，创作板 `CreatorProjectRead` / 作品卡 `ProjectOverviewRead` / `ProjectRead`（计算字段）都带。
- 所有提示词统一经 `resolve_style_text` 取值，老模板不用改——`{{ style }}` 变量直接拿到整段风格描述：关键帧（`shot_frame_prompt_tasks`）、视频提示词包（`shot_video_prompt_pack.style`，含兜底提示词与预演四宫格）、形象图（`asset_image/build_base.py`：角色按 `project_id`、场景 / 道具 / 服装经 `Project*Link` 找到首个所属作品；作品没有预设时沿用实体自身的 `style` 列）、一句话起草剧本（`run_args.style`）。实体表上的 `style` / `visual_style` 列仍存粗分桶，供筛选与老模板的 `{{ visual_style }}`。

### 启动建表与补列（`app/deploy_bootstrap.py`）

`ensure_schema` 以表结构指纹判断模型是否变化，变化时 `create_all` 建缺失的表，再跑 `add_missing_columns`：对比模型与库里已有表，用方言的 DDL 编译器生成列定义，`ALTER TABLE … ADD COLUMN` 补上新增的可空列或带服务端默认值的列；非空且只有 Python 侧默认值的列记 warning 跳过，留给人工迁移。项目没有 Alembic，这是新增列在老库上生效的唯一路径。

### 浏览器直传（`app/services/studio/direct_upload.py`，路由 `routes/studio/uploads.py`）

`GET /files/direct-upload/capabilities`、`POST /files/direct-upload/prepare`、`POST /files/client-upload`（`@vercel/blob` handleUpload 协议，裸 JSON 响应，仅 Blob 模式）、`POST /files/direct-upload/register`。凭证（Blob 客户端令牌 / S3 预签名 PUT）只对本服务生成的 `uploads/<uuid>/<name>` 路径签发，登记时校验 URL 指向同一对象（S3 模式还 HeadObject 确认存在）。

### 对象存储（`app/core/storage.py`）

`storage_backend()`：配置了 `S3_BUCKET_NAME` 为 `s3`，否则有 Blob 令牌为 `vercel_blob`。S3 路径对 Cloudflare R2 自动适配（端点 `*.r2.cloudflarestorage.com`：region `auto`、path-style、关闭 boto3 默认 CRC 校验、建桶不带 LocationConstraint）；对象公网 URL 为 `S3_PUBLIC_BASE_URL/<key>`（key 按 RFC 3986 转义）。`init_storage()` 建桶并写入「任意来源 GET/HEAD/PUT」的 CORS 规则（直传与合成导出 fetch 片段都要它），Vercel 上由 `deploy_bootstrap.ensure_storage_ready` 在冷启动时尽力执行，令牌无桶级权限时记为 error 不阻断。`/_deploy/status` 的 `storage` 字段给出后端、桶、端点主机、直传方式与一次 HeadBucket 探测结果。

### api 层

- `app/api/v1/routes/studio/chapters.py`：`POST /{id}/auto-confirm`、`GET /{id}/creator-board`。
- `app/api/v1/routes/studio/projects.py`：`GET /overview`；`GET /style-options` 增加 `preset_groups` / `presets`（`StylePresetRead`）/ `default_preset`；`POST` / `PATCH` 带 `style_preset` 时校验 key（未知 → 400 `unknown style_preset`）并以预设的粗分桶覆盖 `visual_style` / `style`，再做原有的组合校验。
- `app/api/v1/routes/studio/creator.py`（前缀 `/studio/creator`）：`PUT /shots/{id}/links`、`PUT /chapters/{cid}/entities/{type}/{id}/shots`、`POST /chapters/{cid}/entities`、`POST /entities/{type}/{id}/image-from-file`、`POST /shots/{id}/keyframe-from-file`、`POST /shots/{id}/video-from-file`、`POST /entities/character/{id}/views`（→ `task_ids`）、`POST /shots/{id}/preview-grid`（→ `task_id`）、`POST /shots/{id}/audio-from-file`、`DELETE /shots/{id}/audio`。service 抛 `CreatorInputError` → 400，其它 `ValueError`（not found）→ 404。
- `app/api/v1/routes/film/video_request.py`：`VideoGenerationTaskRequest` 增加 `audio_file_id`；`preview-prompt` 与 `tasks/video` 都接收。
- `app/api/v1/routes/script_processing.py`：`POST /draft-script-async`（`ScriptDraftRequest`，`idea` 2–2000 字、`target_seconds` 15–600）→ `AsyncTaskCreateRead`。
- `app/api/v1/routes/studio/creator.py` 另有 `PUT /chapters/{cid}/shot-order`（`ShotOrderWrite{shot_ids}`）。

### 部署路由（`vercel.json`）

Vercel Services 下静态 `web` 服务不会自己做 SPA 回退，`destination.path` 与服务级 `request.path` transform 都不改变静态文件查找；因此第一条顶层 rewrite 把所有非 `/api/`、非文档、非静态资源（`/assets/`、`env.js`、`logo.svg`、`mockServiceWorker.js`）的路径改写为 `/index.html`，再经 `/(.*)` → `web` 服务命中。直接打开 / 刷新 `/works`、`/works/:id`、`/models` 都能加载应用。

读模型（`app/schemas/studio/creator.py`）使用 `json_schema_serialization_defaults_required=True`，带默认值的字段在响应 schema 中仍为必填，前端类型不再到处可选。

## 状态语义（未改变）

- `shot.status`：信息提取确认状态，`auto-confirm` 只是把达到 `ready` 的操作自动化；用户在创作页解除关联时候选变为 `ignored`，仍属「已处理」。
- 运行时状态来自任务系统（`creator-board` 里的 `*_task`）。
- `video-readiness` 仍可用（创作页不再展示，生成失败时以任务错误为准）。

## 已删除的旧页面

项目工作台、章节管理、分镜列表、分镜编辑页、分镜工作室、资产管理、提示词模板、Agents、文件管理、视频剪辑占位页、使用指南页。对应后端接口全部保留，供创作页与任务中心使用。
