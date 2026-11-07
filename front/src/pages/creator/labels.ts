import type { CreatorEntityRead } from '../../services/generated'

/**
 * 创作页用到的中文标签表：实体类型、景别、运镜。
 *
 * 为什么存在：后端存英文 code（ECU / DOLLY_IN …），页面只出现中文，且多个步骤共用同一套词。
 */

export type CreatorEntityType = CreatorEntityRead['type']

export const ENTITY_TYPE_LABEL: Record<CreatorEntityType, string> = { character: '角色', scene: '场景', prop: '道具', costume: '服装' }

/** 用户可手动新增的实体类型（服装仍由剧本提取产生）。 */
export const CREATABLE_ENTITY_TYPES: CreatorEntityType[] = ['character', 'scene', 'prop']

export const CAMERA_SHOT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'ECU', label: '大特写' },
  { value: 'CU', label: '特写' },
  { value: 'MCU', label: '中近景' },
  { value: 'MS', label: '中景' },
  { value: 'MLS', label: '中远景' },
  { value: 'LS', label: '远景' },
  { value: 'ELS', label: '大远景' },
]

export const CAMERA_MOVEMENT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'STATIC', label: '固定' },
  { value: 'PAN', label: '横摇' },
  { value: 'TILT', label: '竖摇' },
  { value: 'DOLLY_IN', label: '推进' },
  { value: 'DOLLY_OUT', label: '拉远' },
  { value: 'TRACK', label: '跟拍' },
  { value: 'CRANE', label: '升降' },
  { value: 'HANDHELD', label: '手持' },
  { value: 'STEADICAM', label: '稳定器' },
  { value: 'ZOOM_IN', label: '变焦推' },
  { value: 'ZOOM_OUT', label: '变焦拉' },
]

export function cameraShotLabel(code: string): string {
  return CAMERA_SHOT_OPTIONS.find((o) => o.value === code)?.label ?? ''
}

export function cameraMovementLabel(code: string): string {
  return CAMERA_MOVEMENT_OPTIONS.find((o) => o.value === code)?.label ?? ''
}
