import type React from 'react'
import { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, Spin, Tabs, message } from 'antd'
import { LockOutlined, MailOutlined, UserOutlined, KeyOutlined } from '@ant-design/icons'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AuthService } from '../services/generated'
import { extractErrorText, localizeErrorMessage } from '../utils/errorMessage'
import type { AuthStatusRead, UserRead } from '../services/generated'
import { useAuth } from '../auth/AuthContext'

/**
 * 登录 / 注册页（邮箱 + 密码）。
 *
 * 根据 `/auth/status` 决定展示：还没有任何用户时只给「创建管理员账号」；需要邀请码时注册表单多一栏；
 * 关闭注册时只能登录。登录成功后回到来源页（没有就去作品列表）。
 */

type LoginForm = { email: string; password: string }
type RegisterForm = { email: string; password: string; display_name?: string; invite_code?: string }

const errorText = (e: unknown, fallback: string) => localizeErrorMessage(extractErrorText(e), fallback)

const LoginPage: React.FC = () => {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/works'
  const [status, setStatus] = useState<AuthStatusRead | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    AuthService.authStatusApiV1AuthStatusGet()
      .then((res) => {
        const data = res.data ?? null
        setStatus(data)
        if (data && !data.has_users) setTab('register')
      })
      .catch((e) => setStatusError(errorText(e, '无法连接服务器')))
  }, [])

  if (user) return <Navigate to={from} replace />

  const finish = (u: UserRead | null | undefined) => {
    if (!u) return
    setUser(u)
    navigate(from, { replace: true })
  }

  const login = async (values: LoginForm) => {
    setBusy(true)
    try {
      const res = await AuthService.loginApiV1AuthLoginPost({ requestBody: { email: values.email.trim(), password: values.password } })
      finish(res.data)
    } catch (e) {
      message.error(errorText(e, '登录失败'))
    } finally {
      setBusy(false)
    }
  }

  const register = async (values: RegisterForm) => {
    setBusy(true)
    try {
      const res = await AuthService.registerApiV1AuthRegisterPost({
        requestBody: {
          email: values.email.trim(),
          password: values.password,
          display_name: values.display_name?.trim() || '',
          invite_code: values.invite_code?.trim() || null,
        },
      })
      message.success(status && !status.has_users ? '管理员账号已创建' : '注册成功')
      finish(res.data)
    } catch (e) {
      message.error(errorText(e, '注册失败'))
    } finally {
      setBusy(false)
    }
  }

  const firstAdmin = !!status && !status.has_users
  const registration = status?.registration ?? 'open'
  const canRegister = registration !== 'closed'

  const loginForm = (
    <Form<LoginForm> layout="vertical" onFinish={(v) => void login(v)} requiredMark={false} size="large">
      <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
        <Input prefix={<MailOutlined />} placeholder="you@example.com" autoComplete="email" autoFocus data-testid="login-email" />
      </Form.Item>
      <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
        <Input.Password prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" data-testid="login-password" />
      </Form.Item>
      <Button type="primary" htmlType="submit" block loading={busy} data-testid="login-submit">登录</Button>
    </Form>
  )

  const registerForm = canRegister ? (
    <Form<RegisterForm> layout="vertical" onFinish={(v) => void register(v)} requiredMark={false} size="large">
      {firstAdmin && (
        <Alert
          type="info"
          showIcon
          className="mb-4"
          message="这是第一个账号，将成为管理员"
          description="管理员可以在「系统设置」里管理注册方式（邀请码 / 开放 / 关闭）和模型配置。此前创建的作品会归到这个账号下。"
        />
      )}
      <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '邮箱格式不正确' }]}>
        <Input prefix={<MailOutlined />} placeholder="you@example.com" autoComplete="email" data-testid="register-email" />
      </Form.Item>
      <Form.Item name="password" label="密码" rules={[{ required: true, message: '请设置密码' }, { min: 8, message: '至少 8 位' }]}>
        <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" autoComplete="new-password" data-testid="register-password" />
      </Form.Item>
      <Form.Item name="display_name" label="怎么称呼你（可选）">
        <Input prefix={<UserOutlined />} placeholder="显示名" maxLength={80} />
      </Form.Item>
      {registration === 'invite' && (
        <Form.Item name="invite_code" label="邀请码" rules={[{ required: true, message: '请输入邀请码' }]} extra="向管理员索取；管理员可在「系统设置」里看到并重新生成。">
          <Input prefix={<KeyOutlined />} placeholder="8 位邀请码" maxLength={64} data-testid="register-invite" />
        </Form.Item>
      )}
      <Button type="primary" htmlType="submit" block loading={busy} data-testid="register-submit">
        {firstAdmin ? '创建管理员账号' : '注册并登录'}
      </Button>
    </Form>
  ) : (
    <Alert type="warning" showIcon message="当前未开放注册" description="请联系管理员获取账号。" />
  )

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-[420px]">
        <div className="flex items-center justify-center gap-2 mb-6">
          <img src="/logo.svg" alt="Jellyfish" className="w-9 h-9" />
          <div>
            <div className="text-lg font-semibold leading-tight">Jellyfish</div>
            <div className="text-xs text-gray-500">AI 短剧工作台</div>
          </div>
        </div>
        <Card>
          {statusError ? (
            <Alert type="error" showIcon message={statusError} />
          ) : !status ? (
            <div className="py-8 grid place-items-center"><Spin /></div>
          ) : firstAdmin ? (
            <>
              <h2 className="text-base font-semibold m-0 mb-4">创建管理员账号</h2>
              {registerForm}
            </>
          ) : (
            <Tabs
              activeKey={tab}
              onChange={(k) => setTab(k as 'login' | 'register')}
              centered
              items={[
                { key: 'login', label: '登录', children: loginForm },
                { key: 'register', label: '注册', children: registerForm },
              ]}
            />
          )}
        </Card>
      </div>
    </div>
  )
}

export default LoginPage
