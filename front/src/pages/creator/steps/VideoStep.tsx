import type React from 'react'
import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Checkbox, Drawer, Input, Progress, Segmented, Table, Tag, message } from 'antd'
import type { CreatorBoardRead, CreatorShotRead } from '../../../services/generated'
import { useIsMobile } from '../../../hooks/useIsMobile'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import { generateVideo, isRealPersonRejection, previewVideoPrompt, resolveRatio, uploadShotVideo, type VideoPlan, type VideoRatio } from '../actions'
import ImagePickButton from '../ImagePickButton'
import { ArtBox, DurationBadge, IndexBadge, TaskTag, taskErrorText } from '../ui'
import { isActiveStatus } from '../taskPolling'
import { VIDEO_MODE_HINT, VIDEO_MODE_LABEL, defaultVideoMode, describeVideoMode, referenceCandidates, type VideoMode } from '../videoPlan'

/**
 * 第 4 步 · 视频：先出确认单，开始后变成进度板；失败可单独重试。
 *
 * 每个镜头可以打开抽屉：选参考方式（形象参考 / 首帧图 / 仅文字）、勾选参考素材、
 * 看并改最终发给模型的提示词，或者直接上传自己的视频片段作为成片。
 */

type Props = {
  board: CreatorBoardRead
  onBack: () => void
  onFinal: () => void
  onTaskStarted: () => void
  onChanged: () => Promise<void> | void
  onEditShot: () => void
  startRef?: React.MutableRefObject<(() => void) | null>
}

const errText = (e: unknown, fallback: string) => localizeErrorMessage(e instanceof Error ? e.message : String(e), fallback)

export function videoStarted(board: CreatorBoardRead): boolean {
  return board.shots.some((s) => s.video_task || s.video_file_id)
}

/** 把「模式 + 勾选的素材」变成提交方案；素材不够时自动降级（形象参考 → 首帧 → 仅文字）。 */
function planFor(shot: CreatorShotRead, board: CreatorBoardRead, mode: VideoMode, selected?: string[]): VideoPlan {
  if (mode === 'reference') {
    const refs = referenceCandidates(shot, board).filter((r) => !selected || selected.includes(r.file_id))
    if (refs.length > 0) return { mode: 'reference', images: refs.map((r) => r.file_id), labels: refs.map((r) => r.label) }
  }
  if (mode !== 'text_only' && shot.keyframe_file_id) return { mode: 'first', images: [shot.keyframe_file_id] }
  return { mode: 'text_only', images: [] }
}

