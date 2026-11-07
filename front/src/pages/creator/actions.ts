import {
  FilmService,
  ScriptProcessingService,
  StudioChaptersService,
  StudioEntitiesService,
  StudioImageTasksService,
  StudioShotDetailsService,
  StudioShotsService,
} from '../../services/generated'
import type {
  ChapterRead,
  CreatorBoardRead,
  CreatorEntityRead,
  CreatorShotRead,
  ShotLinkedAssetItem,
  VideoGenerationTaskRequest,
} from '../../services/generated'
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

/** 为角色 / 场景 / 道具 / 服装生成一张形象图（没有图片槽位时先创建）。 */
export async function generateEntityImage(entity: CreatorEntityRead): Promise<void> {
  let imageId = entity.image_id ?? null
  // 角色不需要预建图片槽位（后端按角色级生成并自动创建首张形象图）；场景 / 道具 / 服装需要。
  if (entity.type !== 'character' && (imageId === null || imageId === undefined)) {
    const created = await StudioEntitiesService.createEntityImageApiV1StudioEntitiesEntityTypeEntityIdImagesPost({
      entityType: entity.type,
      entityId: entity.id,
      requestBody: { quality_level: 'low', view_angle: 'front' },
    })
    const id = (created.data as Record<string, unknown> | null)?.id
    if (typeof id !== 'number') throw new Error('创建图片槽位失败')
    imageId = id
  }
  if (entity.type === 'character') {
    const rendered = await StudioImageTasksService.renderCharacterImagePromptApiV1StudioImageTasksCharactersCharacterIdRenderPromptPost({
      characterId: entity.id,
      requestBody: { image_id: imageId },
    })
    const prompt = rendered.data?.prompt?.trim()
    if (!prompt) throw new Error('没有生成出形象描述')
    await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
      characterId: entity.id,
      requestBody: { image_id: imageId, prompt },
    })
    return
  }
  const rendered = await StudioImageTasksService.renderAssetImagePromptApiV1StudioImageTasksAssetsAssetTypeAssetIdRenderPromptPost({
    assetType: entity.type,
    assetId: entity.id,
    requestBody: { image_id: imageId },
  })
  const prompt = rendered.data?.prompt?.trim()
  if (!prompt) throw new Error('没有生成出参考图描述')
  await StudioImageTasksService.createAssetImageGenerationTaskApiV1StudioImageTasksAssetsAssetTypeAssetIdImageTasksPost({
    assetType: entity.type,
    assetId: entity.id,
    requestBody: { image_id: imageId, prompt },
  })
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

/** 生成视频：有关键帧用首帧模式，否则纯文字；提示词由后端按镜头信息渲染。textOnly 可强制不带参考图。 */
export async function generateVideo(args: { shot: CreatorShotRead; ratio: VideoRatio; textOnly?: boolean }): Promise<void> {
  const { shot, ratio, textOnly } = args
  const useFrame = !!shot.keyframe_file_id && !textOnly
  const referenceMode: VideoGenerationTaskRequest['reference_mode'] = useFrame ? 'first' : 'text_only'
  const images = useFrame ? [shot.keyframe_file_id as string] : []
  const preview = await FilmService.previewVideoGenerationPromptApiV1FilmTasksVideoPreviewPromptPost({
    requestBody: { shot_id: shot.id, reference_mode: referenceMode, prompt: null, images, ratio },
  })
  const prompt = preview.data?.prompt?.trim()
  if (!prompt) throw new Error('没有生成出视频提示词')
  const res = await FilmService.createVideoGenerationTaskApiV1FilmTasksVideoPost({
    requestBody: { shot_id: shot.id, reference_mode: referenceMode, prompt, images: preview.data?.images ?? images, ratio },
  })
  if (!res.data?.task_id) throw new Error(res.message || '视频任务创建失败')
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

/** 保存镜头卡片上可编辑的字段。 */
export async function saveShot(args: { shotId: string; title: string; description: string; duration: number }): Promise<void> {
  const { shotId, title, description, duration } = args
  await StudioShotsService.updateShotApiV1StudioShotsShotIdPatch({ shotId, requestBody: { title } })
  await StudioShotDetailsService.updateShotDetailApiV1StudioShotDetailsShotIdPatch({
    shotId,
    requestBody: { first_frame_prompt: description, duration },
  })
}

export async function deleteShot(shotId: string): Promise<void> {
  await StudioShotsService.deleteShotApiV1StudioShotsShotIdDelete({ shotId })
}
