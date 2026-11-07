import {
  FilmService,
  OpenAPI,
  ScriptProcessingService,
  StudioChaptersService,
  StudioCreatorService,
  StudioEntitiesService,
  StudioFilesService,
  StudioImageTasksService,
  StudioShotDetailsService,
  StudioShotDialogLinesService,
  StudioShotsService,
} from '../../services/generated'
import type {
  CameraAngle,
  CameraMovement,
  CameraShotType,
  ChapterRead,
  CreatorBoardRead,
  CreatorDialogueLineRead,
  CreatorEntityRead,
  CreatorShotRead,
  ShotDetailUpdate,
  ShotLinkedAssetItem,
  VideoGenerationTaskRequest,
} from '../../services/generated'
import { downscaleImage } from '../../utils/imageResize'
import { assertSucceeded, pollTask } from './taskPolling'

/**
 * 创作页的业务动作：把多个后端任务串成用户眼中的「一步」。
 *
 * 为什么存在：用户只看到「一键拆分镜」「生成关键帧」「生成视频」三个按钮，
 * 背后分别是 2–3 个任务 / 接口；这里负责编排与错误透传，页面组件只管展示。
 * 所有调用都走 OpenAPI generated client。
 */

export type VideoRatio = VideoGenerationTaskRequest['ratio']

export function resolveRatio(board: CreatorBoardRead | null): VideoRatio {
  const raw = board?.project.default_video_ratio ?? '9:16'
  const allowed: VideoRatio[] = ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9']
  return (allowed as string[]).includes(raw) ? (raw as VideoRatio) : '9:16'
}

export type PrepareStage = 'divide' | 'extract' | 'confirm'
export type PrepareStageState = 'idle' | 'run' | 'done' | 'fail'

export type PrepareCallbacks = {
  onStage: (stage: PrepareStage, state: PrepareStageState, note?: string) => void
  onLog: (line: string) => void
}

/** 列出章节全部镜头（分页接口最多 100 条，短剧单集足够）。 */
async function listChapterShots(chapterId: string) {
  const res = await StudioShotsService.listShotsApiV1StudioShotsGet({ chapterId, page: 1, pageSize: 100, order: 'index' })
  return res.data?.items ?? []
}

/** 已有章节则更新原文，否则在作品下新建一集。 */
export async function ensureChapter(args: {
  projectId: string
  chapters: ChapterRead[]
  chapterId: string | null
  scriptText: string
}): Promise<ChapterRead> {
  const { projectId, chapters, chapterId, scriptText } = args
  if (chapterId) {
    const res = await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
      chapterId,
      requestBody: { raw_text: scriptText },
    })
    if (!res.data) throw new Error('保存剧本失败')
    return res.data
  }
  const index = chapters.reduce((m, c) => Math.max(m, c.index), 0) + 1
  const res = await StudioChaptersService.createChapterApiV1StudioChaptersPost({
    requestBody: { id: crypto.randomUUID(), project_id: projectId, index, title: `第 ${index} 集`, raw_text: scriptText },
  })
  if (!res.data) throw new Error('创建章节失败')
  return res.data
}

/** 清空章节镜头（重新拆分镜前使用）。 */
export async function clearChapterShots(chapterId: string): Promise<void> {
  const shots = await listChapterShots(chapterId)
  for (const shot of shots) {
    await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId: shot.id })
  }
}

type DivisionLike = { total_shots: number; shots: Array<Record<string, unknown>> }

function pickDivision(result: unknown): DivisionLike | null {
  if (!result || typeof result !== 'object') return null
  const obj = result as Record<string, unknown>
  if (Array.isArray(obj.shots)) return obj as unknown as DivisionLike
  const nested = obj.division ?? obj.data ?? obj.result
  if (nested && typeof nested === 'object' && Array.isArray((nested as Record<string, unknown>).shots)) {
    return nested as unknown as DivisionLike
  }
  return null
}

/**
 * 一键拆分镜：拆镜头 → 识别角色场景道具 → 自动建档关联 + 接受对白。
 * 三段任何一段失败都会抛错，页面据此显示原因；成功后镜头处于 ready。
 */
