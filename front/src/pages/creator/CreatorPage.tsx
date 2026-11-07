import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Select, Spin, message } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { StudioChaptersService, StudioProjectsService } from '../../services/generated'
import type { ChapterRead, ProjectRead } from '../../services/generated'
import { useIsMobile } from '../../hooks/useIsMobile'
import { useTaskPageContext } from '../aiStudio/components/taskPageContext'
import DirectorRail, { STEP_TIPS, type RailPrimary } from './DirectorRail'
import StepBar from './StepBar'
import { CREATOR_STEPS, WORKS_PATH, isCreatorStepKey, type CreatorStepKey } from './routes'
import { useCreatorBoard } from './useCreatorBoard'
import CastStep from './steps/CastStep'
import FinalStep from './steps/FinalStep'
import ScriptStep from './steps/ScriptStep'
import StoryboardStep from './steps/StoryboardStep'
import VideoStep, { videoStarted } from './steps/VideoStep'
import type { CreatorBoardRead } from '../../services/generated'

/**
 * 创作页：一个作品的一集在同一页里走完「剧本 → 角色场景 → 分镜 → 视频 → 成片」。
 *
 * 为什么存在：原来的流程分散在 7 个页面；这里把步骤放进顶部进度条，右侧「导演助手」
 * 始终告诉用户下一步做什么。步骤通过 URL hash 记录（#script / #cast / ...），章节通过 ?chapter=。
 */

function defaultStep(board: CreatorBoardRead | null): CreatorStepKey {
  if (!board || board.summary.shot_count === 0) return 'script'
  if (board.summary.video_done_count > 0 && board.summary.video_done_count === board.summary.shot_count) return 'final'
  if (videoStarted(board)) return 'video'
  if (board.summary.keyframe_count > 0) return 'storyboard'
  return 'cast'
}

