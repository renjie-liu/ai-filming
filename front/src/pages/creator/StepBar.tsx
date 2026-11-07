import type React from 'react'
import { Steps } from 'antd'
import { CREATOR_STEPS, type CreatorStepKey } from './routes'

/** 顶部五步进度条：已完成 / 当前 / 待进行，可点击跳转。 */
const StepBar: React.FC<{ current: CreatorStepKey; onChange: (key: CreatorStepKey) => void; compact?: boolean }> = ({ current, onChange, compact }) => {
  const currentIndex = CREATOR_STEPS.findIndex((s) => s.key === current)
  return (
    <div className={compact ? 'overflow-x-auto' : ''}>
      <Steps
        size="small"
        responsive={false}
        current={currentIndex}
        onChange={(i) => onChange(CREATOR_STEPS[i].key)}
        items={CREATOR_STEPS.map((s) => ({ title: s.label }))}
        className={compact ? 'min-w-[560px]' : ''}
      />
    </div>
  )
}

export default StepBar
