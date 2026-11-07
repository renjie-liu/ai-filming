import type React from 'react'
import { useState } from 'react'
import { Progress, Tag, Tooltip } from 'antd'
import type { CreatorImageCandidateRead, CreatorTaskRead } from '../../services/generated'
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

/**
 * 候选 / 历史缩略图条：当前用的那张高亮，点其它任意一张即「采用」（切回历史或换成另一张候选）。
 *
 * 为什么存在：角色形象与镜头关键帧都支持「多生成几张挑一张 / 回退到上一版」，两处共用同一条。
 * 只有一张时不渲染（没有可选的）。
 */
export const CandidateStrip: React.FC<{
  candidates: CreatorImageCandidateRead[]
  onAdopt: (fileId: string) => Promise<void>
  ratio?: 'portrait' | 'landscape' | 'square'
  disabled?: boolean
}> = ({ candidates, onAdopt, ratio = 'square', disabled }) => {
  const [busyId, setBusyId] = useState<string | null>(null)
  if (candidates.length < 2) return null
  const aspect = ratio === 'portrait' ? 'aspect-[9/16]' : ratio === 'square' ? 'aspect-square' : 'aspect-video'
  const width = ratio === 'landscape' ? 'w-24' : 'w-16'
  const adopt = async (fileId: string) => {
    setBusyId(fileId)
    try {
      await onAdopt(fileId)
    } finally {
      setBusyId(null)
    }
  }
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-gray-500">历史候选 · 点一张采用（{candidates.length} 张）</span>
      <div className="flex gap-2 overflow-x-auto pb-1" data-testid="candidate-strip">
        {candidates.map((c, i) => (
          <Tooltip key={c.file_id} title={c.is_current ? '当前使用' : c.created_at ? `生成于 ${new Date(c.created_at).toLocaleString()}` : '上传的图片'}>
            <button
              type="button"
              aria-label={c.is_current ? `候选 ${i + 1}（当前）` : `采用候选 ${i + 1}`}
              disabled={disabled || c.is_current || busyId !== null}
              onClick={() => void adopt(c.file_id)}
              className={`relative shrink-0 ${width} ${aspect} rounded overflow-hidden border-2 p-0 bg-gray-100 ${c.is_current ? 'border-blue-500' : 'border-transparent hover:border-gray-400'} ${busyId === c.file_id ? 'opacity-60' : ''} disabled:cursor-default`}
            >
              {c.url && <img src={c.url} alt="" className="absolute inset-0 w-full h-full object-cover" />}
              {c.is_current && <span className="absolute left-1 top-1 text-[10px] px-1 rounded bg-blue-500 text-white">当前</span>}
            </button>
          </Tooltip>
        ))}
      </div>
    </div>
  )
}

export const SectionTitle: React.FC<{ children: React.ReactNode; count?: number }> = ({ children, count }) => (
  <h2 className="text-sm text-gray-500 font-medium m-0">
    {children}
    {typeof count === 'number' && <span className="ml-1 tabular-nums">{count}</span>}
  </h2>
)
