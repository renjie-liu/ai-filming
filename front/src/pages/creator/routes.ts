/**
 * 创作模式路由。
 *
 * 为什么存在：作品列表与创作页是应用仅有的两个业务页面，路径集中在这里，
 * 任务中心跳转、作品卡片、章节切换都引用同一份定义。
 */

export const WORKS_PATH = '/works'

/** 创作页：`/works/:projectId?chapter=<chapterId>#<step>` */
export function getCreatorPath(projectId: string, chapterId?: string | null, step?: CreatorStepKey): string {
  const query = chapterId ? `?chapter=${encodeURIComponent(chapterId)}` : ''
  const hash = step ? `#${step}` : ''
  return `${WORKS_PATH}/${encodeURIComponent(projectId)}${query}${hash}`
}

export type CreatorStepKey = 'script' | 'cast' | 'storyboard' | 'video' | 'final'

export const CREATOR_STEPS: Array<{ key: CreatorStepKey; label: string }> = [
  { key: 'script', label: '剧本' },
  { key: 'cast', label: '角色场景' },
  { key: 'storyboard', label: '分镜' },
  { key: 'video', label: '视频' },
  { key: 'final', label: '成片' },
]

export function isCreatorStepKey(value: string | null | undefined): value is CreatorStepKey {
  return !!value && CREATOR_STEPS.some((s) => s.key === value)
}