export async function prepareChapter(args: { projectId: string; chapterId: string; scriptText: string } & PrepareCallbacks): Promise<void> {
  const { projectId, chapterId, scriptText, onStage, onLog } = args

  onStage('divide', 'run')
  onLog(`读取剧本 · ${scriptText.split('\n').filter((l) => l.trim()).length} 行`)
  const divideRes = await ScriptProcessingService.divideScriptAsyncApiV1ScriptProcessingDivideAsyncPost({
    requestBody: { chapter_id: chapterId, script_text: scriptText, write_to_db: true },
  })
  const divideTaskId = divideRes.data?.task_id
  if (!divideTaskId) throw new Error(divideRes.message || '拆分镜任务创建失败')
  const divided = await pollTask(divideTaskId)
  try {
    assertSucceeded(divided, '拆分镜失败')
  } catch (e) {
    onStage('divide', 'fail')
    throw e
  }
  let division = pickDivision(divided.result)
  const shots = await listChapterShots(chapterId)
  if (!division || division.shots.length === 0) {
    division = {
      total_shots: shots.length,
      shots: shots.map((s) => ({ index: s.index, start_line: 1, end_line: 1, script_excerpt: s.script_excerpt ?? '', shot_name: s.title ?? '' })),
    }
  }
  onStage('divide', 'done', `${shots.length} 个镜头`)
  onLog(`拆出 ${shots.length} 个镜头：${shots.map((s) => s.title).join(' / ')}`)

  onStage('extract', 'run')
  const extractRes = await ScriptProcessingService.extractScriptAsyncApiV1ScriptProcessingExtractAsyncPost({
    requestBody: { project_id: projectId, chapter_id: chapterId, script_division: division as Record<string, unknown>, refresh_cache: true },
  })
  const extractTaskId = extractRes.data?.task_id
  if (!extractTaskId) throw new Error(extractRes.message || '角色场景识别任务创建失败')
  const extracted = await pollTask(extractTaskId)
  try {
    assertSucceeded(extracted, '角色场景识别失败')
  } catch (e) {
    onStage('extract', 'fail')
    throw e
  }
  onStage('extract', 'done')

  onStage('confirm', 'run')
  const confirmRes = await StudioChaptersService.autoConfirmChapterApiApiV1StudioChaptersChapterIdAutoConfirmPost({ chapterId })
  const summary = confirmRes.data
  const entityNote = summary ? `${summary.created_entities} 个新角色 / 场景 / 道具` : ''
  onStage('confirm', 'done', summary ? `${summary.ready_shots}/${summary.shot_count} 个镜头就绪` : '完成')
  onLog(`识别完成：${entityNote}，已自动关联到镜头；对白 ${summary?.accepted_dialogues ?? 0} 条`)
}

/**
 * 渲染实体形象图的提示词（按名称 / 设定描述 / 作品风格），供用户查看、修改后再生成。
 * 场景 / 道具 / 服装没有图片槽位时顺便创建一个；角色按角色级生成，不需要槽位。
 */
export async function renderEntityPrompt(entity: CreatorEntityRead): Promise<{ prompt: string; imageId: number | null }> {
  let imageId = entity.image_id ?? null
  if (entity.type !== 'character' && imageId === null) {
    const created = await StudioEntitiesService.createEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesPost({
      entityType: entity.type,
      entityId: entity.id,
      requestBody: { quality_level: 'low', view_angle: 'front' },
    })
    const id = (created.data as Record<string, unknown> | null)?.id
    if (typeof id !== 'number') throw new Error('创建图片槽位失败')
    imageId = id
  }
  const rendered =
    entity.type === 'character'
      ? await StudioImageTasksService.renderCharacterImagePromptApiV1StudioImageTasksCharactersCharacterIdRenderPromptPost({
          characterId: entity.id,
          requestBody: { image_id: imageId },
        })
      : await StudioImageTasksService.renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
          assetType: entity.type,
          assetId: entity.id,
          requestBody: { image_id: imageId },
        })
  return { prompt: rendered.data?.prompt?.trim() ?? '', imageId }
}

/**
 * 为角色 / 场景 / 道具 / 服装生成一张形象图。
 * 不传 prompt 时用默认渲染的提示词；传入时按用户改过的提示词出图。
 */
