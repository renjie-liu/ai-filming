import type React from 'react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, AuthService } from '../services/generated'
import type { UserRead } from '../services/generated'

/**
 * 登录态：应用启动时问一次 `/auth/me`，之后由登录 / 退出动作更新；窗口重新可见时若距上次检查超过一分钟再问一次，
 * 会话过期（401）就把用户置空，`RequireAuth` 据此跳回登录页。
 *
 * 为什么存在：会话凭证是 HttpOnly cookie，前端拿不到也不需要保存；唯一要知道的是「现在是谁」。
 */

type AuthState = {
  user: UserRead | null
  /** 首次 `/auth/me` 还没回来 */
  loading: boolean
  setUser: (user: UserRead | null) => void
  refresh: () => Promise<UserRead | null>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)
const RECHECK_INTERVAL_MS = 60 * 1000

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserRead | null>(null)
  const [loading, setLoading] = useState(true)
  const lastCheck = useRef(0)

  const refresh = useCallback(async (): Promise<UserRead | null> => {
    lastCheck.current = Date.now()
    try {
      const res = await AuthService.meApiV1AuthMeGet()
      const next = res.data ?? null
      setUser(next)
      return next
    } catch (e) {
      // 401 = 未登录 / 会话过期；其它错误（网络、500）保留现有状态，避免把人误踢出去
      if (e instanceof ApiError && e.status === 401) setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await AuthService.logoutApiV1AuthLogoutPost()
    } finally {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastCheck.current < RECHECK_INTERVAL_MS) return
      void refresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [refresh])

  const value = useMemo<AuthState>(() => ({ user, loading, setUser, refresh, logout }), [user, loading, refresh, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
