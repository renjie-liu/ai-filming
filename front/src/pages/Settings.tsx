import type React from 'react'
import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Form, Input, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { AuthService } from '../services/generated'
import { extractErrorText, localizeErrorMessage } from '../utils/errorMessage'
import type { RegistrationSettingsRead, UserRead } from '../services/generated'
import { useAuth } from '../auth/AuthContext'

/**
 * 系统设置：当前账号信息 + 修改密码 + 退出登录；管理员还能管理注册方式（允许 / 关闭、邀请码）并查看用户列表。
 * 模型配置在「模型管理」页，这里不重复。
 */

const errorText = (e: unknown, fallback: string) => localizeErrorMessage(extractErrorText(e), fallback)

const formatTime = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : '—')

type PasswordForm = { current_password: string; new_password: string; confirm: string }

const Settings: React.FC = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [settings, setSettings] = useState<RegistrationSettingsRead | null>(null)
  const [users, setUsers] = useState<UserRead[]>([])
  const [saving, setSaving] = useState(false)
  const [codeDraft, setCodeDraft] = useState('')
  const [pwForm] = Form.useForm<PasswordForm>()
  const [pwSaving, setPwSaving] = useState(false)

  const loadAdmin = useCallback(async () => {
    if (!user?.is_admin) return
    try {
      const [s, u] = await Promise.all([AuthService.getRegistrationSettingsApiV1AuthSettingsGet(), AuthService.listUsersApiV1AuthUsersGet()])
      setSettings(s.data ?? null)
      setCodeDraft(s.data?.invite_code ?? '')
      setUsers(u.data ?? [])
    } catch (e) {
      message.error(errorText(e, '加载注册设置失败'))
    }
  }, [user?.is_admin])

  useEffect(() => {
    void loadAdmin()
  }, [loadAdmin])

  const update = async (body: { enabled?: boolean; invite_code?: string | null; regenerate_invite_code?: boolean }) => {
    setSaving(true)
    try {
      const res = await AuthService.updateRegistrationSettingsApiV1AuthSettingsPut({ requestBody: body })
      setSettings(res.data ?? null)
      setCodeDraft(res.data?.invite_code ?? '')
      message.success('已保存')
    } catch (e) {
      message.error(errorText(e, '保存失败'))
    } finally {
      setSaving(false)
    }
  }

  const changePassword = async (values: PasswordForm) => {
    setPwSaving(true)
    try {
      await AuthService.changePasswordApiV1AuthPasswordPost({ requestBody: { current_password: values.current_password, new_password: values.new_password } })
      message.success('密码已更新')
      pwForm.resetFields()
    } catch (e) {
      message.error(errorText(e, '修改密码失败'))
    } finally {
      setPwSaving(false)
    }
  }

  const doLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  if (!user) return null

  return (
    <div className="h-full overflow-auto p-4 md:p-6">
      <div className="mx-auto max-w-[900px] flex flex-col gap-4">
        <Card title="我的账号" extra={<Button onClick={() => void doLogout()} data-testid="logout">退出登录</Button>}>
          <Descriptions column={{ xs: 1, sm: 2 }} size="small">
            <Descriptions.Item label="邮箱">{user.email}</Descriptions.Item>
            <Descriptions.Item label="显示名">{user.display_name || '—'}</Descriptions.Item>
            <Descriptions.Item label="角色">{user.is_admin ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>}</Descriptions.Item>
            <Descriptions.Item label="最近登录">{formatTime(user.last_login_at)}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="修改密码">
          <Form<PasswordForm> form={pwForm} layout="vertical" onFinish={(v) => void changePassword(v)} requiredMark={false} className="max-w-[420px]">
            <Form.Item name="current_password" label="当前密码" rules={[{ required: true, message: '请输入当前密码' }]}>
              <Input.Password autoComplete="current-password" data-testid="pw-current" />
            </Form.Item>
            <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请设置新密码' }, { min: 8, message: '至少 8 位' }]}>
              <Input.Password autoComplete="new-password" data-testid="pw-new" />
            </Form.Item>
            <Form.Item
              name="confirm"
              label="再输一次新密码"
              dependencies={['new_password']}
              rules={[
                { required: true, message: '请再输入一次新密码' },
                ({ getFieldValue }) => ({
                  validator: (_, value) => (!value || value === getFieldValue('new_password') ? Promise.resolve() : Promise.reject(new Error('两次输入的密码不一致'))),
                }),
              ]}
            >
              <Input.Password autoComplete="new-password" data-testid="pw-confirm" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={pwSaving} data-testid="pw-submit">更新密码</Button>
          </Form>
        </Card>

        {user.is_admin && (
          <Card title="注册方式" loading={!settings}>
            {settings && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <div className="font-medium">允许新用户注册</div>
                    <div className="text-xs text-gray-500">关闭后登录页只能登录，不能注册。</div>
                  </div>
                  <Switch checked={settings.enabled} loading={saving} onChange={(v) => void update({ enabled: v })} data-testid="registration-enabled" />
                </div>
                <div>
                  <div className="font-medium">邀请码</div>
                  <div className="text-xs text-gray-500 mb-2">
                    设置了邀请码，新用户注册时必须填写；清空则任何人都可以注册。把邀请码发给要加入的人即可。
                  </div>
                  <Space.Compact className="w-full max-w-[480px]">
                    <Input
                      value={codeDraft}
                      onChange={(e) => setCodeDraft(e.target.value.toUpperCase())}
                      placeholder="留空 = 开放注册"
                      maxLength={64}
                      data-testid="invite-code"
                    />
                    <Button onClick={() => void update({ invite_code: codeDraft.trim() })} loading={saving} disabled={(settings.invite_code ?? '') === codeDraft.trim()}>
                      保存
                    </Button>
                    <Button icon={<ReloadOutlined />} onClick={() => void update({ regenerate_invite_code: true })} loading={saving}>
                      重新生成
                    </Button>
                  </Space.Compact>
                  {settings.invite_code ? (
                    <div className="mt-2 text-sm">
                      当前邀请码：<Typography.Text copyable strong data-testid="invite-code-current">{settings.invite_code}</Typography.Text>
                    </div>
                  ) : (
                    <Alert className="mt-2" type="warning" showIcon message="现在没有邀请码：任何知道网址的人都能注册并使用你的生成额度。" />
                  )}
                </div>
              </div>
            )}
          </Card>
        )}

        {user.is_admin && (
          <Card title={`用户（${users.length}）`}>
            <Table<UserRead>
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={users}
              columns={[
                { title: '邮箱', dataIndex: 'email' },
                { title: '显示名', dataIndex: 'display_name', render: (v: string) => v || '—' },
                { title: '角色', dataIndex: 'is_admin', render: (v: boolean) => (v ? <Tag color="gold">管理员</Tag> : <Tag>成员</Tag>) },
                { title: '注册时间', dataIndex: 'created_at', render: (v: string | null) => formatTime(v) },
                { title: '最近登录', dataIndex: 'last_login_at', render: (v: string | null) => formatTime(v) },
              ]}
            />
          </Card>
        )}
      </div>
    </div>
  )
}

export default Settings
