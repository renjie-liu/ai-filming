import type { CreatorBoardRead, CreatorEntityRead, CreatorShotRead } from '../../services/generated'
import { linkedEntities } from './actions'
import { viewAngleLabel } from './labels'

/**
 * 视频参考方式的纯逻辑：哪些素材可以当参考、默认用哪种模式、确认单上怎么描述。
 *
 * 为什么存在：Seedance 2.x 的全能参考（最多 9 张图，提示词按 [Image n] 点名）是跨镜头不换脸的关键；
 * 这里的候选顺序与后端 `collect_reference_candidates` 一致（角色 → 场景 → 道具 → 服装 → 关键帧），
 * 角色的侧面 / 背面视图紧跟在该角色正面之后（后端清单不含视图，前端把它们一并点名，预览与提交用同一份）。
 */

export type VideoMode = 'reference' | 'first' | 'text_only'

export type VideoReference = {
  file_id: string
  label: string
  kind: CreatorEntityRead['type'] | 'keyframe'
  name: string
  thumbnail: string | null
}

export const MAX_VIDEO_REFERENCES = 9

export const VIDEO_MODE_LABEL: Record<VideoMode, string> = { reference: '形象参考', first: '首帧图', text_only: '仅文字' }

export const VIDEO_MODE_HINT: Record<VideoMode, string> = {
  reference: '把角色 / 场景的形象图和关键帧一起给模型，提示词按 [Image n] 点名；人物最不容易换脸',
  first: '用关键帧锁定第一帧的构图，形象图不参与',
  text_only: '只按文字描述生成，不带任何参考图',
}

const TYPE_LABEL: Record<CreatorEntityRead['type'], string> = { character: '角色', scene: '场景', prop: '道具', costume: '服装' }

/** 镜头可用的参考素材清单（只取有形象图的关联实体 + 角色已生成的其它视角 + 关键帧）。 */
export function referenceCandidates(shot: CreatorShotRead, board: CreatorBoardRead): VideoReference[] {
  const seen = new Set<string>()
  const out: VideoReference[] = []
  for (const e of linkedEntities(shot, board)) {
    if (!e.image_file_id || seen.has(e.image_file_id)) continue
    seen.add(e.image_file_id)
    const desc = e.description.replace(/\s+/g, ' ').trim()
    out.push({
      file_id: e.image_file_id,
      label: `${TYPE_LABEL[e.type]}「${e.name}」${desc ? `：${desc.slice(0, 60)}` : ''}`,
      kind: e.type,
      name: e.name,
      thumbnail: e.thumbnail || null,
    })
    for (const v of e.views) {
      if (!v.file_id || seen.has(v.file_id)) continue
      seen.add(v.file_id)
      out.push({ file_id: v.file_id, label: `${TYPE_LABEL[e.type]}「${e.name}」${viewAngleLabel(v.view_angle)}（同一人）`, kind: e.type, name: e.name, thumbnail: v.url || null })
    }
  }
  if (shot.keyframe_file_id && !seen.has(shot.keyframe_file_id)) {
    out.push({ file_id: shot.keyframe_file_id, label: '本镜头关键帧（构图与起始状态）', kind: 'keyframe', name: '关键帧', thumbnail: shot.keyframe_url })
  }
  return out.slice(0, MAX_VIDEO_REFERENCES)
}

/** 默认参考方式：有形象图就全能参考；只有关键帧用首帧；都没有则纯文字。 */
export function defaultVideoMode(shot: CreatorShotRead, board: CreatorBoardRead): VideoMode {
  const refs = referenceCandidates(shot, board)
  if (refs.some((r) => r.kind !== 'keyframe')) return 'reference'
  if (shot.keyframe_file_id) return 'first'
  return 'text_only'
}

/** 确认单「参考」列的文案。 */
export function describeVideoMode(shot: CreatorShotRead, board: CreatorBoardRead, mode: VideoMode = defaultVideoMode(shot, board)): string {
  if (mode === 'reference') return `形象参考 ${referenceCandidates(shot, board).length} 张`
  if (mode === 'first') return '首帧图 + 描述'
  return '仅文字描述'
}
