import { useEffect, useState } from 'react'
import { SystemService } from '../../../services/generated'
import type { SetupStatusRead } from '../../../services/generated'

/**
 * 读取「开箱即用」配置状态（默认模型是否就绪、供应商是否由部署托管）。
 *
 * 为什么存在：快速上手卡片、使用指南页与模型管理页都需要同一份状态，
 * 统一在此请求，避免各页面重复编写加载逻辑。
 *
 * @returns loading：是否加载中；status：后端返回的状态（失败时为 null）
 */
export function useSetupStatus(): { loading: boolean; status: SetupStatusRead | null } {
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<SetupStatusRead | null>(null)

  useEffect(() => {
    let cancelled = false
    SystemService.setupStatusApiV1SystemSetupStatusGet()
      .then((res) => {
        if (!cancelled) setStatus(res.data ?? null)
      })
      .catch(() => {
        if (!cancelled) setStatus(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { loading, status }
}