/** 单个镜头的视频设置抽屉。 */
const VideoDrawer: React.FC<{
  shot: CreatorShotRead | null
  board: CreatorBoardRead
  ratio: VideoRatio
  onClose: () => void
  onTaskStarted: () => void
  onChanged: () => Promise<void> | void
}> = ({ shot, board, ratio, onClose, onTaskStarted, onChanged }) => {
  const isMobile = useIsMobile()
  const [mode, setMode] = useState<VideoMode>('text_only')
  const [selected, setSelected] = useState<string[]>([])
  const [prompt, setPrompt] = useState('')
  const [promptDirty, setPromptDirty] = useState(false)
  const [loadingPrompt, setLoadingPrompt] = useState(false)
  const [generating, setGenerating] = useState(false)
  const shotId = shot?.id
  const candidates = useMemo(() => (shot ? referenceCandidates(shot, board) : []), [shot, board])

  useEffect(() => {
    if (!shot) return
    setMode(defaultVideoMode(shot, board))
    setSelected(referenceCandidates(shot, board).map((r) => r.file_id))
    setPrompt('')
    setPromptDirty(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId])

  const selectedKey = selected.join(',')
  useEffect(() => {
    if (!shot || promptDirty) return
    let cancelled = false
    setLoadingPrompt(true)
    previewVideoPrompt({ shot, ratio, plan: planFor(shot, board, mode, selected) })
      .then((r) => {
        if (!cancelled) setPrompt(r.prompt)
      })
      .catch((e) => {
        if (!cancelled) message.error(errText(e, '提示词渲染失败'))
      })
      .finally(() => {
        if (!cancelled) setLoadingPrompt(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId, mode, selectedKey, promptDirty])

  if (!shot) return <Drawer open={false} onClose={onClose} />

  const plan = planFor(shot, board, mode, selected)
  const effectiveMode = plan.mode as VideoMode
  const active = shot.video_task && isActiveStatus(shot.video_task.status)

  const generate = async () => {
    setGenerating(true)
    try {
      await generateVideo({ shot, ratio, plan, prompt: promptDirty ? prompt : undefined })
      onTaskStarted()
      message.success('已开始生成这个镜头的视频')
      onClose()
    } catch (e) {
      message.error(errText(e, '视频任务创建失败'))
    } finally {
      setGenerating(false)
    }
  }
  const upload = async (file: File) => {
    await uploadShotVideo(shot, file, { projectId: board.project.id, chapterId: board.chapter.id })
    await onChanged()
    message.success('已把你上传的视频作为这个镜头的成片')
    onClose()
  }

  return (
    <Drawer open onClose={onClose} title={`镜头 ${shot.index} · ${shot.title}`} width={isMobile ? '100%' : 560} destroyOnClose>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-gray-500">参考方式</span>
          <Segmented
            value={mode}
            onChange={(v) => {
              setMode(v as VideoMode)
              setPromptDirty(false)
            }}
            options={[
              { value: 'reference', label: VIDEO_MODE_LABEL.reference, disabled: candidates.length === 0 },
              { value: 'first', label: VIDEO_MODE_LABEL.first, disabled: !shot.keyframe_file_id },
              { value: 'text_only', label: VIDEO_MODE_LABEL.text_only },
            ]}
          />
          <span className="text-xs text-gray-400">{VIDEO_MODE_HINT[mode]}</span>
          {effectiveMode !== mode && <span className="text-xs text-orange-500">所选素材不足，实际会按「{VIDEO_MODE_LABEL[effectiveMode]}」生成。</span>}
        </div>

        {mode === 'reference' && candidates.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-gray-500">参考素材（按勾选顺序对应提示词里的 [Image n]，最多 9 张）</span>
            <Checkbox.Group
              value={selected}
              onChange={(v) => {
                setSelected(v as string[])
                setPromptDirty(false)
              }}
              className="flex flex-col gap-1"
            >
              {candidates.map((r, i) => (
                <Checkbox key={r.file_id} value={r.file_id}>
                  <span className="inline-flex items-center gap-2">
                    {r.thumbnail && <img src={r.thumbnail} alt="" className="w-8 h-8 object-cover rounded" />}
                    <span className="text-sm">
                      <span className="text-gray-400 tabular-nums mr-1">[Image {selected.indexOf(r.file_id) >= 0 ? selected.indexOf(r.file_id) + 1 : i + 1}]</span>
                      {r.label}
                    </span>
                  </span>
                </Checkbox>
              ))}
            </Checkbox.Group>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">发给模型的提示词（可以改）</span>
            <Button size="small" type="link" loading={loadingPrompt} onClick={() => setPromptDirty(false)}>
              按当前设置重新渲染
            </Button>
          </div>
          <Input.TextArea
            id="video-prompt"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value)
              setPromptDirty(true)
            }}
            autoSize={{ minRows: 8, maxRows: 18 }}
            disabled={loadingPrompt && !prompt}
          />
          {promptDirty && <span className="text-xs text-blue-600">已修改，点「生成」按改过的提示词提交；参考素材仍按上面的勾选。</span>}
        </div>

        <div className="flex gap-2 flex-wrap items-center">
          <Button type="primary" loading={generating} disabled={!!active || loadingPrompt} onClick={() => void generate()}>
            {shot.video_file_id ? '重新生成' : '生成视频'}
          </Button>
          <Button onClick={onClose}>取消</Button>
          <span className="text-gray-400 text-xs mx-1">或</span>
          <ImagePickButton onPick={upload} size="middle" accept="video/mp4,video/quicktime,video/webm" disabled={!!active}>
            上传自己的视频
          </ImagePickButton>
        </div>
        <span className="text-xs text-gray-400">上传的视频会直接作为这个镜头的成片；mp4 / mov / webm，存储为 Vercel Blob 时支持大文件直传。</span>
      </div>
    </Drawer>
  )
}

const VideoStep: React.FC<Props> = ({ board, onBack, onFinal, onTaskStarted, onChanged, onEditShot, startRef }) => {
  const [starting, setStarting] = useState(false)
  const [retrying, setRetrying] = useState<Record<string, boolean>>({})
  const [editingId, setEditingId] = useState<string | null>(null)
  const editing = useMemo(() => board.shots.find((s) => s.id === editingId) ?? null, [board.shots, editingId])
  const ratio = resolveRatio(board)
  const started = videoStarted(board) || starting

  // 上次因参考图含真人形象被拒的镜头，重试时自动改用纯文字描述。
  const runOne = async (shot: CreatorShotRead, textOnly = false) => {
    const forceText = textOnly || isRealPersonRejection(shot.video_task?.error)
    await generateVideo({ shot, ratio, plan: planFor(shot, board, defaultVideoMode(shot, board)), textOnly: forceText })
  }
  const startAll = async () => {
    const todo = board.shots.filter((s) => !s.video_file_id && !(s.video_task && isActiveStatus(s.video_task.status)))
    if (todo.length === 0) {
      message.info('所有镜头都已生成或正在生成')
      return
    }
    setStarting(true)
    let failed = 0
    for (const s of todo) {
      try {
        await runOne(s)
      } catch (e) {
        failed += 1
        message.error(`${s.title}：${errText(e, '视频任务创建失败')}`)
      }
    }
    onTaskStarted()
    if (failed === 0) message.success(`已开始生成 ${todo.length} 段视频`)
    setStarting(false)
  }
  if (startRef) startRef.current = () => void startAll()

  const retry = async (shot: CreatorShotRead, textOnly = false) => {
    setRetrying((p) => ({ ...p, [shot.id]: true }))
    try {
      await runOne(shot, textOnly)
      onTaskStarted()
    } catch (e) {
      message.error(errText(e, '视频任务创建失败'))
    } finally {
      setRetrying((p) => ({ ...p, [shot.id]: false }))
    }
  }

  const done = board.summary.video_done_count
  const failedCount = board.shots.filter((s) => s.video_task?.status === 'failed' && !s.video_file_id).length
  const pct = board.shots.length
    ? Math.round(board.shots.reduce((a, s) => a + (s.video_file_id ? 100 : s.video_task && isActiveStatus(s.video_task.status) ? s.video_task.progress : 0), 0) / board.shots.length)
    : 0
  const referenceShots = board.shots.filter((s) => defaultVideoMode(s, board) === 'reference').length

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">{started ? '生成视频' : '确认后开始生成'}</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">
            {started
              ? '每个镜头单独生成；失败的镜头会给出原因，可以单独重试或上传自己的视频，不影响其他镜头。'
              : '生成前先确认一遍，额度只在你点「开始生成」之后才消耗。点「调整」可以改参考方式和提示词。'}
          </p>
        </div>
        {started && (
          <div className="flex gap-2">
            <Button onClick={onBack}>回到分镜板</Button>
            <Button type="primary" disabled={done === 0} onClick={onFinal}>查看成片</Button>
          </div>
        )}
      </div>

      {!started ? (
        <Card className="max-w-[760px]">
          <h2 className="text-base font-semibold m-0 mb-3">生成 {board.shots.length} 段视频</h2>
          <Table
            size="small"
            pagination={false}
            rowKey="id"
            dataSource={board.shots}
            columns={[
              { title: '镜头', dataIndex: 'title', render: (v: string, r: CreatorShotRead) => <span className="tabular-nums">{String(r.index).padStart(2, '0')} {v}</span> },
              { title: '时长', dataIndex: 'duration', width: 72, render: (v: number) => <span className="tabular-nums">{v} 秒</span> },
              {
                title: '参考',
                width: 200,
                render: (_: unknown, r: CreatorShotRead) => (
                  <span className="inline-flex items-center gap-2">
                    <span className={defaultVideoMode(r, board) === 'text_only' ? 'text-gray-400' : ''}>{describeVideoMode(r, board)}</span>
                    <Button size="small" type="link" className="px-0" onClick={() => setEditingId(r.id)}>调整</Button>
                  </span>
                ),
              },
            ]}
          />
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-gray-500 mt-3">
            <span>共 <b className="text-gray-900 font-medium tabular-nums">{board.summary.total_seconds} 秒</b></span>
            <span>比例 <b className="text-gray-900 font-medium">{ratio}</b></span>
            <span>预计 <b className="text-gray-900 font-medium">{Math.max(2, Math.ceil(board.shots.length * 0.8))}–{Math.max(4, board.shots.length * 2)} 分钟</b></span>
            {referenceShots > 0 && <span>{referenceShots} 个镜头带形象参考</span>}
          </div>
          <div className="flex flex-wrap items-center gap-3 mt-4">
            <Button type="primary" size="large" loading={starting} onClick={() => void startAll()} disabled={board.shots.length === 0}>开始生成</Button>
            <Button type="text" onClick={onBack}>返回修改</Button>
            <span className="text-gray-500 text-[13px]">每个镜头单独生成，失败的可以单独重试。</span>
          </div>
        </Card>
      ) : (
        <>
          <Card size="small">
            <div className="flex justify-between text-sm mb-1">
              <span>{done + failedCount === board.shots.length ? `完成 · ${done}/${board.shots.length} 成功${failedCount ? `，${failedCount} 个失败` : ''}` : `正在生成 · ${done}/${board.shots.length} 完成`}</span>
              <span className="tabular-nums text-gray-500">{pct}%</span>
            </div>
            <Progress percent={pct} showInfo={false} />
          </Card>
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {board.shots.map((s) => {
              const error = s.video_file_id ? null : taskErrorText(s.video_task)
              const active = s.video_task && isActiveStatus(s.video_task.status)
              return (
                <Card
                  key={s.id}
                  size="small"
                  bodyStyle={{ padding: 12 }}
                  cover={
                    <ArtBox
                      src={s.video_url ?? s.keyframe_url}
                      video={!!s.video_url}
                      task={s.video_task}
                      placeholder={s.video_task ? '排队中' : '未开始'}
                      badge={<IndexBadge index={s.index} />}
                      corner={<DurationBadge seconds={s.duration} />}
                      onClick={() => setEditingId(s.id)}
                    />
                  }
                >
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span className="truncate">{s.title}</span>
                    <span className="ml-auto">{s.video_file_id ? <Tag color="success">已完成</Tag> : <TaskTag task={s.video_task} />}</span>
                  </div>
                  {error ? <div className="text-red-600 text-xs mt-1">{error}</div> : <div className="text-gray-500 text-xs mt-1 line-clamp-2 min-h-[32px]">{s.description || s.script_excerpt}</div>}
                  <div className="flex gap-2 mt-2 flex-wrap">
                    {!active && (
                      <Button size="small" type={error ? 'primary' : 'default'} loading={retrying[s.id]} onClick={() => void retry(s)}>
                        {s.video_file_id ? '重新生成' : isRealPersonRejection(s.video_task?.error) ? '改用文字描述重试' : '重试'}
                      </Button>
                    )}
                    <Button size="small" type="text" onClick={() => setEditingId(s.id)}>调整</Button>
                    {error && <Button size="small" type="text" onClick={onEditShot}>修改描述</Button>}
                  </div>
                </Card>
              )
            })}
          </div>
        </>
      )}
      <VideoDrawer shot={editing} board={board} ratio={ratio} onClose={() => setEditingId(null)} onTaskStarted={onTaskStarted} onChanged={onChanged} />
    </div>
  )
}

export default VideoStep
