import type React from 'react';
import { useState } from 'react'
import { Button, Card, Progress, Table, Tag, message } from 'antd'
import type { CreatorBoardRead, CreatorShotRead } from '../../../services/generated'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import { generateVideo, resolveRatio } from '../actions'
import { ArtBox, DurationBadge, IndexBadge, TaskTag, taskErrorText } from '../ui'
import { isActiveStatus } from '../taskPolling'

/** 第 4 步 · 视频：先出确认单，开始后变成进度板；失败可单独重试。 */

type Props = {
  board: CreatorBoardRead
  onBack: () => void
  onFinal: () => void
  onTaskStarted: () => void
  onEditShot: () => void
  startRef?: React.MutableRefObject<(() => void) | null>
}

export function videoStarted(board: CreatorBoardRead): boolean {
  return board.shots.some((s) => s.video_task || s.video_file_id)
}

const VideoStep: React.FC<Props> = ({ board, onBack, onFinal, onTaskStarted, onEditShot, startRef }) => {
  const [starting, setStarting] = useState(false)
  const [retrying, setRetrying] = useState<Record<string, boolean>>({})
  const ratio = resolveRatio(board)
  const started = videoStarted(board) || starting

  const runOne = async (shot: CreatorShotRead) => {
    await generateVideo({ shot, ratio })
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
        message.error(`${s.title}：${localizeErrorMessage(e instanceof Error ? e.message : String(e), '视频任务创建失败')}`)
      }
    }
    onTaskStarted()
    if (failed === 0) message.success(`已开始生成 ${todo.length} 段视频`)
    setStarting(false)
  }
  if (startRef) startRef.current = () => void startAll()

  const retry = async (shot: CreatorShotRead) => {
    setRetrying((p) => ({ ...p, [shot.id]: true }))
    try {
      await runOne(shot)
      onTaskStarted()
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '视频任务创建失败'))
    } finally {
      setRetrying((p) => ({ ...p, [shot.id]: false }))
    }
  }

  const done = board.summary.video_done_count
  const failedCount = board.shots.filter((s) => s.video_task?.status === 'failed' && !s.video_file_id).length
  const pct = board.shots.length
    ? Math.round(board.shots.reduce((a, s) => a + (s.video_file_id ? 100 : s.video_task && isActiveStatus(s.video_task.status) ? s.video_task.progress : 0), 0) / board.shots.length)
    : 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">{started ? '生成视频' : '确认后开始生成'}</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">
            {started ? '每个镜头单独生成；失败的镜头会给出原因，可以单独重试，不影响其他镜头。' : '生成前先确认一遍，额度只在你点「开始生成」之后才消耗。'}
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
        <Card className="max-w-[720px]">
          <h2 className="text-base font-semibold m-0 mb-3">生成 {board.shots.length} 段视频</h2>
          <Table
            size="small"
            pagination={false}
            rowKey="id"
            dataSource={board.shots}
            columns={[
              { title: '镜头', dataIndex: 'title', render: (v: string, r: CreatorShotRead) => <span className="tabular-nums">{String(r.index).padStart(2, '0')} {v}</span> },
              { title: '时长', dataIndex: 'duration', width: 80, render: (v: number) => <span className="tabular-nums">{v} 秒</span> },
              { title: '参考', width: 140, render: (_: unknown, r: CreatorShotRead) => (r.keyframe_file_id ? '首帧图 + 描述' : <span className="text-gray-400">仅文字描述</span>) },
            ]}
          />
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-gray-500 mt-3">
            <span>共 <b className="text-gray-900 font-medium tabular-nums">{board.summary.total_seconds} 秒</b></span>
            <span>比例 <b className="text-gray-900 font-medium">{ratio}</b></span>
            <span>预计 <b className="text-gray-900 font-medium">{Math.max(2, Math.ceil(board.shots.length * 0.8))}–{Math.max(4, board.shots.length * 2)} 分钟</b></span>
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
              const error = taskErrorText(s.video_task)
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
                    />
                  }
                >
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span className="truncate">{s.title}</span>
                    <span className="ml-auto">{s.video_file_id ? <Tag color="success">已完成</Tag> : <TaskTag task={s.video_task} />}</span>
                  </div>
                  {error && !s.video_file_id ? <div className="text-red-600 text-xs mt-1">{error}</div> : <div className="text-gray-500 text-xs mt-1 line-clamp-2 min-h-[32px]">{s.description || s.script_excerpt}</div>}
                  <div className="flex gap-2 mt-2">
                    {!active && (
                      <Button size="small" type={error && !s.video_file_id ? 'primary' : 'default'} loading={retrying[s.id]} onClick={() => void retry(s)}>
                        {s.video_file_id ? '重新生成' : '重试'}
                      </Button>
                    )}
                    {error && !s.video_file_id && <Button size="small" onClick={onEditShot}>修改描述</Button>}
                  </div>
                </Card>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

export default VideoStep