export async function generateEntityImage(entity: CreatorEntityRead, prompt?: string): Promise<void> {
  let finalPrompt = prompt?.trim() ?? ''
  let imageId = entity.image_id ?? null
  if (!finalPrompt || (entity.type !== 'character' && imageId === null)) {
    const rendered = await renderEntityPrompt(entity)
    imageId = rendered.imageId
    if (!finalPrompt) finalPrompt = rendered.prompt
  }
  if (!finalPrompt) throw new Error(entity.type === 'character' ? '没有生成出形象描述' : '没有生成出参考图描述')
  if (entity.type === 'character') {
    await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
      characterId: entity.id,
      requestBody: { image_id: imageId, prompt: finalPrompt },
    })
    return
  }
  await StudioImageTasksService.createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
    assetType: entity.type,
    assetId: entity.id,
    requestBody: { image_id: imageId, prompt: finalPrompt },
  })
}

// ---------------------------------------------------------------------------
// 角色场景 / 分镜的编辑动作（P2）
// ---------------------------------------------------------------------------

export type UploadScope = {
  projectId: string
  chapterId?: string | null
  shotId?: string | null
  usageKind: 'character_image' | 'asset_image' | 'shot_frame' | 'generated_video' | 'upload'
}

/** 上传一张图片：先在浏览器缩到 2K 以内（避开函数请求体上限），再建文件记录；返回文件 ID。 */
export async function uploadImage(file: File, scope: UploadScope): Promise<string> {
  const prepared = await downscaleImage(file)
  const res = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
    formData: {
      // 生成客户端把 File 原样放进 multipart；类型声明里是 string（OpenAPI binary）。
      file: prepared as unknown as string,
      project_id: scope.projectId,
      chapter_id: scope.chapterId ?? null,
      shot_id: scope.shotId ?? null,
      usage_kind: scope.usageKind,
    },
  })
  const id = res.data?.id
  if (!id) throw new Error(res.message || '上传失败')
  return id
}

/** 用自己的图片作为角色形象 / 场景道具参考图（替代 AI 生成）。 */
export async function uploadEntityImage(entity: CreatorEntityRead, file: File, scope: { projectId: string; chapterId: string }): Promise<void> {
  const fileId = await uploadImage(file, { ...scope, usageKind: entity.type === 'character' ? 'character_image' : 'asset_image' })
  await StudioCreatorService.attachEntityImageApiApiV1StudioCreatorEntitiesEntityTypeEntityIdImageFromFilePost({
    entityType: entity.type,
    entityId: entity.id,
    requestBody: { file_id: fileId },
  })
}

/** 用自己的图片作为镜头关键帧（首帧）。 */
export async function uploadShotKeyframe(shot: CreatorShotRead, file: File, scope: { projectId: string; chapterId: string }): Promise<void> {
  const fileId = await uploadImage(file, { ...scope, shotId: shot.id, usageKind: 'shot_frame' })
  await StudioCreatorService.attachShotKeyframeApiApiV1StudioCreatorShotsShotIdKeyframeFromFilePost({
    shotId: shot.id,
    requestBody: { file_id: fileId },
  })
}

/** 整体替换镜头「画面里会用到」的实体（按类型；未传的类型不变）。 */
export async function setShotLinks(shotId: string, links: { characterIds?: string[]; sceneIds?: string[]; propIds?: string[] }): Promise<void> {
  await StudioCreatorService.setShotLinksApiApiV1StudioCreatorShotsShotIdLinksPut({
    shotId,
    requestBody: { character_ids: links.characterIds ?? null, scene_ids: links.sceneIds ?? null, prop_ids: links.propIds ?? null },
  })
}

/** 设置实体在本集出现的镜头（不选任何镜头时实体仍保留在作品里）。 */
export async function setEntityShots(chapterId: string, entity: CreatorEntityRead, shotIds: string[]): Promise<void> {
  await StudioCreatorService.setEntityShotsApiApiV1StudioCreatorChaptersChapterIdEntitiesEntityTypeEntityIdShotsPut({
    chapterId,
    entityType: entity.type,
    entityId: entity.id,
    requestBody: { shot_ids: shotIds },
  })
}