const CreatorPage: React.FC = () => {
  const { projectId = '' } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const isMobile = useIsMobile()

  const [project, setProject] = useState<ProjectRead | null>(null)
  const [chapters, setChapters] = useState<ChapterRead[]>([])
  const [loadingMeta, setLoadingMeta] = useState(true)
  const [metaError, setMetaError] = useState<string | null>(null)

  const chapterParam = searchParams.get('chapter')
  const chapter = useMemo(() => {
    if (chapters.length === 0) return null
    return chapters.find((c) => c.id === chapterParam) ?? [...chapters].sort((a, b) => b.index - a.index)[0]
  }, [chapters, chapterParam])

  const { board, loading: boardLoading, refresh, pollSoon } = useCreatorBoard(chapter?.id ?? null)

  const loadMeta = useCallback(async () => {
    if (!projectId) return
    try {
      const [p, c] = await Promise.all([
        StudioProjectsService.getProjectApiV1StudioProjectsProjectIdGet({ projectId }),
        StudioChaptersService.listChaptersApiV1StudioChaptersGet({ projectId, page: 1, pageSize: 100, order: 'index' }),
      ])
      setProject(p.data ?? null)
      setChapters(c.data?.items ?? [])
      setMetaError(null)
    } catch (e) {
      setMetaError(e instanceof Error ? e.message : '加载作品失败')
    } finally {
      setLoadingMeta(false)
    }
  }, [projectId])

  useEffect(() => {
    void loadMeta()
  }, [loadMeta])

  // 当前步骤：优先 URL hash；没有时按进度推断（只在首次拿到聚合时设置一次）
  const hashStep = location.hash.replace('#', '')
  const [step, setStepState] = useState<CreatorStepKey>(isCreatorStepKey(hashStep) ? hashStep : 'script')
  const inferredRef = useRef(false)
  useEffect(() => {
    if (isCreatorStepKey(hashStep)) {
      setStepState(hashStep)
      inferredRef.current = true
    }
  }, [hashStep])
  useEffect(() => {
    if (inferredRef.current || !board) return
    inferredRef.current = true
    setStepState(defaultStep(board))
  }, [board])

  const setStep = useCallback(
    (next: CreatorStepKey) => {
      if (!board && next !== 'script') {
        message.info('先在「剧本」里一键拆分镜')
        return
      }
      setStepState(next)
      navigate({ pathname: location.pathname, search: location.search, hash: `#${next}` }, { replace: true })
      window.scrollTo({ top: 0 })
    },
    [board, location.pathname, location.search, navigate],
  )

  // 任务中心高亮当前章节 / 镜头的任务
  useTaskPageContext(
    useMemo(
      () => [
        chapter ? { relationType: 'chapter_division', relationEntityId: chapter.id } : null,
        chapter ? { relationType: 'script_extraction', relationEntityId: chapter.id } : null,
        ...(board?.shots.map((s) => ({ relationType: 'video', relationEntityId: s.id })) ?? []),
      ],
      [board?.shots, chapter],
    ),
  )

  const scriptTrigger = useRef<(() => void) | null>(null)
  const storyboardBatch = useRef<(() => void) | null>(null)
  const videoStart = useRef<(() => void) | null>(null)
  const [scriptRunning, setScriptRunning] = useState(false)

  const switchChapter = (chapterId: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('chapter', chapterId)
      return next
    })
    inferredRef.current = false
  }

  const newEpisode = async () => {
    const index = chapters.reduce((m, c) => Math.max(m, c.index), 0) + 1
    try {
      const res = await StudioChaptersService.createChapterApiV1StudioChaptersPost({
        requestBody: { id: crypto.randomUUID(), project_id: projectId, index, title: `第 ${index} 集` },
      })
      await loadMeta()
      if (res.data) {
        switchChapter(res.data.id)
        setStep('script')
      }
    } catch {
      message.error('创建新一集失败')
    }
  }

  const primary: RailPrimary | null = (() => {
    const hasShots = (board?.summary.shot_count ?? 0) > 0
    switch (step) {
      case 'script':
        return hasShots
          ? { label: '去分镜板', onClick: () => setStep('storyboard') }
          : { label: '一键拆分镜', onClick: () => scriptTrigger.current?.(), loading: scriptRunning }
      case 'cast':
        return { label: '下一步：分镜板', onClick: () => setStep('storyboard') }
      case 'storyboard':
        return { label: '下一步：生成视频', onClick: () => setStep('video'), disabled: !hasShots }
      case 'video':
        return board && videoStarted(board)
          ? { label: '查看成片', onClick: () => setStep('final'), disabled: (board?.summary.video_done_count ?? 0) === 0 }
          : { label: '开始生成', onClick: () => videoStart.current?.() }
      case 'final':
        return { label: '继续创作下一集', onClick: () => void newEpisode() }
      default:
        return null
    }
  })()

  if (loadingMeta) {
    return (
      <div className="h-full grid place-items-center">
        <Spin />
      </div>
    )
  }
  if (metaError || !project) {
    return (
      <div className="p-4">
        <Alert type="error" showIcon message={metaError ?? '作品不存在'} action={<Link to={WORKS_PATH}>返回作品列表</Link>} />
      </div>
    )
  }

  const stepIndex = CREATOR_STEPS.findIndex((s) => s.key === step)
  const content = (() => {
    if (step === 'script' || !board) {
      return (
        <ScriptStep
          projectId={projectId}
          project={project}
          chapters={chapters}
          chapter={chapter}
          board={board}
          triggerRef={scriptTrigger}
          onRunningChange={setScriptRunning}
          onChapterCreated={async (c) => {
            await loadMeta()
            switchChapter(c.id)
          }}
          onPrepared={async () => {
            await refresh()
            setStep('cast')
          }}
          onGoStoryboard={() => setStep('storyboard')}
        />
      )
    }
    if (boardLoading) {
      return (
        <div className="py-10 grid place-items-center">
          <Spin />
        </div>
      )
    }
    switch (step) {
      case 'cast':
        return <CastStep board={board} onNext={() => setStep('storyboard')} onTaskStarted={pollSoon} onChanged={refresh} />
      case 'storyboard':
        return <StoryboardStep board={board} onNext={() => setStep('video')} onTaskStarted={pollSoon} onChanged={refresh} batchRef={storyboardBatch} />
      case 'video':
        return <VideoStep board={board} onBack={() => setStep('storyboard')} onFinal={() => setStep('final')} onTaskStarted={pollSoon} onEditShot={() => setStep('storyboard')} startRef={videoStart} />
      case 'final':
        return <FinalStep board={board} onBackToVideo={() => setStep('video')} onNewEpisode={() => void newEpisode()} />
      default:
        return null
    }
  })()

  return (
    <div className="h-full min-h-0 flex flex-col">
      {/* 顶栏：作品名 + 集数 + 步骤条 */}
      <div className={`flex items-center gap-3 flex-wrap border-b border-gray-200 bg-white ${isMobile ? 'px-3 py-2' : 'px-5 py-2.5'}`}>
        <Link to={WORKS_PATH} className="text-gray-500 hover:text-blue-600 text-sm flex items-center gap-1 shrink-0">
          <ArrowLeftOutlined /> 作品
        </Link>
        <span className="font-medium truncate max-w-[40vw]">{project.name}</span>
        {chapters.length > 0 && (
          <Select
            size="small"
            value={chapter?.id}
            onChange={switchChapter}
            options={[...chapters].sort((a, b) => a.index - b.index).map((c) => ({ value: c.id, label: c.title }))}
            popupMatchSelectWidth={false}
          />
        )}
        <div className={`${isMobile ? 'w-full order-last' : 'flex-1 min-w-[520px]'} px-2`}>
          <StepBar current={step} onChange={setStep} compact={isMobile} />
        </div>
      </div>

      <div className={`flex-1 min-h-0 overflow-auto ${isMobile ? 'pb-24' : ''}`}>
        <div className={`mx-auto max-w-[1280px] grid gap-5 items-start ${isMobile ? 'p-3 grid-cols-1' : 'p-5 grid-cols-[minmax(0,1fr)_300px]'}`}>
          <div className="min-w-0">{content}</div>
          {!isMobile && (
            <div className="sticky top-5">
              <DirectorRail step={step} board={board} primary={primary} />
            </div>
          )}
        </div>
      </div>

      {isMobile && (
        <div className="fixed left-0 right-0 bottom-0 z-20 bg-white border-t border-gray-200 px-4 py-3 flex items-center justify-between gap-3" style={{ paddingBottom: 'calc(12px + env(safe-area-inset-bottom, 0px))' }}>
          <div className="min-w-0 text-[13px]">
            <div className="font-medium">第 {stepIndex + 1} 步 · {CREATOR_STEPS[stepIndex]?.label}</div>
            <div className="text-gray-500 text-xs truncate">{STEP_TIPS[step]}</div>
          </div>
          {primary && (
            <Button type="primary" onClick={primary.onClick} disabled={primary.disabled} loading={primary.loading}>
              {primary.label}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

export default CreatorPage
