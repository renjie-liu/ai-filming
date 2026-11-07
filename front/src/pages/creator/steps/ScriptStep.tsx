import type React from 'react';
import { useEffect, useState } from 'react'
import { Alert, Button, Card, Input, Popconfirm, Segmented, Tag, message } from 'antd'
import { CheckCircleFilled, LoadingOutlined } from '@ant-design/icons'
import type { ChapterRead, CreatorBoardRead, ProjectRead } from '../../../services/generated'
import { StudioProjectsService } from '../../../services/generated'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import { clearChapterShots, ensureChapter, prepareChapter, type PrepareStage, type PrepareStageState } from '../actions'

/**
 * 第 1 步 · 剧本：粘贴剧本 → 一键拆分镜。
 * 已拆过镜的章节显示摘要，并允许清空后重新拆分。
 */

const STAGE_LABELS: Array<{ key: PrepareStage; label: string }> = [
  { key: 'divide', label: '拆分镜头' },
  { key: 'extract', label: '识别角色、场景与道具' },
  { key: 'confirm', label: '整理镜头信息（自动确认）' },
]

const SAMPLE = `【第1集】大厂的神
开放式办公区，清晨。雷霆总监（40岁，西装外套套在T恤外，手里攥着闪电形状的马克杯）站在白板前。
雷霆总监：各位，先自我介绍一下。我，雷霆，P9，负责天气业务线，上季度 KPI 完成率 108%。
智慧（30岁，产品经理，戴眼镜，电脑贴满便利贴）推了推眼镜。
智慧：智慧，P7，产品经理。我负责把你们的神力拆成需求文档。
雷霆总监把马克杯重重放下，白板上出现一道闪电。
雷霆总监：这个季度，我们的 OKR 是——让人类再次相信天气预报。`

type Props = {
  projectId: string
  project: ProjectRead
  chapters: ChapterRead[]
  chapter: ChapterRead | null
  board: CreatorBoardRead | null
  onChapterCreated: (chapter: ChapterRead) => void
  onPrepared: () => void
  onGoStoryboard: () => void
  /** 由父组件触发（导演助手 / 底部操作条上的主按钮） */
  triggerRef?: React.MutableRefObject<(() => void) | null>
  onRunningChange?: (running: boolean) => void
}