/** 手动新增角色 / 场景 / 道具并挂到镜头；同名已存在时后端会沿用（reused=true）。 */
export async function createEntity(args: { chapterId: string; type: CreatorEntityRead['type']; name: string; description: string; shotIds: string[] }): Promise<{ id: string; reused: boolean }> {
  const res = await StudioCreatorService.createChapterEntityApiApiV1StudioCreatorChaptersChapterIdEntitiesPost({
    chapterId: args.chapterId,
    requestBody: { type: args.type, name: args.name.trim(), description: args.description.trim(), shot_ids: args.shotIds },
  })
  if (!res.data?.id) throw new Error(res.message || '新增失败')
  return { id: res.data.id, reused: res.data.reused }
}

/** 改实体名称 / 设定描述。 */
export async function updateEntity(entity: CreatorEntityRead, patch: { name: string; description: string }): Promise<void> {
  await StudioEntitiesService.updateEntityApiV1StudioEntitiesEntityTypeEntityIdPatch({
    entityType: entity.type,
    entityId: entity.id,
    requestBody: { name: patch.name.trim() || entity.name, description: patch.description },
  })
}

/** 从作品里删除实体（镜头关联与形象图一并删除）。 */
export async function deleteEntity(entity: CreatorEntityRead): Promise<void> {
  await StudioEntitiesService.deleteEntityApiV1StudioEntitiesEntityTypeEntityIdDelete({ entityType: entity.type, entityId: entity.id })
}

export type DialogueDraft = { id?: number; speakerCharacterId: string | null; speakerName: string; text: string }

/**
 * 保存镜头对白：删掉被移除的行、更新改过的行、把新行接在现有行之后（序号按镜头内唯一约束递增）。
 */
export async function saveDialogue(shotId: string, drafts: DialogueDraft[], existing: CreatorDialogueLineRead[]): Promise<void> {
  const keep = new Set(drafts.map((d) => d.id).filter((id): id is number => typeof id === 'number'))
  for (const line of existing) {
    if (!keep.has(line.id)) await StudioShotDialogLinesService.deleteShotDialogLineApiV1StudioShotDialogLinesLineIdDelete({ lineId: line.id })
  }
  const listed = await StudioShotDialogLinesService.listShotDialogLinesApiV1StudioShotDialogLinesGet({ shotDetailId: shotId, page: 1, pageSize: 100 })
  let nextIndex = (listed.data?.items ?? []).reduce((m, l) => Math.max(m, l.index ?? 0), -1) + 1
  for (const draft of drafts) {
    const text = draft.text.trim()
    if (!text) continue
    const speakerName = draft.speakerName.trim() || null
    if (typeof draft.id === 'number') {
      const prev = existing.find((l) => l.id === draft.id)
      const unchanged = prev && prev.text === text && (prev.speaker_character_id ?? null) === draft.speakerCharacterId && (prev.speaker || null) === speakerName
      if (unchanged) continue
      await StudioShotDialogLinesService.updateShotDialogLineApiV1StudioShotDialogLinesLineIdPatch({
        lineId: draft.id,
        requestBody: { text, speaker_character_id: draft.speakerCharacterId, speaker_name: speakerName },
      })
    } else {
      await StudioShotDialogLinesService.createShotDialogLineApiV1StudioShotDialogLinesPost({
        requestBody: { shot_detail_id: shotId, index: nextIndex++, text, speaker_character_id: draft.speakerCharacterId, speaker_name: speakerName },
      })
    }
  }
}

/** 镜头里会用到的实体（按角色 → 场景 → 道具排序）。 */
export function linkedEntities(shot: CreatorShotRead, board: CreatorBoardRead): CreatorEntityRead[] {
  const ids = new Set([...shot.character_ids, ...shot.scene_ids, ...shot.prop_ids])
  const order = { character: 0, scene: 1, prop: 2, costume: 3 }
  return board.entities.filter((e) => ids.has(e.id)).sort((a, b) => order[a.type] - order[b.type])
}

/** 用 AI 重写镜头的画面描述（首帧提示词），返回新的描述。 */
export async function rewriteShotDescription(shotId: string): Promise<string> {
  const task = await FilmService.createShotFramePromptTaskApiV1FilmTasksShotFramePromptsPost({
    requestBody: { shot_id: shotId, frame_type: 'first' },
  })
  const taskId = task.data?.task_id
  if (!taskId) throw new Error(task.message || '画面描述任务创建失败')
  const settled = await pollTask(taskId)
  assertSucceeded(settled, '画面描述生成失败')
  const detail = await StudioShotDetailsService.getShotDetailApiV1StudioShotDetailsShotIdGet({ shotId })
  return detail.data?.first_frame_prompt?.trim() ?? ''
}

