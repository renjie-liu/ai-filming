import type React from 'react'
import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Drawer, Empty, Input, InputNumber, Popconfirm, Select, Tag, message } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import type { CreatorBoardRead, CreatorEntityRead, CreatorShotRead } from '../../../services/generated'
import { useIsMobile } from '../../../hooks/useIsMobile'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import {
  addShot,
  adoptShotKeyframe,
  deleteShot,
  generateKeyframe,
  generatePreviewGrid,
  linkedEntities,
  resolveRatio,
  rewriteShotDescription,
  saveDialogue,
  saveShot,
  setShotLinks,
  uploadShotKeyframe,
  type DialogueDraft,
} from '../actions'
import ImagePickButton from '../ImagePickButton'
import { CAMERA_ANGLE_OPTIONS, CAMERA_MOVEMENT_OPTIONS, CAMERA_SHOT_OPTIONS, ENTITY_TYPE_LABEL, cameraAngleLabel, cameraMovementLabel, cameraShotLabel } from '../labels'
import { ArtBox, CandidateStrip, DurationBadge, IndexBadge, TaskTag, taskErrorText } from '../ui'
import { isActiveStatus } from '../taskPolling'

/**
 * 第 3 步 · 分镜板：每个镜头一张卡。
 *
 * 卡片可生成 / 重画关键帧；抽屉里可以在历史候选里挑一张关键帧 / 回退、改标题、景别、机位、运镜、动作节拍、
 * 画面描述（AI 改写）、时长、画面里会用到的角色 / 场景 / 道具、对白，也可以上传自己的图当关键帧，
 * 并在生视频前先出一张「预演四宫格」（2×2 图演四个节拍）检查节奏与连续性。
 */

type Props = {
  board: CreatorBoardRead
  onNext: () => void
  onTaskStarted: () => void
  onChanged: () => Promise<void> | void
  batchRef?: React.MutableRefObject<(() => void) | null>
}

const errText = (e: unknown, fallback: string) => localizeErrorMessage(e instanceof Error ? e.message : String(e), fallback)

function keyframeActive(shot: CreatorShotRead): boolean {
  return !!(
    (shot.keyframe_prompt_task && isActiveStatus(shot.keyframe_prompt_task.status)) ||
    (shot.keyframe_image_task && isActiveStatus(shot.keyframe_image_task.status))
  )
}

function keyframeRatio(board: CreatorBoardRead): 'portrait' | 'landscape' | 'square' {
  const r = resolveRatio(board)
  if (r === '9:16' || r === '3:4') return 'portrait'
  if (r === '1:1') return 'square'
  return 'landscape'
}

const ShotCard: React.FC<{ shot: CreatorShotRead; board: CreatorBoardRead; onEdit: () => void; onGenerate: () => Promise<void> }> = ({ shot, board, onEdit, onGenerate }) => {
  const [busy, setBusy] = useState(false)
  const active = keyframeActive(shot)
  const error = shot.keyframe_url ? null : taskErrorText(shot.keyframe_image_task) ?? taskErrorText(shot.keyframe_prompt_task)
  const refs = linkedEntities(shot, board)
  const camera = [cameraShotLabel(shot.camera_shot), cameraAngleLabel(shot.angle), cameraMovementLabel(shot.movement)].filter(Boolean).join(' · ')
  const run = async () => {
    setBusy(true)
    try {
      await onGenerate()
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
          src={shot.keyframe_url}
          task={shot.keyframe_image_task ?? shot.keyframe_prompt_task}
          placeholder="尚无关键帧"
          ratio={keyframeRatio(board)}
          badge={<IndexBadge index={shot.index} />}
          corner={<DurationBadge seconds={shot.duration} />}
          onClick={onEdit}
        />
      }
    >
      <div className="font-medium text-sm truncate">{shot.title}</div>
      {camera && <div className="text-[11px] text-gray-400 mt-0.5">{camera}</div>}
      <div className="text-gray-500 text-xs mt-1 line-clamp-2 min-h-[32px]">{shot.description || shot.script_excerpt || '点「编辑」补充画面描述'}</div>
      {shot.dialogue.length > 0 ? (
        <div className="text-xs mt-1 bg-gray-50 rounded px-2 py-1 line-clamp-2">
          <span className="text-gray-500">{shot.dialogue[0].speaker ? `${shot.dialogue[0].speaker}：` : ''}</span>
          {shot.dialogue[0].text}
          {shot.dialogue.length > 1 && <span className="text-gray-400"> 等 {shot.dialogue.length} 句</span>}
        </div>
      ) : (
        <div className="text-xs mt-1 text-gray-400 bg-gray-50 rounded px-2 py-1">无对白</div>
      )}
      {refs.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {refs.slice(0, 4).map((r) => <Tag key={r.id} className="m-0 text-[11px]">{r.name}</Tag>)}
          {refs.length > 4 && <span className="text-[11px] text-gray-400">+{refs.length - 4}</span>}
        </div>
      )}
      {error && <div className="text-red-600 text-xs mt-1">{error}</div>}
      <div className="flex gap-2 mt-2 items-center">
        <Button size="small" type={shot.keyframe_url ? 'default' : 'primary'} loading={busy} disabled={active} onClick={() => void run()}>
          {shot.keyframe_url ? '重画' : '生成关键帧'}
        </Button>
        <Button size="small" type="text" onClick={onEdit}>编辑</Button>
        <TaskTag task={shot.keyframe_image_task} />
      </div>
    </Card>
  )
}

