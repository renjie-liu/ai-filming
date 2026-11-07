import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { FilmService } from '../../../services/generated'
import { useTaskUiStore } from './taskUiStore'

/** 有任务在跑时的轮询间隔。 */
const TASK_POLL_ACTIVE_MS = 4000
/** 空闲时的轮询间隔：Neon 免费版按计算时长计费，持续每 4 秒查一次会让数据库永远无法自动休眠。 */
const TASK_POLL_IDLE_MS = 60000
const TASK_RECENT_SECONDS = 15
const TASK_PAGE_SIZE = 50
const ACTIVE_STATUSES = new Set(['pending', 'running', 'streaming'])

type TaskRuntimeProviderProps = {
  children: ReactNode
}

/**
 * 任务中心的全局轮询：拉取最近任务写进 taskUiStore。
 *
 * 只在有任务处于排队 / 运行中时每 4 秒刷新；空闲时降到每分钟一次，标签页不可见时暂停，
 * 重新可见时立刻刷新一次。这样闲置的页面不会一直唤醒数据库（Neon 免费额度按计算时长扣）。
 */
export function TaskRuntimeProvider({ children }: TaskRuntimeProviderProps) {
  const setServerTasks = useTaskUiStore((state) => state.setServerTasks)

  useEffect(() => {
    let cancelled = false
    let timer: number | null = null

    const schedule = (delay: number) => {
      if (cancelled) return
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(() => void load(), delay)
    }

    const load = async () => {
      if (cancelled) return
      if (document.visibilityState === 'hidden') {
        schedule(TASK_POLL_IDLE_MS)
        return
      }
      let hasActive = false
      try {
        const res = await FilmService.listTasksApiV1FilmTasksGet({
          recentSeconds: TASK_RECENT_SECONDS,
          page: 1,
          pageSize: TASK_PAGE_SIZE,
        })
        if (cancelled) return
        const items = res.data?.items ?? []
        setServerTasks(items)
        hasActive = items.some((task) => ACTIVE_STATUSES.has(String(task.status)))
      } catch {
        if (!cancelled) {
          setServerTasks([])
        }
      } finally {
        schedule(hasActive ? TASK_POLL_ACTIVE_MS : TASK_POLL_IDLE_MS)
      }
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') void load()
    }

    document.addEventListener('visibilitychange', onVisible)
    void load()
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisible)
      if (timer) window.clearTimeout(timer)
    }
  }, [setServerTasks])

  return <>{children}</>
}
