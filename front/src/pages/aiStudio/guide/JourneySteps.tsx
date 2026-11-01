import React from 'react'
import { Card, Steps, Tag } from 'antd'
import { useTranslation } from 'react-i18next'

/** 用户主流程的步骤键（顺序即推荐操作顺序），文案位于 locales/<lang>/guide.json 的 steps.<key>。 */
export const JOURNEY_STEP_KEYS = ['project', 'chapter', 'extract', 'prepare', 'keyframe', 'video'] as const

type Props = {
  /** compact：横向步骤条（快速上手卡片）；detailed：逐步详细说明（使用指南页） */
  variant: 'compact' | 'detailed'
  /** 当前所处步骤（0 起），仅用于高亮；未知时不高亮 */
  current?: number
}

/**
 * 主流程步骤展示（快速上手卡片与使用指南页共用，保证两处文案与顺序一致）。
 *
 * 流程遵循页面职责约定：分镜编辑页负责「准备」，分镜工作室负责「生成」。
 */
const JourneySteps: React.FC<Props> = ({ variant, current }) => {
  const { t } = useTranslation('guide')

  if (variant === 'compact') {
    return (
      <Steps
        size="small"
        current={current ?? -1}
        responsive
        items={JOURNEY_STEP_KEYS.map((key) => ({
          title: t(`steps.${key}.title`),
          description: <span className="text-xs">{t(`steps.${key}.summary`)}</span>,
        }))}
      />
    )
  }

  return (
    <div className="space-y-3">
      {JOURNEY_STEP_KEYS.map((key, index) => {
        const details = t(`steps.${key}.details`, { returnObjects: true }) as unknown
        const lines = Array.isArray(details) ? (details as string[]) : []
        return (
          <Card
            key={key}
            size="small"
            title={
              <span>
                <Tag color="blue">{index + 1}</Tag>
                {t(`steps.${key}.title`)}
                <span className="ml-2 text-xs font-normal text-gray-500">{t(`steps.${key}.summary`)}</span>
              </span>
            }
          >
            <ol className="list-decimal pl-5 space-y-1 text-sm text-gray-700">
              {lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ol>
          </Card>
        )
      })}
    </div>
  )
}

export default JourneySteps