const ScriptStep: React.FC<Props> = ({ projectId, project, chapters, chapter, board, onChapterCreated, onPrepared, onGoStoryboard, triggerRef, onRunningChange }) => {
  const [text, setText] = useState(chapter?.raw_text ?? '')
  const [ratio, setRatio] = useState<string>(board?.project.default_video_ratio ?? project.default_video_ratio ?? '9:16')
  const [running, setRunning] = useState(false)
  const [stages, setStages] = useState<Record<PrepareStage, { state: PrepareStageState; note?: string }>>({
    divide: { state: 'idle' },
    extract: { state: 'idle' },
    confirm: { state: 'idle' },
  })
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setText(chapter?.raw_text ?? '')
  }, [chapter?.id, chapter?.raw_text])
  useEffect(() => {
    if (board?.project.default_video_ratio) setRatio(board.project.default_video_ratio)
  }, [board?.project.default_video_ratio])

  const hasShots = (board?.summary.shot_count ?? 0) > 0

  const run = async (force: boolean) => {
    const script = text.trim()
    if (!script) {
      message.warning('先把剧本或故事粘贴进来')
      return
    }
    setRunning(true)
    onRunningChange?.(true)
    setError(null)
    setLog([])
    setStages({ divide: { state: 'idle' }, extract: { state: 'idle' }, confirm: { state: 'idle' } })
    try {
      const target = await ensureChapter({ projectId, chapters, chapterId: chapter?.id ?? null, scriptText: script })
      if (!chapter) onChapterCreated(target)
      if (force) await clearChapterShots(target.id)
      await prepareChapter({
        projectId,
        chapterId: target.id,
        scriptText: script,
        onStage: (stage, state, note) => setStages((prev) => ({ ...prev, [stage]: { state, note } })),
        onLog: (line) => setLog((prev) => [...prev, line]),
      })
      message.success('分镜已就绪')
      onPrepared()
    } catch (e) {
      setError(localizeErrorMessage(e instanceof Error ? e.message : String(e), '拆分镜失败，请稍后重试'))
    } finally {
      setRunning(false)
      onRunningChange?.(false)
    }
  }

  if (triggerRef) triggerRef.current = () => void run(hasShots)

  const changeRatio = async (value: string) => {
    setRatio(value)
    try {
      await StudioProjectsService.updateProjectApiV1StudioProjectsProjectIdPatch({ projectId, requestBody: { default_video_ratio: value } })
    } catch {
      message.error('保存比例失败')
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold m-0">把故事交给我</h1>
        <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">
          粘贴剧本，或者先写几句想法。拆镜头、找角色、配场景都由 Jellyfish 完成，你只需要在关键处做选择。
        </p>
      </div>
      {hasShots && !running && (
        <Alert
          type="success"
          showIcon
          message={`这一集已经拆出 ${board?.summary.shot_count} 个镜头`}
          description="可以直接去分镜板继续；如果改了剧本想重新拆，会清空现有镜头、关键帧和视频。"
          action={
            <div className="flex gap-2">
              <Button size="small" type="primary" onClick={onGoStoryboard}>去分镜板</Button>
              <Popconfirm title="重新拆分会清空现有镜头、关键帧和视频，确定吗？" okText="重新拆分" cancelText="取消" onConfirm={() => void run(true)}>
                <Button size="small" danger>重新拆分镜</Button>
              </Popconfirm>
            </div>
          }
        />
      )}
      <Card>
        <div className="flex flex-col gap-4">
          <Input.TextArea
            id="creator-script"
            value={text}
            onChange={(e) => setText(e.target.value)}
            autoSize={{ minRows: 10, maxRows: 24 }}
            placeholder={`把剧本或故事贴在这里，例如：\n\n${SAMPLE}`}
            disabled={running}
          />
          <div className="flex flex-wrap gap-x-8 gap-y-3 items-center">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">风格</span>
              <Tag>{project.visual_style}</Tag>
              <Tag>{project.style}</Tag>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">比例</span>
              <Segmented size="small" value={ratio} onChange={(v) => void changeRatio(String(v))} options={[{ label: '竖屏 9:16', value: '9:16' }, { label: '横屏 16:9', value: '16:9' }]} disabled={running} />
            </div>
          </div>
          {!hasShots && (
            <div className="flex flex-wrap items-center gap-3">
              <Button type="primary" size="large" loading={running} onClick={() => void run(false)}>
                一键拆分镜
              </Button>
              <span className="text-gray-500 text-[13px]">约 1–2 分钟 · 只分析文字，不消耗生成额度</span>
              {!text && <Button type="link" size="small" onClick={() => setText(SAMPLE)}>用示例试试</Button>}
            </div>
          )}
          {(running || log.length > 0 || error) && (
            <Card size="small" className="bg-gray-50">
              <div className="flex flex-col gap-2">
                {STAGE_LABELS.map((s) => {
                  const st = stages[s.key]
                  return (
                    <div key={s.key} className="flex items-center gap-2 text-sm">
                      {st.state === 'done' ? (
                        <CheckCircleFilled className="text-green-600" />
                      ) : st.state === 'run' ? (
                        <LoadingOutlined className="text-blue-600" />
                      ) : (
                        <span className={`inline-block w-3.5 h-3.5 rounded-full border ${st.state === 'fail' ? 'border-red-500 bg-red-100' : 'border-gray-300'}`} />
                      )}
                      <span>{s.label}</span>
                      {st.note && <span className="ml-auto text-gray-400">{st.note}</span>}
                    </div>
                  )
                })}
                {log.length > 0 && (
                  <div className="font-mono text-[12px] text-gray-500 bg-white rounded p-2 flex flex-col gap-0.5">
                    {log.map((l, i) => <div key={i}>{l}</div>)}
                  </div>
                )}
                {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => void run(hasShots)}>重试</Button>} />}
              </div>
            </Card>
          )}
        </div>
      </Card>
    </div>
  )
}

export default ScriptStep
