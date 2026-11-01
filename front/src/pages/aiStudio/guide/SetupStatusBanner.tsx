import React from 'react'
import { Alert, Button, Tag } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { SetupStatusRead } from '../../../services/generated'

type Props = {
  /** 由 useSetupStatus 提供的状态；null 表示接口不可用（不渲染任何内容） */
  status: SetupStatusRead | null
  loading?: boolean
  /** 在模型管理页展示「部署托管，Key 无需在此填写」的补充说明 */
  showManagedHint?: boolean
  className?: string
}

/**
 * 开箱即用状态横幅。
 *
 * 为什么存在：部署时已用环境变量接入 Seedance 并自动配置默认模型，用户不需要再去「模型管理」填写 API Key；
 * 该横幅明确告知这一点，并在缺少默认模型时给出唯一的处理入口。
 */
const SetupStatusBanner: React.FC<Props> = ({ status, loading, showManagedHint, className }) => {
  const { t } = useTranslation('guide')
  const navigate = useNavigate()

  if (loading) {
    return <Alert className={className} type="info" showIcon message={t('setup.loading')} />
  }
  if (!status) return null

  if (status.ready) {
    const params = {
      provider: status.managed_provider?.label ?? '',
      text: status.text_model?.name ?? '—',
      image: status.image_model?.name ?? '—',
      video: status.video_model?.name ?? '—',
    }
    const managed = status.managed_provider?.managed_by_deployment
    return (
      <Alert
        className={className}
        type="success"
        showIcon
        message={
          <span>
            {t('setup.readyTitle')}
            {managed && (
              <Tag color="green" className="ml-2">
                {t('setup.managedTag')}
              </Tag>
            )}
          </span>
        }
        description={
          <div className="space-y-1">
            <div>{managed ? t('setup.readyDesc', params) : t('setup.readyDescGeneric', params)}</div>
            {showManagedHint && managed && <div className="text-gray-500">{t('setup.managedHint')}</div>}
          </div>
        }
      />
    )
  }

  const missing = (status.missing ?? []).map((c) => t(`setup.categories.${c}`)).join(' / ')
  return (
    <Alert
      className={className}
      type="warning"
      showIcon
      message={t('setup.notReadyTitle', { missing })}
      description={t('setup.notReadyDesc')}
      action={
        <Button size="small" onClick={() => navigate('/models')}>
          {t('setup.goModels')}
        </Button>
      }
    />
  )
}

export default SetupStatusBanner