/**
 * 生成关键帧：没有画面描述时先让 AI 写，再按描述 + 角色 / 场景参考图生成首帧。
 * 图片任务创建后由聚合轮询显示进度。
 */
export async function generateKeyframe(args: { shot: CreatorShotRead; board: CreatorBoardRead; ratio: VideoRatio }): Promise<void> {
  const { shot, board, ratio } = args
  let prompt = shot.description.trim()
  if (!prompt) prompt = await rewriteShotDescription(shot.id)
  if (!prompt) throw new Error('没有画面描述，请先在镜头里填写')
  const images: ShotLinkedAssetItem[] = linkedEntities(shot, board)
    .filter((e) => e.image_file_id)
    .map((e) => ({ type: e.type, id: e.id, image_id: e.image_id ?? null, file_id: e.image_file_id ?? null, name: e.name, thumbnail: e.thumbnail }))
  await StudioImageTasksService.createShotFrameImageGenerationTaskApiV1StudioImageTasksShotShotIdFrameImageTasksPost({
    shotId: shot.id,
    requestBody: { frame_type: 'first', prompt, images, target_ratio: ratio, resolution_profile: 'standard' },
  })
}

/** 视频平台拒绝了含真人形象的参考图（真人实拍风格常见）；此时只能改用纯文字生成。 */
export function isRealPersonRejection(error: string | null | undefined): boolean {
  return /PrivacyInformation|real person/i.test(error ?? '')
}

/** 一次视频生成的参考方案：模式 + 参考图 file_id（reference 模式还带每张图的 [Image n] 说明）。 */
export type VideoPlan = { mode: VideoGenerationTaskRequest['reference_mode']; images: string[]; labels?: string[] }

/** 让后端按镜头信息（含参考素材块、镜头语言、时间码节拍）渲染视频提示词；prompt 传入时只做补强不重写。 */
export async function previewVideoPrompt(args: { shot: CreatorShotRead; ratio: VideoRatio; plan: VideoPlan; prompt?: string | null }): Promise<{ prompt: string; images: string[]; labels: string[] }> {
  const { shot, ratio, plan, prompt } = args
  const preview = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
    requestBody: { shot_id: shot.id, reference_mode: plan.mode, prompt: prompt ?? null, images: plan.images, reference_labels: plan.labels ?? null, ratio },
  })
  const rendered = preview.data?.prompt?.trim()
  if (!rendered) throw new Error('没有生成出视频提示词')
  return { prompt: rendered, images: preview.data?.images ?? plan.images, labels: preview.data?.reference_labels ?? [] }
}

/**
 * 生成视频。不传 plan 时按「有关键帧用首帧，否则纯文字」；创作页通常由 videoPlan.ts 给出全能参考方案。
 * prompt 传入时按用户改过的提示词提交；textOnly 可强制不带任何参考图（真人参考被拒后的重试）。
 */
export async function generateVideo(args: { shot: CreatorShotRead; ratio: VideoRatio; plan?: VideoPlan; prompt?: string | null; textOnly?: boolean }): Promise<void> {
  const { shot, ratio, textOnly } = args
  let plan: VideoPlan = args.plan ?? (shot.keyframe_file_id ? { mode: 'first', images: [shot.keyframe_file_id] } : { mode: 'text_only', images: [] })
  if (textOnly) plan = { mode: 'text_only', images: [] }
  const preview = await previewVideoPrompt({ shot, ratio, plan, prompt: args.prompt })
  const res = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
    requestBody: {
      shot_id: shot.id,
      reference_mode: plan.mode,
      prompt: preview.prompt,
      images: preview.images,
      reference_labels: plan.mode === 'reference' ? preview.labels : null,
      ratio,
    },
  })
  if (!res.data?.task_id) throw new Error(res.message || '视频任务创建失败')
}

/**
 * 上传一段视频：存储是 Vercel Blob 时浏览器直传（绕开函数 4.5 MB 请求体上限），否则走多部分上传并限制大小。
 * 返回文件 ID。
 */
