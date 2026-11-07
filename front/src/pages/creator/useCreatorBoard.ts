import { useCallback, useEffect, useRef, useState } from 'react'
import { StudioChaptersService } from '../../services/generated'
import type { CreatorBoardRead, CreatorTaskRead } from '../../services/generated'
import { isActiveStatus } from './taskPolling'

/**
 * 创作页聚合数据：一次请求拿到镜头 / 实体 / 关键帧 / 视频与最近任务状态。
 *
 * 为什么存在：页面上的进度（生成中 x%、失败原因、完成）都来自这份数据；
 * 只要还有任务在跑就自动轮询，发起任务后也会短暂轮询一段时间，等待后端把任务写入。
 */

const POLL_MS = 3000
const FORCE_POLL_MS = 12000

export function boardHasActiveTask(board: CreatorBoardRead | null): boolean {
  if (!board) return false
  const tasks: Array<CreatorTaskRead | null | undefined> = [board.divide_task, board.extract_task]
  for (const shot of board.shots) tasks.push(shot.keyframe_prompt_task, shot.keyframe_image_task, shot.preview_grid_task, shot.video_task)
  for (const ent of board.entities) tasks.push(ent.image_task, ...ent.views.map((v) => v.task))
  return tasks.some((t) => t && isActiveStatus(t.status))
}

export function useCreatorBoard(chapterId: string | null | undefined) {
  const [board, setBoard] = useState<CreatorBoardRead | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const forcePollUntilRef = useRef(0)
  const inFlightRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!chapterId || inFlightRef.current) return
    inFlightRef.current = true
    try {
      const res = await StudioChaptersService.getCreatorBoardApiApiV1StudioChaptersChapterIdCreatorBoardGet({ chapterId })
      setBoard(res.data ?? null)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      inFlightRef.current = false
      setLoading(false)
    }
  }, [chapterId])

  /** 发起任务后调用：接下来一小段时间持续刷新，直到后端任务状态出现在聚合里。 */
  const pollSoon = useCallback(() => {
    forcePollUntilRef.current = Date.now() + FORCE_POLL_MS
    void refresh()
  }, [refresh])

  useEffect(() => {
    setBoard(null)
    if (!chapterId) return
    setLoading(true)
    void refresh()
  }, [chapterId, refresh])

  useEffect(() => {
    if (!chapterId) return
    const timer = window.setInterval(() => {
      if (boardHasActiveTask(board) || Date.now() < forcePollUntilRef.current) void refresh()
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [board, chapterId, refresh])

  return { board, loading, error, refresh, pollSoon, setBoard }
}
