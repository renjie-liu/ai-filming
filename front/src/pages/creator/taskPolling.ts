import { FilmService } from '../../services/generated'
import type { TaskStatus } from '../../services/generated'

/**
 * 轮询单个任务直到结束。
 *
 * 为什么存在：创作页把「拆分镜 → 提取 → 自动确认」「写提示词 → 生成关键帧」串成一步，
 * 每一段都要等上一段的任务结束；这里统一轮询与结果读取，避免每个步骤各写一遍。
 */

export type SettledTask = {
  taskId: string
  status: TaskStatus
  progress: number
  error: string | null
  result: unknown
}

const ACTIVE: TaskStatus[] = ['pending', 'running', 'streaming']

export function isActiveStatus(status: string | null | undefined): boolean {
  return !!status && (ACTIVE as string[]).includes(status)
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export async function pollTask(
  taskId: string,
  options: { intervalMs?: number; timeoutMs?: number; onProgress?: (progress: number, status: TaskStatus) => void } = {},
): Promise<SettledTask> {
  const intervalMs = options.intervalMs ?? 2500
  const timeoutMs = options.timeoutMs ?? 10 * 60 * 1000
  const started = Date.now()
  // 先稍等再查，避免刚创建的任务还没写入状态
  await sleep(800)
  for (;;) {
    const res = await FilmService.getTaskStatusApiV1FilmTasksTaskIdStatusGet({ taskId })
    const data = res.data
    if (data) {
      options.onProgress?.(data.progress ?? 0, data.status)
      if (!isActiveStatus(data.status)) {
        let error: string | null = null
        let result: unknown = null
        try {
          const r = await FilmService.getTaskResultApiV1FilmTasksTaskIdResultGet({ taskId })
          error = (r.data?.error as string | null | undefined) ?? null
          result = r.data?.result ?? null
        } catch {
          // 结果接口失败时只返回状态
        }
        return { taskId, status: data.status, progress: data.progress ?? 0, error, result }
      }
    }
    if (Date.now() - started > timeoutMs) {
      return { taskId, status: 'running', progress: 0, error: '等待超时，任务仍在后台运行', result: null }
    }
    await sleep(intervalMs)
  }
}

/** 任务失败时抛出可读错误（原文交给 errorMessage 做中文映射）。 */
export function assertSucceeded(task: SettledTask, fallback: string): void {
  if (task.status === 'succeeded') return
  throw new Error(task.error || (task.status === 'cancelled' ? '任务已取消' : fallback))
}
