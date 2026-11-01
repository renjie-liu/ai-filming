import React from 'react'
import { Alert, Button, Card, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import JourneySteps from './JourneySteps'
import SetupStatusBanner from './SetupStatusBanner'
import { useSetupStatus } from './useSetupStatus'

/**
 * 使用指南页（/guide）：从剧本到成片的完整操作说明。
 *
 * 为什么存在：应用界面以中文按钮为主、流程跨多个页面（项目 → 章节 → 分镜编辑 → 分镜工作室），
 * 这里集中说明每一步在哪个页面、点哪个按钮，并说明 AI 模型已由部署自动配置。
 */
const GuidePage: React.FC = () => {
  const { t } = useTranslation('guide')
  const navigate = useNavigate()
  const { loading, status } = useSetupStatus()
  const tips = t('tips.items', { returnObjects: true }) as unknown
  const tipLines = Array.isArray(tips) ? (tips as string[]) : []

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="max-w-4xl mx-auto space-y-4 pb-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Typography.Title level={4} className="!mb-1">
              {t('pageTitle')}
            </Typography.Title>
            <Typography.Paragraph type="secondary" className="!mb-0">
              {t('pageIntro')}
            </Typography.Paragraph>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/projects?create=1')}>
            {t('quickStart.createProject')}
          </Button>
        </div>

        <SetupStatusBanner status={status} loading={loading} />

        <Alert type="info" showIcon message={t('flowTitle')} description={t('flowRule')} />

        <JourneySteps variant="detailed" />

        <Card size="small" title={t('tips.title')}>
          <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700">
            {tipLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}

export default GuidePage
