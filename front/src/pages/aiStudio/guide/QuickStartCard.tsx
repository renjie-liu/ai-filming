import React, { useState } from 'react'
import { Button, Card, Space } from 'antd'
import { CompassOutlined, PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import JourneySteps from './JourneySteps'
import SetupStatusBanner from './SetupStatusBanner'
import { useSetupStatus } from './useSetupStatus'

/** 用户点击「不再显示」后写入的 localStorage 键。 */
export const QUICK_START_DISMISSED_KEY = 'jellyfish_quick_start_dismissed_v1'

type Props = {
  /** 用户已有项目数量；为 0 时始终展示卡片并高亮第一步 */
  projectCount: number
  /** 打开「新建项目」弹窗 */
  onCreateProject: () => void
}

/**
 * 项目列表页顶部的「快速上手」卡片。
 *
 * 为什么存在：首次进入的用户不知道从哪开始；卡片展示 6 步主流程、AI 模型是否已就绪（无需配置 API Key），
 * 并提供「新建项目」与完整指南入口。已有项目的用户可选择不再显示。
 */
const QuickStartCard: React.FC<Props> = ({ projectCount, onCreateProject }) => {
  const { t } = useTranslation('guide')
  const navigate = useNavigate()
  const { loading, status } = useSetupStatus()
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(QUICK_START_DISMISSED_KEY) === '1'
    } catch {
      return false
    }
  })

  if (dismissed && projectCount > 0) return null

  const dismiss = () => {
    try {
      localStorage.setItem(QUICK_START_DISMISSED_KEY, '1')
    } catch {
      // 隐私模式等场景下 localStorage 不可用，仅本次隐藏
    }
    setDismissed(true)
  }

  return (
    <Card
      size="small"
      className="mb-3"
      title={
        <span>
          <CompassOutlined className="mr-2" />
          {t('quickStart.title')}
          <span className="ml-2 text-xs font-normal text-gray-500">{t('quickStart.subtitle')}</span>
        </span>
      }
      extra={
        <Space size="small">
          <Button size="small" type="link" onClick={() => navigate('/guide')}>
            {t('quickStart.openGuide')}
          </Button>
          {projectCount > 0 && (
            <Button size="small" type="text" onClick={dismiss}>
              {t('quickStart.dismiss')}
            </Button>
          )}
        </Space>
      }
    >
      <div className="space-y-3">
        <SetupStatusBanner status={status} loading={loading} />
        <JourneySteps variant="compact" current={projectCount === 0 ? 0 : undefined} />
        {projectCount === 0 && (
          <Button type="primary" icon={<PlusOutlined />} onClick={onCreateProject}>
            {t('quickStart.createProject')}
          </Button>
        )}
      </div>
    </Card>
  )
}

export default QuickStartCard