/** 对白说话人下拉：角色 / 旁白；剧本里有名字但没建档的说话人也保留为一个选项。 */
function speakerOptions(characters: CreatorEntityRead[], drafts: DialogueDraft[]) {
  const options: Array<{ value: string; label: string }> = [{ value: '', label: '旁白 / 无' }, ...characters.map((c) => ({ value: c.id, label: c.name }))]
  const known = new Set(options.map((o) => o.value))
  for (const d of drafts) {
    if (!d.speakerCharacterId && d.speakerName && !known.has(`name:${d.speakerName}`)) {
      options.push({ value: `name:${d.speakerName}`, label: `${d.speakerName}（未建档）` })
      known.add(`name:${d.speakerName}`)
    }
  }
  return options
}

function speakerValue(d: DialogueDraft): string {
  if (d.speakerCharacterId) return d.speakerCharacterId
  return d.speakerName ? `name:${d.speakerName}` : ''
}

const StoryboardStep: React.FC<Props> = ({ board, onNext, onTaskStarted, onChanged, batchRef }) => {
  const isMobile = useIsMobile()
  const [editingId, setEditingId] = useState<string | null>(null)
  const editing = useMemo(() => board.shots.find((s) => s.id === editingId) ?? null, [board.shots, editingId])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [duration, setDuration] = useState(4)
  const [cameraShot, setCameraShot] = useState<string>('')
  const [angle, setAngle] = useState<string>('')
  const [movement, setMovement] = useState<string>('')
  const [beats, setBeats] = useState('')
  const [linkIds, setLinkIds] = useState<string[]>([])
  const [dialogue, setDialogue] = useState<DialogueDraft[]>([])
  const [saving, setSaving] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [gridRunning, setGridRunning] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)
  const ratio = resolveRatio(board)
  const characters = useMemo(() => board.entities.filter((e) => e.type === 'character'), [board.entities])

  // 打开抽屉时按镜头初始化；聚合轮询刷新（关键帧进度）时不覆盖正在编辑的内容
  useEffect(() => {
    if (!editing) return
    setTitle(editing.title)
    setDescription(editing.description)
    setDuration(editing.duration || 4)
    setCameraShot(editing.camera_shot)
    setAngle(editing.angle)
    setMovement(editing.movement)
    setBeats(editing.action_beats.join('\n'))
    setLinkIds([...editing.character_ids, ...editing.scene_ids, ...editing.prop_ids])
    setDialogue(editing.dialogue.map((d) => ({ id: d.id, speakerCharacterId: d.speaker_character_id ?? null, speakerName: d.speaker, text: d.text })))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingId])

  const generate = async (shot: CreatorShotRead) => {
    try {
      await generateKeyframe({ shot, board, ratio })
      onTaskStarted()
    } catch (e) {
      message.error(errText(e, '关键帧生成失败'))
    }
  }
  const generateAll = async () => {
    const todo = board.shots.filter((s) => !s.keyframe_url && !keyframeActive(s))
    if (todo.length === 0) return
    setBatchRunning(true)
    try {
      for (const s of todo) await generate(s)
    } finally {
      setBatchRunning(false)
    }
  }
  if (batchRef) batchRef.current = () => void generateAll()

  const splitLinks = (ids: string[]) => {
    const byId = new Map(board.entities.map((e) => [e.id, e]))
    const pick = (type: CreatorEntityRead['type']) => ids.filter((id) => byId.get(id)?.type === type)
    return { characterIds: pick('character'), sceneIds: pick('scene'), propIds: pick('prop') }
  }
  const linksDirty = (shot: CreatorShotRead) => linkIds.slice().sort().join() !== [...shot.character_ids, ...shot.scene_ids, ...shot.prop_ids].sort().join()

  /** 把抽屉里的改动写回：标题 / 描述 / 时长 / 景别 / 运镜 → 关联 → 对白。返回带新字段的镜头，供随后生成关键帧使用。 */
  const persist = async (shot: CreatorShotRead): Promise<CreatorShotRead> => {
    await saveShot({ shotId: shot.id, title: title.trim() || shot.title, description: description.trim(), duration, cameraShot, angle, movement, actionBeats: beats.split('\n') })
    const links = splitLinks(linkIds)
    if (linksDirty(shot)) await setShotLinks(shot.id, links)
    await saveDialogue(shot.id, dialogue, shot.dialogue)
    return { ...shot, title: title.trim() || shot.title, description: description.trim(), duration, character_ids: links.characterIds, scene_ids: links.sceneIds, prop_ids: links.propIds }
  }
  const save = async () => {
    if (!editing) return
    setSaving(true)
    try {
      await persist(editing)
      message.success('已保存')
      setEditingId(null)
      await onChanged()
    } catch (e) {
      message.error(errText(e, '保存失败'))
    } finally {
      setSaving(false)
    }
  }
  const saveAndGenerate = async () => {
    if (!editing) return
    setGenerating(true)
    try {
      const next = await persist(editing)
      await onChanged()
      await generateKeyframe({ shot: next, board, ratio })
      onTaskStarted()
      message.success('已开始生成关键帧')
    } catch (e) {
      message.error(errText(e, '关键帧生成失败'))
    } finally {
      setGenerating(false)
    }
  }
  const upload = async (file: File) => {
    if (!editing) return
    await uploadShotKeyframe(editing, file, { projectId: board.project.id, chapterId: board.chapter.id })
    await onChanged()
    message.success('已换成你上传的关键帧')
  }
  const adopt = async (fileId: string) => {
    if (!editing) return
    try {
      await adoptShotKeyframe(editing, fileId)
      await onChanged()
      message.success('已采用这张关键帧')
    } catch (e) {
      message.error(errText(e, '切换失败'))
    }
  }
  /** 先把抽屉里的节拍 / 镜头语言存下来（四宫格按它们画），再创建四宫格任务。 */
  const makeGrid = async () => {
    if (!editing) return
    setGridRunning(true)
    try {
      await persist(editing)
      await onChanged()
      await generatePreviewGrid(editing, ratio)
      onTaskStarted()
      message.success('已开始生成预演四宫格')
    } catch (e) {
      message.error(errText(e, '四宫格生成失败'))
    } finally {
      setGridRunning(false)
    }
  }
  const rewrite = async () => {
    if (!editing) return
    setRewriting(true)
    try {
      const next = await rewriteShotDescription(editing.id)
      if (next) setDescription(next)
      else message.warning('AI 没有给出新的描述')
    } catch (e) {
      message.error(errText(e, 'AI 改写失败'))
    } finally {
      setRewriting(false)
    }
  }
  const remove = async () => {
    if (!editing) return
    try {
      await deleteShot(editing.id)
      setEditingId(null)
      await onChanged()
    } catch (e) {
      message.error(errText(e, '删除失败'))
    }
  }
  const add = async () => {
    const index = board.shots.reduce((m, s) => Math.max(m, s.index), 0) + 1
    try {
      await addShot({ chapterId: board.chapter.id, index, title: `镜头 ${index}`, excerpt: '' })
      await onChanged()
      message.success('已添加镜头，点卡片补充画面描述')
    } catch (e) {
      message.error(errText(e, '添加失败'))
    }
  }

  const entityOptions = (['character', 'scene', 'prop'] as const)
    .map((t) => ({ label: ENTITY_TYPE_LABEL[t], options: board.entities.filter((e) => e.type === t).map((e) => ({ value: e.id, label: e.name })) }))
    .filter((g) => g.options.length > 0)
  const missing = board.shots.filter((s) => !s.keyframe_url).length
  const liveError = editing && !editing.keyframe_url ? taskErrorText(editing.keyframe_image_task) ?? taskErrorText(editing.keyframe_prompt_task) : null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">分镜板</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[64ch]">
            {board.summary.shot_count} 个镜头 · 共 {board.summary.total_seconds} 秒 · 点镜头卡可以改画面描述、景别运镜、对白和画面里的人物场景，也能上传自己的关键帧。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void generateAll()} loading={batchRunning} disabled={missing === 0}>
            生成全部关键帧 · {missing} 张图
          </Button>
          <Button type="text" onClick={() => void add()}>+ 添加镜头</Button>
          <Button type="primary" onClick={onNext}>下一步：生成视频</Button>
        </div>
      </div>
      {board.shots.length === 0 ? (
        <Empty description="还没有镜头，先回到「剧本」一键拆分镜" />
      ) : (
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {board.shots.map((s) => (
            <ShotCard key={s.id} shot={s} board={board} onEdit={() => setEditingId(s.id)} onGenerate={() => generate(s)} />
          ))}
        </div>
      )}
      <Drawer open={!!editing} onClose={() => setEditingId(null)} title={editing ? `镜头 ${editing.index} · ${editing.title}` : ''} width={isMobile ? '100%' : 560} destroyOnClose>
        {editing && (
          <div className="flex flex-col gap-4">
            {/* 关键帧：当前图 + 生成 / 上传 */}
            <div className="flex gap-3">
              <div className={keyframeRatio(board) === 'landscape' ? 'w-56 shrink-0' : 'w-32 shrink-0'}>
                <ArtBox src={editing.keyframe_url} task={editing.keyframe_image_task ?? editing.keyframe_prompt_task} placeholder="尚无关键帧" ratio={keyframeRatio(board)} />
              </div>
              <div className="flex-1 min-w-0 flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">关键帧</span>
                  <TaskTag task={editing.keyframe_image_task} />
                </div>
                {liveError && <div className="text-red-600 text-xs">{liveError}</div>}
                <Button type="primary" loading={generating} disabled={keyframeActive(editing)} onClick={() => void saveAndGenerate()}>
                  {editing.keyframe_url ? '保存并重画' : '保存并生成关键帧'}
                </Button>
                <ImagePickButton onPick={upload} size="middle" disabled={keyframeActive(editing)}>上传自己的图片</ImagePickButton>
                <span className="text-xs text-gray-400">关键帧会作为这个镜头视频的首帧；留空时视频只按文字生成。</span>
              </div>
            </div>
            <CandidateStrip candidates={editing.keyframe_candidates} onAdopt={adopt} ratio={keyframeRatio(board)} disabled={keyframeActive(editing)} />

            {/* 预演四宫格：一张图看四个节拍 */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">预演四宫格（一张图演四个节拍，先看节奏再生视频）</span>
                <Button size="small" type="link" loading={gridRunning} disabled={!!(editing.preview_grid_task && isActiveStatus(editing.preview_grid_task.status))} onClick={() => void makeGrid()}>
                  {editing.preview_grid_url ? '重新生成四宫格' : '生成四宫格'}
                </Button>
              </div>
              {editing.preview_grid_url || editing.preview_grid_task ? (
                <div className="flex gap-3 items-start">
                  <div className={keyframeRatio(board) === 'landscape' ? 'w-56 shrink-0' : 'w-32 shrink-0'}>
                    <ArtBox src={editing.preview_grid_url} task={editing.preview_grid_task} placeholder="四宫格生成中" ratio={keyframeRatio(board)} />
                  </div>
                  <div className="flex flex-col gap-1 text-xs text-gray-500">
                    <TaskTag task={editing.preview_grid_task} />
                    {taskErrorText(editing.preview_grid_task) && !editing.preview_grid_url && <span className="text-red-600">{taskErrorText(editing.preview_grid_task)}</span>}
                    <span>四格从左上到右下按时间顺序，对应动作节拍。节奏不对就改节拍再生成一次，只花一张图的费用。</span>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-gray-400 bg-gray-50 rounded p-2">按下方动作节拍、景别运镜与画面里的人物场景，画一张 2×2 连续分镜；花一张图的费用先看节奏和人物连续性。</div>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">标题</span>
              <Input id="shot-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-500">景别</span>
                <Select id="shot-camera" value={cameraShot || undefined} onChange={(v) => setCameraShot(v)} options={CAMERA_SHOT_OPTIONS} placeholder="未指定" allowClear onClear={() => setCameraShot('')} />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-500">机位</span>
                <Select id="shot-angle" value={angle || undefined} onChange={(v) => setAngle(v)} options={CAMERA_ANGLE_OPTIONS} placeholder="未指定" allowClear onClear={() => setAngle('')} />
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-500">运镜</span>
                <Select id="shot-movement" value={movement || undefined} onChange={(v) => setMovement(v)} options={CAMERA_MOVEMENT_OPTIONS} placeholder="未指定" allowClear onClear={() => setMovement('')} />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">动作节拍（每行一个；多条时按时长平均分配时间码写进视频提示词，如 [0-3s] / [3-6s]）</span>
              <Input.TextArea id="shot-beats" value={beats} onChange={(e) => setBeats(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} placeholder={'三位神端着咖啡走向白板\n雷霆总监放下马克杯，白板出现闪电\n留空时由 AI 从描述里提炼'} />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">画面描述（关键帧提示词）</span>
                <Button size="small" type="link" loading={rewriting} onClick={() => void rewrite()}>AI 改写</Button>
              </div>
              <Input.TextArea id="shot-description" value={description} onChange={(e) => setDescription(e.target.value)} autoSize={{ minRows: 5, maxRows: 12 }} placeholder="描述这个镜头里发生了什么、谁在画面里、镜头怎么动。留空时生成关键帧会先让 AI 写。" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">画面里会用到（关键帧和视频按这些形象做参考）</span>
              <Select id="shot-links" mode="multiple" value={linkIds} onChange={(v) => setLinkIds(v)} options={entityOptions} placeholder="选角色 / 场景 / 道具；没有则只按文字描述" maxTagCount="responsive" />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">对白</span>
                <Button size="small" type="link" onClick={() => setDialogue((d) => [...d, { speakerCharacterId: null, speakerName: '', text: '' }])}>+ 添加一句</Button>
              </div>
              {dialogue.length === 0 && <div className="text-xs text-gray-400 bg-gray-50 rounded p-2">无对白</div>}
              <div className="flex flex-col gap-2">
                {dialogue.map((d, i) => (
                  <div key={d.id ?? `new-${i}`} className="flex gap-2 items-start">
                    <Select
                      className="w-32 shrink-0"
                      value={speakerValue(d)}
                      options={speakerOptions(characters, dialogue)}
                      onChange={(v: string) =>
                        setDialogue((list) =>
                          list.map((x, j) =>
                            j === i
                              ? v.startsWith('name:')
                                ? { ...x, speakerCharacterId: null, speakerName: v.slice(5) }
                                : { ...x, speakerCharacterId: v || null, speakerName: characters.find((c) => c.id === v)?.name ?? '' }
                              : x,
                          ),
                        )
                      }
                    />
                    <Input.TextArea value={d.text} onChange={(e) => setDialogue((list) => list.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} autoSize={{ minRows: 1, maxRows: 4 }} placeholder="台词" />
                    <Button type="text" danger icon={<DeleteOutlined />} onClick={() => setDialogue((list) => list.filter((_, j) => j !== i))} />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">时长（秒）· Seedance 2.5 支持 4–30 秒</span>
              <InputNumber id="shot-duration" min={4} max={30} value={duration} onChange={(v) => setDuration(Number(v) || 4)} />
            </div>
            {editing.script_excerpt && (
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-500">剧本片段</span>
                <div className="text-sm bg-gray-50 rounded p-2 whitespace-pre-wrap">{editing.script_excerpt}</div>
              </div>
            )}
            <div className="flex gap-2 flex-wrap">
              <Button type="primary" loading={saving} onClick={() => void save()}>保存</Button>
              <Button onClick={() => setEditingId(null)}>取消</Button>
              <Popconfirm title="删除这个镜头？" okText="删除" cancelText="取消" onConfirm={() => void remove()}>
                <Button danger type="text" className="ml-auto">删除镜头</Button>
              </Popconfirm>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}

export default StoryboardStep
