import type React from 'react';
import { useState } from 'react'
import { Button, Card, Empty, Tag, message } from 'antd'
import type { CreatorBoardRead, CreatorEntityRead } from '../../../services/generated'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import { generateEntityImage } from '../actions'
import { ArtBox, SectionTitle, TaskTag, taskErrorText } from '../ui'
import { isActiveStatus } from '../taskPolling'

/** 第 2 步 · 角色场景：确认提取出的角色 / 场景 / 道具，并生成形象图。 */

const TYPE_LABEL: Record<CreatorEntityRead['type'], string> = { character: '角色', scene: '场景', prop: '道具', costume: '服装' }

type Props = {
  board: CreatorBoardRead
  onNext: () => void
  onTaskStarted: () => void
}

const EntityCard: React.FC<{ entity: CreatorEntityRead; onGenerate: (e: CreatorEntityRead) => Promise<void> }> = ({ entity, onGenerate }) => {
  const [busy, setBusy] = useState(false)
  const active = entity.image_task && isActiveStatus(entity.image_task.status)
  const error = taskErrorText(entity.image_task)
  const run = async () => {
    setBusy(true)
    try {
      await onGenerate(entity)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card size="small" bodyStyle={{ padding: 12 }} cover={<ArtBox src={entity.thumbnail || null} task={entity.image_task} placeholder={entity.type === 'character' ? '尚无形象' : '尚无参考图'} ratio={entity.type === 'character' ? 'square' : 'landscape'} />}>
      <div className="flex items-center gap-2 font-medium text-sm">
        <span className="truncate">{entity.name}</span>
        <Tag className="ml-auto">{TYPE_LABEL[entity.type]}</Tag>
      </div>
      <div className="text-gray-500 text-xs mt-1 line-clamp-2 min-h-[32px]">{entity.description || '剧本里没有更多描述'}</div>
      <div className="text-gray-400 text-[11px] mt-1">出现在 {entity.shot_count} 个镜头</div>
      {error && <div className="text-red-600 text-xs mt-1">{error}</div>}
      <div className="flex gap-2 mt-2 items-center">
        <Button size="small" type={entity.thumbnail ? 'default' : 'primary'} loading={busy} disabled={!!active} onClick={() => void run()}>
          {entity.thumbnail ? '换一张' : entity.type === 'character' ? '生成形象' : '生成参考图'}
        </Button>
        <TaskTag task={entity.image_task} />
      </div>
    </Card>
  )
}

const CastStep: React.FC<Props> = ({ board, onNext, onTaskStarted }) => {
  const [batchRunning, setBatchRunning] = useState(false)
  const generate = async (entity: CreatorEntityRead) => {
    try {
      await generateEntityImage(entity)
      onTaskStarted()
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '生成失败，请稍后重试'))
    }
  }
  const generateAll = async () => {
    const todo = board.entities.filter((e) => !e.thumbnail && !(e.image_task && isActiveStatus(e.image_task.status)))
    if (todo.length === 0) return
    setBatchRunning(true)
    try {
      for (const e of todo) await generate(e)
    } finally {
      setBatchRunning(false)
    }
  }
  const groups = (['character', 'scene', 'prop', 'costume'] as const).map((t) => ({ type: t, items: board.entities.filter((e) => e.type === t) })).filter((g) => g.items.length > 0)
  const missing = board.entities.filter((e) => !e.thumbnail).length

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">确认角色与场景</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">Jellyfish 从剧本里认出了这些人和地方。先定下形象，之后每个镜头都会沿用，画面才不会换人。</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => void generateAll()} loading={batchRunning} disabled={missing === 0}>
            全部生成形象 · {missing} 张图
          </Button>
          <Button type="primary" onClick={onNext}>下一步：分镜板</Button>
        </div>
      </div>
      {groups.length === 0 && <Empty description="剧本里没有识别出角色或场景，可以直接去分镜板" />}
      {groups.map((g) => (
        <div key={g.type} className="flex flex-col gap-2">
          <SectionTitle count={g.items.length}>{TYPE_LABEL[g.type]}</SectionTitle>
          <div className={`grid gap-3 ${g.type === 'character' ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'}`}>
            {g.items.map((e) => <EntityCard key={e.id} entity={e} onGenerate={generate} />)}
          </div>
        </div>
      ))}
    </div>
  )
}

export default CastStep