export async function uploadVideo(file: File, scope: UploadScope): Promise<string> {
  const caps = await StudioFilesService.directUploadCapabilitiesApiApiV1StudioFilesDirectUploadCapabilitiesGet()
  if (caps.data?.direct === 'vercel_blob') {
    const prepared = await StudioFilesService.directUploadPrepareApiApiV1StudioFilesDirectUploadPreparePost({ requestBody: { filename: file.name } })
    const storageKey = prepared.data?.storage_key
    const pathname = prepared.data?.pathname
    if (!storageKey || !pathname) throw new Error(prepared.message || '上传准备失败')
    const { upload } = await import('@vercel/blob/client')
    const result = await upload(pathname, file, {
      access: 'public',
      handleUploadUrl: `${OpenAPI.BASE}/api/v1/studio/files/client-upload`,
      contentType: file.type || 'video/mp4',
      multipart: file.size > 8 * 1024 * 1024,
    })
    const registered = await StudioFilesService.directUploadRegisterApiApiV1StudioFilesDirectUploadRegisterPost({
      requestBody: {
        storage_key: storageKey,
        url: result.url,
        name: file.name,
        content_type: file.type || null,
        size: file.size,
        project_id: scope.projectId,
        chapter_id: scope.chapterId ?? null,
        shot_id: scope.shotId ?? null,
        usage_kind: scope.usageKind,
      },
    })
    const id = registered.data?.id
    if (!id) throw new Error(registered.message || '上传登记失败')
    return id
  }
  const max = caps.data?.max_server_upload_bytes ?? 4 * 1024 * 1024
  if (file.size > max) throw new Error(`视频超过 ${Math.round(max / 1024 / 1024)} MB，当前存储不支持浏览器直传，请压缩后再传`)
  const res = await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
    formData: { file: file as unknown as string, project_id: scope.projectId, chapter_id: scope.chapterId ?? null, shot_id: scope.shotId ?? null, usage_kind: scope.usageKind },
  })
  const id = res.data?.id
  if (!id) throw new Error(res.message || '上传失败')
  return id
}

/** 用自己的视频片段作为镜头成片（替换 AI 生成结果）。 */
export async function uploadShotVideo(shot: CreatorShotRead, file: File, scope: { projectId: string; chapterId: string }): Promise<void> {
  const fileId = await uploadVideo(file, { ...scope, shotId: shot.id, usageKind: 'generated_video' })
  await StudioCreatorService.attachShotVideoApiApiV1StudioCreatorShotsShotIdVideoFromFilePost({ shotId: shot.id, requestBody: { file_id: fileId } })
}

/** 新增一个镜头（带默认时长 4 秒），并自动确认使其可生成。 */
export async function addShot(args: { chapterId: string; index: number; title: string; excerpt: string }): Promise<void> {
  const { chapterId, index, title, excerpt } = args
  const id = crypto.randomUUID()
  await StudioShotsService.createShotApiV1StudioShotsPost({
    requestBody: { id, chapter_id: chapterId, index, title, script_excerpt: excerpt, status: 'pending' },
  })
  await StudioChaptersService.autoConfirmChapterApiApiV1StudioChaptersChapterIdAutoConfirmPost({ chapterId })
}

/** 保存镜头卡片上可编辑的字段：标题、画面描述、时长，以及可选的景别 / 机位 / 运镜与动作节拍。 */
export async function saveShot(args: {
  shotId: string
  title: string
  description: string
  duration: number
  cameraShot?: string
  angle?: string
  movement?: string
  actionBeats?: string[]
}): Promise<void> {
  const { shotId, title, description, duration, cameraShot, angle, movement, actionBeats } = args
  await StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({ shotId, requestBody: { title } })
  const body: ShotDetailUpdate = { first_frame_prompt: description, duration }
  if (cameraShot) body.camera_shot = cameraShot as CameraShotType
  if (angle) body.angle = angle as CameraAngle
  if (movement) body.movement = movement as CameraMovement
  if (actionBeats) body.action_beats = actionBeats.map((b) => b.trim()).filter(Boolean)
  await StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({ shotId, requestBody: body })
}

export async function deleteShot(shotId: string): Promise<void> {
  await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId })
}
