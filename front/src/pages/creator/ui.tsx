import type React from 'react'
import { Progress, Tag } from 'antd'
import type { CreatorTaskRead } from '../../services/generated'
import { localizeErrorMessage } from '../../utils/errorMessage'
import { isActiveStatus } from './taskPolling'

/** 创作页公用小组件：任务状态标签、进度遮罩、画面占位。 */

export function taskErrorText(task: CreatorTaskRead | null | undefined): string | null {
  if (!task || task.status !== 'failed') return null
  return localizeErrorMessage(task.error, '生成失败，请重试')
}

export const TaskTag: React.FC<{ task?: CreatorTaskRead | null; doneLabel?: string }> = ({ task, doneLabel = '已完成' }) => {
  if (!task) return null
  if (isActiveStatus(task.status)) return <Tag color="processing">生成中 {task.progress}%</Tag>
  if (task.status === 'failed') return <Tag color="error">失败</Tag>
  if (task.status === 'cancelled') return <Tag>已取消</Tag>
  return <Tag color="success">{doneLabel}</Tag>
}

/** 卡片画面区：有图显示图，生成中显示进度，否则显示占位文案。 */
export const ArtBox: React.FC<{
  src?: string | null
  video?: boolean
  task?: CreatorTaskRead | null
  placeholder: string
  ratio?: 'portrait' | 'landscape' | 'square'
  badge?: React.ReactNode
  corner?: React.ReactNode
  onClick?: () => void
}> = ({ src, video, task, placeholder, ratio = 'portrait', badge, corner, onClick }) => {
  const aspect = ratio === 'portrait' ? 'aspect-[9/16]' : ratio === 'square' ? 'aspect-square' : 'aspect-video'
  const active = task && isActiveStatus(task.status)
  return (
    <div
      className={`relative w-full ${aspect} bg-gray-100 overflow-hidden rounded-t-lg ${onClick ? 'cursor-pointer' : ''}`}
      onClick={onClick}
    >
      {src && !video && <img src={src} alt="" className="absolute inset-0 w-full h-full object-cover" />}
      {src && video && <video src={src} className="absolute inset-0 w-full h-full object-cover" muted playsInline preload="metadata" />}
      {!src && !active && <div className="absolute inset-0 grid place-items-center text-gray-400 text-xs px-3 text-center">{placeholder}</div>}
      {active && (
        <div className="absolute inset-0 grid place-items-center bg-black/40">
          <Progress type="circle" percent={task?.progress ?? 0} size={56} strokeColor="#fff" trailColor="rgba(255,255,255,.3)" format={(p) => <span className="text-white text-xs">{p}%</span>} />
        </div>
      )}
      {badge && <div className="absolute left-2 top-2">{badge}</div>}
      {corner && <div className="absolute right-2 bottom-2">{corner}</div>}
    </div>
  )
}

export const IndexBadge: React.FC<{ index: number }> = ({ index }) => (
  <span className="text-[11px] px-2 py-0.5 rounded-full bg-black/70 text-white tabular-nums">{String(index).padStart(2, '0')}</span>
)

export const DurationBadge: React.FC<{ seconds: number }> = ({ seconds }) => (
  <span className="text-[11px] px-2 py-0.5 rounded-full bg-black/70 text-white tabular-nums">{seconds}s</span>
)

export const SectionTitle: React.FC<{ children: React.ReactNode; count?: number }> = ({ children, count }) => (
  <h2 className="text-sm text-gray-500 font-medium m-0">
    {children}
    {typeof count === 'number' && <span className="ml-1 tabular-nums">{count}</span>}
  </h2>
)
