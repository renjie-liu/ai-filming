import type React from 'react'
import { Button, Card, Progress } from 'antd'
import type { CreatorBoardRead } from '../../services/generated'
import { CREATOR_STEPS, type CreatorStepKey } from './routes'
import { isActiveStatus } from './taskPolling'

/**
 * 导演助手：告诉用户现在该做什么、哪些任务在跑、本集大概花多少。
 * 桌面端固定在右栏，手机端由 CreatorPage 折叠成底部操作条（复用 primary）。
 */

export type RailPrimary = { label: string; onClick: () => void; disabled?: boolean; loading?: boolean }

export function collectRunningTasks(board: CreatorBoardRead | null): Array<{ name: string; progress: number }> {
  if (!board) return []
  const out: Array<{ name: string; progress: number }> = []
  if (board.divide_task && isActiveStatus(board.divide_task.status)) out.push({ name: '拆分镜头', progress: board.divide_task.progress })
  if (board.extract_task && isActiveStatus(board.extract_task.status)) out.push({ name: '识别角色与场景', progress: board.extract_task.progress })
  for (const e of board.entities) {
    if (e.image_task && isActiveStatus(e.image_task.status)) out.push({ name: `形象 · ${e.name}`, progress: e.image_task.progress })
  }
  for (const s of board.shots) {
    if (s.keyframe_prompt_task && isActiveStatus(s.keyframe_prompt_task.status)) out.push({ name: `画面描述 · ${s.title}`, progress: s.keyframe_prompt_task.progress })
    if (s.keyframe_image_task && isActiveStatus(s.keyframe_image_task.status)) out.push({ name: `关键帧 · ${s.title}`, progress: s.keyframe_image_task.progress })
    if (s.video_task && isActiveStatus(s.video_task.status)) out.push({ name: `视频 · ${s.title}`, progress: s.video_task.progress })
  }
  return out
}

export const STEP_TIPS: Record<CreatorStepKey, string> = {
  script: '粘贴剧本后点「一键拆分镜」。拆分只分析文字，不消耗生成额度，可以多试几次。',
  cast: '先定下主要角色的形象（AI 生成或上传自己的图），后面的关键帧和视频都会沿用，画面才不会换人。点卡片可以改设定、改提示词、选出现的镜头。',
  storyboard: '点镜头卡可以改画面描述、景别运镜、对白和画面里的人物场景，也能上传自己的关键帧。先出关键帧看构图再生成视频，便宜得多。',
  video: '确认镜头和时长后开始生成，额度在此时才扣；失败的镜头看原因后单独重试。',
  final: '满意就下载片段；不满意的镜头回到「视频」单独重做，其余不受影响。',
}

const DirectorRail: React.FC<{
  step: CreatorStepKey
  board: CreatorBoardRead | null
  primary: RailPrimary | null
  tip?: string
}> = ({ step, board, primary, tip }) => {
  const idx = CREATOR_STEPS.findIndex((s) => s.key === step)
  const running = collectRunningTasks(board)
  const imageCount = (board?.entities.filter((e) => e.thumbnail).length ?? 0) + (board?.summary.keyframe_count ?? 0)
  const videoSeconds = board?.shots.filter((s) => s.video_file_id || s.video_task).reduce((a, s) => a + s.duration, 0) ?? 0
  return (
    <div className="flex flex-col gap-3">
      <Card size="small" title={<span className="text-gray-500 font-medium">导演助手</span>}>
        <div className="font-medium text-[15px] mb-1">
          第 {idx + 1} 步 · {CREATOR_STEPS[idx]?.label}
        </div>
        <p className="text-gray-500 text-[13px] m-0 mb-3">{tip ?? STEP_TIPS[step]}</p>
        {primary && (
          <Button type="primary" block onClick={primary.onClick} disabled={primary.disabled} loading={primary.loading}>
            {primary.label}
          </Button>
        )}
      </Card>
      <Card size="small" title={<span className="text-gray-500 font-medium">进行中</span>}>
        {running.length === 0 ? (
          <div className="text-gray-400 text-[13px]">没有正在运行的任务</div>
        ) : (
          <div className="flex flex-col gap-2">
            {running.map((t) => (
              <div key={t.name}>
                <div className="flex justify-between text-[13px]">
                  <span className="truncate">{t.name}</span>
                  <span className="text-gray-400 tabular-nums">{t.progress}%</span>
                </div>
                <Progress percent={t.progress} size="small" showInfo={false} />
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card size="small" title={<span className="text-gray-500 font-medium">本集用量</span>}>
        <div className="flex justify-between text-[13px]">
          <span>图片</span>
          <b className="font-medium tabular-nums">{imageCount} 张</b>
        </div>
        <div className="flex justify-between text-[13px]">
          <span>视频</span>
          <b className="font-medium tabular-nums">{videoSeconds} 秒</b>
        </div>
        <p className="text-gray-400 text-[12px] m-0 mt-2">只在你点击「生成」后才扣费；拆分镜和改文字都是免费的。</p>
      </Card>
    </div>
  )
}

export default DirectorRail
