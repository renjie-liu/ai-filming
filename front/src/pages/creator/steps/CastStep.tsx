import type React from 'react'
import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Drawer, Empty, Input, Modal, Popconfirm, Segmented, Select, Tag, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { CreatorBoardRead, CreatorEntityRead } from '../../../services/generated'
import { useIsMobile } from '../../../hooks/useIsMobile'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import {
  adoptEntityImage,
  createEntity,
  deleteEntity,
  generateCharacterViews,
  generateEntityImage,
  generateEntityImages,
  renderEntityPrompt,
  setEntityShots,
  updateEntity,
  uploadEntityImage,
} from '../actions'
import ImagePickButton from '../ImagePickButton'
import { CREATABLE_ENTITY_TYPES, DEFAULT_CHARACTER_VIEWS, ENTITY_TYPE_LABEL, viewAngleLabel, type CreatorEntityType } from '../labels'
import { ArtBox, CandidateStrip, SectionTitle, TaskTag, taskErrorText } from '../ui'
import { isActiveStatus } from '../taskPolling'

/**
 * 第 2 步 · 角色场景：剧本里认出来的人和地方，都是可编辑的资产卡。
 *
 * 每张卡可以：AI 生成形象（一次 1–4 张候选，提示词可先看可改）、在历史候选里挑一张 / 回退、上传自己的图、
 * 改名称 / 设定、选它出现在哪些镜头、删除；角色还能以正面形象派生侧面 / 背面（三视图），转身镜头不换脸。
 * 也可以手动新增角色 / 场景 / 道具。其它集建过档的实体也会列出（标「本集未用到」），方便沿用。
 */

const COUNT_OPTIONS = [1, 2, 4].map((n) => ({ value: n, label: `${n} 张` }))

type Props = {
  board: CreatorBoardRead
  onNext: () => void
  onTaskStarted: () => void
  onChanged: () => Promise<void> | void
}

const errText = (e: unknown, fallback: string) => localizeErrorMessage(e instanceof Error ? e.message : String(e), fallback)
const pad = (n: number) => String(n).padStart(2, '0')

function useShotOptions(board: CreatorBoardRead) {
  return useMemo(() => board.shots.map((s) => ({ value: s.id, label: `${pad(s.index)} ${s.title}` })), [board.shots])
}

