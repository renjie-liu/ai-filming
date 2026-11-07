import type React from 'react';
import { useEffect, useState } from 'react'
import { Button, Card, Drawer, Empty, Input, InputNumber, Popconfirm, Tag, message } from 'antd'
import type { CreatorBoardRead, CreatorShotRead } from '../../../services/generated'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import { addShot, deleteShot, generateKeyframe, linkedEntities, resolveRatio, rewriteShotDescription, saveShot } from '../actions'
import { ArtBox, DurationBadge, IndexBadge, TaskTag, taskErrorText } from '../ui'
import { isActiveStatus } from '../taskPolling'

/** 第 3 步 · 分镜板：每个镜头一张卡，生成关键帧、改画面描述与时长。 */

type Props = {
  board: CreatorBoardRead
  onNext: () => void
  onTaskStarted: () => void
  onChanged: () => Promise<void> | void
  batchRef?: React.MutableRefObject<(() => void) | null>
}

function keyframeActive(shot: CreatorShotRead): boolean {
  return !!(
    (shot.keyframe_prompt_task && isActiveStatus(shot.keyframe_prompt_task.status)) ||
    (shot.keyframe_image_task && isActiveStatus(shot.keyframe_image_task.status))
  )
}

const ShotCard: React.FC<{ shot: CreatorShotRead; board: CreatorBoardRead; onEdit: () => void; onGenerate: () => Promise<void> }> = ({ shot, board, onEdit, onGenerate }) => {
  const [busy, setBusy] = useState(false)
  const active = keyframeActive(shot)
  const error = taskErrorText(shot.keyframe_image_task) ?? taskErrorText(shot.keyframe_prompt_task)
  const refs = linkedEntities(shot, board)
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
          badge={<IndexBadge index={shot.index} />}
          corner={<DurationBadge seconds={shot.duration} />}
          onClick={onEdit}
        />
      }
    >
      <div className="font-medium text-sm truncate">{shot.title}</div>
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

const StoryboardStep: React.FC<Props> = ({ board, onNext, onTaskStarted, onChanged, batchRef }) => {
  const [editing, setEditing] = useState<CreatorShotRead | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [duration, setDuration] = useState(4)
  const [saving, setSaving] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [batchRunning, setBatchRunning] = useState(false)
  const ratio = resolveRatio(board)

  useEffect(() => {
    if (!editing) return
    setTitle(editing.title)
    setDescription(editing.description)
    setDuration(editing.duration || 4)
  }, [editing])

  const generate = async (shot: CreatorShotRead) => {
    try {
      await generateKeyframe({ shot, board, ratio })
      onTaskStarted()
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '关键帧生成失败'))
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

  const save = async () => {
    if (!editing) return
    setSaving(true)
    try {
      await saveShot({ shotId: editing.id, title: title.trim() || editing.title, description: description.trim(), duration })
      message.success('已保存')
      setEditing(null)
      await onChanged()
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '保存失败'))
    } finally {
      setSaving(false)
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
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), 'AI 改写失败'))
    } finally {
      setRewriting(false)
    }
  }
  const remove = async () => {
    if (!editing) return
    try {
      await deleteShot(editing.id)
      setEditing(null)
      await onChanged()
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '删除失败'))
    }
  }
  const add = async () => {
    const index = board.shots.reduce((m, s) => Math.max(m, s.index), 0) + 1
    try {
      await addShot({ chapterId: board.chapter.id, index, title: `镜头 ${index}`, excerpt: '' })
      await onChanged()
      message.success('已添加镜头，点卡片补充画面描述')
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '添加失败'))
    }
  }

  const missing = board.shots.filter((s) => !s.keyframe_url).length
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">分镜板</h1>
          <p className="text-gray-500 text-sm m-0 mt-1">
            {board.summary.shot_count} 个镜头 · 共 {board.summary.total_seconds} 秒 · 点击镜头可以改画面描述和时长。
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
            <ShotCard key={s.id} shot={s} board={board} onEdit={() => setEditing(s)} onGenerate={() => generate(s)} />
          ))}
        </div>
      )}
      <Drawer open={!!editing} onClose={() => setEditing(null)} title={editing ? `镜头 ${editing.index} · ${editing.title}` : ''} width={480} destroyOnClose>
        {editing && (
          <div className="flex flex-col gap-4">
            <p className="text-gray-500 text-sm m-0">改完后，关键帧和视频会按新的描述重新生成。</p>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">标题</span>
              <Input id="shot-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">画面描述</span>
                <Button size="small" type="link" loading={rewriting} onClick={() => void rewrite()}>AI 改写画面描述</Button>
              </div>
              <Input.TextArea id="shot-description" value={description} onChange={(e) => setDescription(e.target.value)} autoSize={{ minRows: 5, maxRows: 12 }} placeholder="描述这个镜头里发生了什么、谁在画面里、镜头怎么动。留空时生成关键帧会先让 AI 写。" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">剧本片段</span>
              <div className="text-sm bg-gray-50 rounded p-2 whitespace-pre-wrap">{editing.script_excerpt || '—'}</div>
            </div>
            {editing.dialogue.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-500">对白</span>
                <div className="text-sm bg-gray-50 rounded p-2 flex flex-col gap-1">
                  {editing.dialogue.map((d, i) => (
                    <div key={i}>{d.speaker ? <b className="font-medium">{d.speaker}：</b> : null}{d.text}</div>
                  ))}
                </div>
              </div>
            )}
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">时长（秒）· Seedance 2.5 支持 4–30 秒</span>
              <InputNumber id="shot-duration" min={4} max={30} value={duration} onChange={(v) => setDuration(Number(v) || 4)} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-gray-500">画面里会用到</span>
              <div className="flex flex-wrap gap-1">
                {linkedEntities(editing, board).map((e) => <Tag key={e.id} color="blue">{e.name}</Tag>)}
                {linkedEntities(editing, board).length === 0 && <span className="text-gray-400 text-sm">暂无关联，生成时按文字描述</span>}
              </div>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button type="primary" loading={saving} onClick={() => void save()}>保存</Button>
              <Button onClick={() => setEditing(null)}>取消</Button>
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
