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

export const CAMERA_ANGLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'EYE_LEVEL', label: '平视' },
  { value: 'HIGH_ANGLE', label: '俯拍' },
  { value: 'LOW_ANGLE', label: '仰拍' },
  { value: 'BIRD_EYE', label: '鸟瞰' },
  { value: 'DUTCH', label: '荷兰角' },
  { value: 'OVER_SHOULDER', label: '过肩' },
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

/** 角色多视角（后端 AssetViewAngle 大写 code）→ 中文；正面是主形象，其余由「生成三视图」派生。 */
export const VIEW_ANGLE_LABEL: Record<string, string> = {
  FRONT: '正面',
  LEFT: '左侧面',
  RIGHT: '右侧面',
  BACK: '背面',
  THREE_QUARTER: '四分之三侧面',
  TOP: '俯视',
}

/** 「生成三视图」默认派生的视角（请求体用小写 code）。 */
export const DEFAULT_CHARACTER_VIEWS: Array<'left' | 'back'> = ['left', 'back']

export function viewAngleLabel(code: string): string {
  return VIEW_ANGLE_LABEL[code.toUpperCase()] ?? code
}

export function cameraShotLabel(code: string): string {
  return CAMERA_SHOT_OPTIONS.find((o) => o.value === code)?.label ?? ''
}

export function cameraMovementLabel(code: string): string {
  return CAMERA_MOVEMENT_OPTIONS.find((o) => o.value === code)?.label ?? ''
}

export function cameraAngleLabel(code: string): string {
  return CAMERA_ANGLE_OPTIONS.find((o) => o.value === code)?.label ?? ''
}