const EntityCard: React.FC<{ entity: CreatorEntityRead; onGenerate: (e: CreatorEntityRead) => Promise<void>; onEdit: () => void }> = ({ entity, onGenerate, onEdit }) => {
  const [busy, setBusy] = useState(false)
  const active = entity.image_task && isActiveStatus(entity.image_task.status)
  const error = entity.thumbnail ? null : taskErrorText(entity.image_task)
  const run = async () => {
    setBusy(true)
    try {
      await onGenerate(entity)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card
      size="small"
      bodyStyle={{ padding: 12 }}
      cover={
        <ArtBox
          src={entity.thumbnail || null}
          task={entity.image_task}
          placeholder={entity.type === 'character' ? '尚无形象' : '尚无参考图'}
          ratio={entity.type === 'character' ? 'square' : 'landscape'}
          onClick={onEdit}
        />
      }
    >
      <div className="flex items-center gap-2 font-medium text-sm">
        <span className="truncate">{entity.name}</span>
        <Tag className="ml-auto">{ENTITY_TYPE_LABEL[entity.type]}</Tag>
      </div>
      <div className="text-gray-500 text-xs mt-1 line-clamp-2 min-h-[32px]">{entity.description || '还没有设定描述，点「编辑」补充'}</div>
      <div className="text-gray-400 text-[11px] mt-1">{entity.shot_count > 0 ? `出现在 ${entity.shot_count} 个镜头` : '本集未用到 · 可在编辑里选镜头'}</div>
      {error && <div className="text-red-600 text-xs mt-1">{error}</div>}
      <div className="flex gap-2 mt-2 items-center">
        <Button size="small" type={entity.thumbnail ? 'default' : 'primary'} loading={busy} disabled={!!active} onClick={() => void run()}>
          {entity.thumbnail ? '换一张' : entity.type === 'character' ? '生成形象' : '生成参考图'}
        </Button>
        <Button size="small" type="text" onClick={onEdit}>编辑</Button>
        <TaskTag task={entity.image_task} />
      </div>
    </Card>
  )
}

/** 实体编辑抽屉：形象（生成 / 上传）、名称、设定、提示词、出现镜头、删除。 */
const EntityDrawer: React.FC<{
  entity: CreatorEntityRead | null
  board: CreatorBoardRead
  onClose: () => void
  onTaskStarted: () => void
  onChanged: () => Promise<void> | void
}> = ({ entity, board, onClose, onTaskStarted, onChanged }) => {
  const isMobile = useIsMobile()
  const shotOptions = useShotOptions(board)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [shotIds, setShotIds] = useState<string[]>([])
  const [prompt, setPrompt] = useState<string | null>(null)
  const [promptDirty, setPromptDirty] = useState(false)
  const [promptLoading, setPromptLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [count, setCount] = useState(1)
  const [viewsRunning, setViewsRunning] = useState(false)

  // 抽屉打开时按实体初始化；聚合轮询刷新时不覆盖用户正在改的内容
  const entityId = entity?.id
  useEffect(() => {
    if (!entity) return
    setName(entity.name)
    setDescription(entity.description)
    setShotIds(entity.shot_ids)
    setPrompt(null)
    setPromptDirty(false)
    setCount(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityId])

  if (!entity) return <Drawer open={false} onClose={onClose} />

  const basicsDirty = name.trim() !== entity.name || description !== entity.description
  const shotsDirty = shotIds.slice().sort().join() !== entity.shot_ids.slice().sort().join()
  const active = entity.image_task && isActiveStatus(entity.image_task.status)
  const error = entity.thumbnail ? null : taskErrorText(entity.image_task)

  const saveBasics = async (): Promise<boolean> => {
    if (basicsDirty) await updateEntity(entity, { name, description })
    if (shotsDirty) await setEntityShots(board.chapter.id, entity, shotIds)
    return basicsDirty || shotsDirty
  }
  const save = async () => {
    setSaving(true)
    try {
      const changed = await saveBasics()
      if (changed) await onChanged()
      message.success('已保存')
      onClose()
    } catch (e) {
      message.error(errText(e, '保存失败'))
    } finally {
      setSaving(false)
    }
  }
  const loadPrompt = async () => {
    setPromptLoading(true)
    try {
      if (basicsDirty) {
        await updateEntity(entity, { name, description })
        await onChanged()
      }
      const rendered = await renderEntityPrompt({ ...entity, name: name.trim() || entity.name, description })
      setPrompt(rendered.prompt)
      setPromptDirty(false)
    } catch (e) {
      message.error(errText(e, '提示词渲染失败'))
    } finally {
      setPromptLoading(false)
    }
  }
  const generate = async () => {
    setGenerating(true)
    try {
      const changed = await saveBasics()
      await generateEntityImages(entity, count, promptDirty && prompt ? prompt : undefined)
      if (changed) await onChanged()
      onTaskStarted()
      message.success(count > 1 ? `已开始生成 ${count} 张候选，完成后在「历史候选」里挑一张` : '已开始生成，完成后会自动显示')
    } catch (e) {
      message.error(errText(e, '生成失败，请稍后重试'))
    } finally {
      setGenerating(false)
    }
  }
  const upload = async (file: File) => {
    await uploadEntityImage(entity, file, { projectId: board.project.id, chapterId: board.chapter.id })
    await onChanged()
    message.success('已换成你上传的图片')
  }
  const adopt = async (fileId: string) => {
    try {
      await adoptEntityImage(entity, fileId)
      await onChanged()
      message.success('已采用这张')
    } catch (e) {
      message.error(errText(e, '切换失败'))
    }
  }
  const makeViews = async () => {
    setViewsRunning(true)
    try {
      const n = await generateCharacterViews(entity, DEFAULT_CHARACTER_VIEWS)
      await onChanged()
      onTaskStarted()
      message.success(`已开始生成 ${n} 个视角，完成后会自动显示`)
    } catch (e) {
      message.error(errText(e, '三视图生成失败'))
    } finally {
      setViewsRunning(false)
    }
  }
  const remove = async () => {
    try {
      await deleteEntity(entity)
      onClose()
      await onChanged()
      message.success('已删除')
    } catch (e) {
      message.error(errText(e, '删除失败'))
    }
  }

  const isCharacter = entity.type === 'character'
  return (
    <Drawer open onClose={onClose} title={`${ENTITY_TYPE_LABEL[entity.type]} · ${entity.name}`} width={isMobile ? '100%' : 520} destroyOnClose>
      <div className="flex flex-col gap-4">
        <div className="flex gap-3">
          <div className={isCharacter ? 'w-36 shrink-0' : 'w-48 shrink-0'}>
            <ArtBox src={entity.thumbnail || null} task={entity.image_task} placeholder={isCharacter ? '尚无形象' : '尚无参考图'} ratio={isCharacter ? 'square' : 'landscape'} />
          </div>
          <div className="flex-1 min-w-0 flex flex-col gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <TaskTag task={entity.image_task} />
              {entity.shot_count > 0 ? <span className="text-xs text-gray-500">出现在 {entity.shot_count} 个镜头</span> : <Tag>本集未用到</Tag>}
            </div>
            {error && <div className="text-red-600 text-xs">{error}</div>}
            <div className="flex gap-2 items-center">
              <Button type="primary" loading={generating} disabled={!!active} onClick={() => void generate()}>
                {entity.thumbnail ? 'AI 重新生成' : isCharacter ? 'AI 生成形象' : 'AI 生成参考图'}
              </Button>
              <Select id="entity-count" size="middle" value={count} onChange={(v) => setCount(Number(v))} options={COUNT_OPTIONS} className="w-20" aria-label="生成张数" />
            </div>
            <ImagePickButton onPick={upload} size="middle" disabled={!!active}>上传自己的图片</ImagePickButton>
            <span className="text-xs text-gray-400">一次生成多张可以挑一张；上传的图会直接作为{isCharacter ? '形象' : '参考图'}；AI 生成按下方提示词出图。</span>
          </div>
        </div>

        <CandidateStrip candidates={entity.image_candidates} onAdopt={adopt} ratio={isCharacter ? 'square' : 'landscape'} disabled={!!active} />

        {isCharacter && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-500">其它视角（侧面 / 背面，视频里转身也不换脸）</span>
              <Button size="small" type="link" loading={viewsRunning} disabled={!entity.thumbnail || !!active} onClick={() => void makeViews()}>
                {entity.views.length > 0 ? '重新生成三视图' : '生成三视图'}
              </Button>
            </div>
            {entity.views.length === 0 ? (
              <div className="text-xs text-gray-400 bg-gray-50 rounded p-2">{entity.thumbnail ? '以当前正面形象为参考，派生左侧面与背面各一张；生成视频时会一并作为参考。' : '先定下正面形象，再派生其它视角。'}</div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1" data-testid="view-strip">
                {entity.views.map((v) => (
                  <div key={v.image_id} className="w-24 shrink-0 flex flex-col gap-1">
                    <ArtBox src={v.url || null} task={v.task} placeholder={viewAngleLabel(v.view_angle)} ratio="square" />
                    <div className="flex items-center justify-between text-[11px] text-gray-500">
                      <span>{viewAngleLabel(v.view_angle)}</span>
                      {v.task && v.task.status === 'failed' && <Tag color="error" className="m-0 text-[10px]">失败</Tag>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-col gap-1">
          <span className="text-xs text-gray-500">名称</span>
          <Input id="entity-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-gray-500">{isCharacter ? '人物设定（年龄、外貌、服装、气质）' : '描述（样子、光线、氛围）'}</span>
          <Input.TextArea id="entity-description" value={description} onChange={(e) => setDescription(e.target.value)} autoSize={{ minRows: 3, maxRows: 8 }} placeholder="写得越具体，形象越稳定；会写进生成提示词。" />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">生成提示词</span>
            <Button size="small" type="link" loading={promptLoading} onClick={() => void loadPrompt()}>
              {prompt === null ? '查看提示词' : '按当前设定重新渲染'}
            </Button>
          </div>
          {prompt === null ? (
            <div className="text-xs text-gray-400 bg-gray-50 rounded p-2">默认由名称、设定与作品风格自动生成；点「查看提示词」可以先看、改好再出图。</div>
          ) : (
            <Input.TextArea
              id="entity-prompt"
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                setPromptDirty(true)
              }}
              autoSize={{ minRows: 4, maxRows: 12 }}
            />
          )}
          {promptDirty && <span className="text-xs text-blue-600">已修改，点「AI 生成」会按改过的提示词出图。</span>}
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs text-gray-500">出现在哪些镜头</span>
          <Select
            id="entity-shots"
            mode="multiple"
            value={shotIds}
            onChange={(v) => setShotIds(v)}
            options={shotOptions}
            placeholder="不选表示本集不用到；关键帧和视频生成时只参考画面里有它的镜头"
            maxTagCount="responsive"
          />
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button type="primary" loading={saving} onClick={() => void save()}>保存</Button>
          <Button onClick={onClose}>取消</Button>
          <Popconfirm title={`删除「${entity.name}」？`} description="会从所有镜头解除关联，并删除它的形象图。" okText="删除" cancelText="取消" onConfirm={() => void remove()}>
            <Button danger type="text" className="ml-auto">删除</Button>
          </Popconfirm>
        </div>
      </div>
    </Drawer>
  )
}

/** 新增角色 / 场景 / 道具。 */
const AddEntityModal: React.FC<{
  open: boolean
  board: CreatorBoardRead
  defaultType: CreatorEntityType
  onClose: () => void
  onCreated: () => Promise<void> | void
}> = ({ open, board, defaultType, onClose, onCreated }) => {
  const shotOptions = useShotOptions(board)
  const [type, setType] = useState<CreatorEntityType>(defaultType)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [shotIds, setShotIds] = useState<string[]>([])
  const [creating, setCreating] = useState(false)
  useEffect(() => {
    if (!open) return
    setType(defaultType)
    setName('')
    setDescription('')
    setShotIds([])
  }, [open, defaultType])
  const submit = async () => {
    if (!name.trim()) {
      message.warning('请填写名称')
      return
    }
    setCreating(true)
    try {
      const { reused } = await createEntity({ chapterId: board.chapter.id, type, name, description, shotIds })
      await onCreated()
      message.success(reused ? `已有同名${ENTITY_TYPE_LABEL[type]}「${name.trim()}」，已沿用并关联到所选镜头` : `已新增${ENTITY_TYPE_LABEL[type]}「${name.trim()}」，点卡片可以生成形象`)
      onClose()
    } catch (e) {
      message.error(errText(e, '新增失败'))
    } finally {
      setCreating(false)
    }
  }
  return (
    <Modal open={open} title="新增角色 / 场景 / 道具" onCancel={onClose} onOk={() => void submit()} okText="新增" cancelText="取消" confirmLoading={creating} destroyOnClose>
      <div className="flex flex-col gap-3 pt-2">
        <Segmented value={type} onChange={(v) => setType(v as CreatorEntityType)} options={CREATABLE_ENTITY_TYPES.map((t) => ({ value: t, label: ENTITY_TYPE_LABEL[t] }))} />
        <Input id="new-entity-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={type === 'character' ? '角色名，如：雷霆总监' : type === 'scene' ? '场景名，如：清晨的开放式办公区' : '道具名，如：闪电形状马克杯'} maxLength={60} />
        <Input.TextArea id="new-entity-description" value={description} onChange={(e) => setDescription(e.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} placeholder={type === 'character' ? '年龄、外貌、服装、气质' : '样子、光线、氛围'} />
        <Select id="new-entity-shots" mode="multiple" value={shotIds} onChange={(v) => setShotIds(v)} options={shotOptions} placeholder="出现在哪些镜头（可以之后再选）" maxTagCount="responsive" />
      </div>
    </Modal>
  )
}

const CastStep: React.FC<Props> = ({ board, onNext, onTaskStarted, onChanged }) => {
  const [batchRunning, setBatchRunning] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [adding, setAdding] = useState<CreatorEntityType | null>(null)
  const editing = useMemo(() => board.entities.find((e) => e.id === editingId) ?? null, [board.entities, editingId])

  const generate = async (entity: CreatorEntityRead) => {
    try {
      await generateEntityImage(entity)
      onTaskStarted()
    } catch (e) {
      message.error(errText(e, '生成失败，请稍后重试'))
    }
  }
  // 批量只管本集用到的实体；沿用自其它集但本集未选镜头的不生成
  const todoAll = board.entities.filter((e) => e.shot_count > 0 && !e.thumbnail && !(e.image_task && isActiveStatus(e.image_task.status)))
  const generateAll = async () => {
    if (todoAll.length === 0) return
    setBatchRunning(true)
    try {
      for (const e of todoAll) await generate(e)
    } finally {
      setBatchRunning(false)
    }
  }
  const groups = (['character', 'scene', 'prop', 'costume'] as const)
    .map((t) => ({ type: t, items: board.entities.filter((e) => e.type === t) }))
    .filter((g) => g.items.length > 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">角色与场景</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">
            Jellyfish 从剧本里认出了这些人和地方。点卡片可以改设定、看并改提示词、上传自己的图、选它出现在哪些镜头；定下形象后每个镜头都会沿用。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void generateAll()} loading={batchRunning} disabled={todoAll.length === 0}>
            全部生成形象 · {todoAll.length} 张图
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => setAdding('character')}>新增</Button>
          <Button type="primary" onClick={onNext}>下一步：分镜板</Button>
        </div>
      </div>
      {groups.length === 0 && (
        <Empty description="剧本里没有识别出角色或场景">
          <Button type="primary" onClick={() => setAdding('character')}>手动新增一个</Button>
        </Empty>
      )}
      {groups.map((g) => (
        <div key={g.type} className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <SectionTitle count={g.items.length}>{ENTITY_TYPE_LABEL[g.type]}</SectionTitle>
            {g.type !== 'costume' && (
              <Button size="small" type="link" className="px-0" onClick={() => setAdding(g.type)}>+ 新增{ENTITY_TYPE_LABEL[g.type]}</Button>
            )}
          </div>
          <div className={`grid gap-3 ${g.type === 'character' ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'}`}>
            {g.items.map((e) => <EntityCard key={e.id} entity={e} onGenerate={generate} onEdit={() => setEditingId(e.id)} />)}
          </div>
        </div>
      ))}
      <EntityDrawer entity={editing} board={board} onClose={() => setEditingId(null)} onTaskStarted={onTaskStarted} onChanged={onChanged} />
      <AddEntityModal open={adding !== null} board={board} defaultType={adding ?? 'character'} onClose={() => setAdding(null)} onCreated={onChanged} />
    </div>
  )
}

export default CastStep
