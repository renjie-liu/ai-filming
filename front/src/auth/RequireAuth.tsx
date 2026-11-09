import type React from 'react'
import { useEffect } from 'react'
import { Spin, message } from 'antd'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

/** 未登录时跳到登录页，并记住想去的地址；登录态还没确定时先转圈，避免业务页面在未登录状态下发请求。 */
export const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <div className="h-screen grid place-items-center">
        <Spin />
      </div>
    )
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}${location.hash}` }} />
  }
  return <>{children}</>
}

/** 只给管理员的页面（模型管理）；普通成员访问时回到作品列表并提示。 */
export const RequireAdmin: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth()
  const denied = !!user && !user.is_admin
  useEffect(() => {
    if (denied) message.info('模型管理只对管理员开放')
  }, [denied])
  if (denied) return <Navigate to="/works" replace />
  return <>{children}</>
}
