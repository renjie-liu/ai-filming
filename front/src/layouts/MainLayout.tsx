import type React from 'react';
import { useEffect, useMemo, useState } from 'react'
import { Layout, Menu, theme, Dropdown, Space, Avatar, Select, Breadcrumb, Drawer } from 'antd'
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SettingOutlined,
  UserOutlined,
  VideoCameraOutlined,
  ApiOutlined,
} from '@ant-design/icons'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/useAppStore'
import { LANGUAGE_STORAGE_KEY } from '../i18n'
import { useIsMobile } from '../hooks/useIsMobile'
import { useTranslation } from 'react-i18next'
import { TaskCenter } from '../pages/aiStudio/components/TaskCenter'
import { TaskRuntimeProvider } from '../pages/aiStudio/components/TaskRuntimeProvider'

const { Header, Sider, Content } = Layout

const MainLayout: React.FC = () => {
  const { t, i18n } = useTranslation('layout')
  const location = useLocation()
  const navigate = useNavigate()
  const { token } = theme.useToken()

  const collapsed = useAppStore((state) => state.siderCollapsed)
  const toggleCollapsed = useAppStore((state) => state.toggleSider)
  const user = useAppStore((state) => state.user)
  const language = useAppStore((state) => state.language)
  const setLanguage = useAppStore((state) => state.setLanguage)
  const isMobile = useIsMobile()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  // 手机端：切换页面后自动收起抽屉菜单。
  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  // 让语言下拉框与 i18n 实际生效的语言保持一致（默认简体中文，用户切换后从 localStorage 读取，
  // 而 store 初始值固定为 zh-CN，否则会出现界面是英文、下拉框却显示「简体中文」的情况）。
  useEffect(() => {
    const resolved = (i18n.resolvedLanguage || i18n.language) === 'en-US' ? 'en-US' : 'zh-CN'
    if (resolved !== language) setLanguage(resolved)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i18n.resolvedLanguage])

  const selectedKeys = useMemo(() => {
    if (location.pathname === '/works' || location.pathname.startsWith('/works/')) return ['works']
    if (location.pathname.startsWith('/models')) return ['models']
    if (location.pathname.startsWith('/settings')) return ['settings']
    return []
  }, [location.pathname])

  const breadcrumbItems = useMemo(() => {
    const path = location.pathname.replace(/^\/+/, '').split('/').filter(Boolean)
    if (path.length === 0) return [{ title: t('title') }]
    const labels: Record<string, string> = {
      works: t('menu.works'),
      models: t('menu.models'),
      settings: t('menu.settings'),
    }
    const items: { title: React.ReactNode; key: string }[] = []
    path.forEach((segment, i) => {
      const href = `/${path.slice(0, i + 1).join('/')}`
      const isLast = i === path.length - 1
      const label = labels[segment] ?? (path[0] === 'works' && i === 1 ? '创作' : segment)
      items.push({ key: href, title: isLast ? label : <Link to={href}>{label}</Link> })
    })
    return items
  }, [location.pathname, t])

  const menuItems = [
    {
      key: 'works',
      icon: <VideoCameraOutlined />,
      label: <Link to="/works">{t('menu.works')}</Link>,
    },
    {
      key: 'models',
      icon: <ApiOutlined />,
      label: <Link to="/models">{t('menu.models')}</Link>,
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: <Link to="/settings">{t('menu.settings')}</Link>,
    },
  ]

  const userMenuItems = [
    {
      key: 'profile',
      label: t('user.profile'),
      onClick: () => navigate('/settings'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      label: t('user.logout'),
      onClick: () => {
        // 这里保留占位，实际项目中可接入登录逻辑
      },
    },
  ]

  /** 品牌区 + 导航菜单：桌面端放在侧边栏，手机端放在抽屉里（复用同一份结构）。 */
  const renderNav = (showText: boolean) => (
    <>
      <div className="flex items-center h-16 px-4 border-b border-solid" style={{ borderColor: token.colorBorderSecondary }}>
        <Link to="/works" className="flex items-center gap-2 min-w-0">
          <img src="/logo.svg" alt="Jellyfish" className="w-8 h-8 shrink-0" />
          {showText && (
            <div className="min-w-0">
              <div className="text-base font-semibold text-gray-900 truncate">
                {t('title')}
              </div>
              <div className="text-xs text-gray-500 truncate">
                {t('subtitle')}
              </div>
            </div>
          )}
        </Link>
      </div>

      <Menu
        mode="inline"
        selectedKeys={selectedKeys}
        items={menuItems}
        style={{ borderRight: 'none', paddingTop: 8 }}
      />
    </>
  )

  return (
    <Layout
      style={{
        // dvh：避免手机浏览器地址栏遮挡底部内容（不支持时由 100vh 兜底）
        height: '100vh',
        maxHeight: '100dvh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'row',
      }}
    >
      {isMobile ? (
        <Drawer
          placement="left"
          open={mobileNavOpen}
          onClose={() => setMobileNavOpen(false)}
          width={248}
          closable={false}
          styles={{ body: { padding: 0 } }}
        >
          {renderNav(true)}
        </Drawer>
      ) : (
        <Sider
          trigger={null}
          collapsible
          collapsed={collapsed}
          width={220}
          style={{
            flexShrink: 0,
            background: token.colorBgContainer,
            borderRight: `1px solid ${token.colorBorderSecondary}`,
            overflow: 'auto',
          }}
        >
          {renderNav(!collapsed)}
        </Sider>
      )}

      <Layout
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}
      >
        <Header
          className={`flex items-center justify-between ${isMobile ? 'px-3' : 'px-4'}`}
          style={{
            flexShrink: 0,
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            ...(isMobile ? { height: 52, lineHeight: '52px' } : {}),
          }}
        >
          <Space size={isMobile ? 'small' : 'middle'} className="flex-1 min-w-0">
            <span
              className="cursor-pointer text-xl shrink-0"
              aria-label="menu"
              onClick={isMobile ? () => setMobileNavOpen(true) : toggleCollapsed}
            >
              {isMobile || collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </span>
            {isMobile && (
              <Link to="/works" className="flex items-center gap-1.5 min-w-0">
                <img src="/logo.svg" alt="Jellyfish" className="w-6 h-6 shrink-0" />
                <span className="text-sm font-semibold text-gray-900 truncate">{t('title')}</span>
              </Link>
            )}
            <Breadcrumb
              items={breadcrumbItems}
              className="hidden sm:block"
              style={{ lineHeight: '32px' }}
            />
          </Space>

          <Space size={isMobile ? 'small' : 'middle'}>
            <Select
              size="small"
              value={language}
              style={{ width: isMobile ? 104 : 120 }}
              onChange={(value) => {
                setLanguage(value)
                void i18n.changeLanguage(value)
                window.localStorage.setItem(LANGUAGE_STORAGE_KEY, value)
                document.documentElement.lang = value === 'en-US' ? 'en' : 'zh-CN'
              }}
              options={[
                { label: t('lang.zh'), value: 'zh-CN' },
                { label: t('lang.en'), value: 'en-US' },
              ]}
            />

            <Dropdown
              menu={{
                items: userMenuItems,
              }}
              placement="bottomRight"
            >
              <div className="flex items-center gap-2 cursor-pointer">
                <Avatar size={isMobile ? 28 : 32} icon={<UserOutlined />} />
                <div className="hidden md:flex flex-col leading-tight">
                  <span className="text-sm font-medium text-gray-800">{user.name}</span>
                  <span className="text-xs text-gray-500">{user.role}</span>
                </div>
              </div>
            </Dropdown>
          </Space>
        </Header>

        <TaskRuntimeProvider>
          <Content
            style={{
              margin: 0,
              padding: 5,
              background: token.colorBgLayout,
              flex: 1,
              minHeight: 0,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div className="w-full h-full min-h-0 overflow-hidden flex flex-col">
              <Outlet />
            </div>
          </Content>
          <TaskCenter />
        </TaskRuntimeProvider>
      </Layout>
    </Layout>
  )
}

export default MainLayout
