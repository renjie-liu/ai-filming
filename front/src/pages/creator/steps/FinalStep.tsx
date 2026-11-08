import type React from 'react';
import { useEffect, useRef, useState } from 'react'
import { Button, Empty, Modal, Progress, message } from 'antd'
import { DownloadOutlined, ExportOutlined, FileTextOutlined, PlayCircleOutlined } from '@ant-design/icons'
import type { CreatorBoardRead } from '../../../services/generated'
import { localizeErrorMessage } from '../../../utils/errorMessage'
import { buildSrt, buildVtt, downloadBlob, exportEpisode, safeFilename, type ExportClip, type ExportProgress } from '../exportEpisode'

/**
 * 第 5 步 · 成片：合成预览（整集拼成一个 mp4 在页内播放，带对白字幕）、按镜头连播、下载片段、导出 mp4 与 .srt。
 *
 * 合成在浏览器里用 ffmpeg.wasm 完成，预览和导出共用同一个结果：先预览，满意再点下载，不重复拼接。
 */

/** 合成好的整集：对象 URL 随镜头列表变化而失效（重做了某一镜就要重新合成）。 */
type Merged = { key: string; blob: Blob; url: string; vttUrl: string | null }

const STAGE_LABEL: Record<ExportProgress['stage'], string> = {
  load: '准备合成内核',
  fetch: '下载片段',
  concat: '拼接片段',
  encode: '重新编码',
  done: '完成',
}

const FinalStep: React.FC<{ board: CreatorBoardRead; onBackToVideo: () => void; onNewEpisode: () => void }> = ({ board, onBackToVideo, onNewEpisode }) => {
  const clips = board.shots.filter((s): s is typeof s & { video_url: string } => !!s.video_url)
  const [pos, setPos] = useState(0)
  const [exporting, setExporting] = useState<ExportProgress | null>(null)
  const [merged, setMerged] = useState<Merged | null>(null)
  const [showMerged, setShowMerged] = useState(true)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const clipsKey = clips.map((s) => `${s.id}:${s.video_url}`).join('|')
  const mergedReady = merged !== null && merged.key === clipsKey
  const current = clips[pos] ?? clips[0]
  const total = clips.reduce((a, s) => a + s.duration, 0)
  const before = clips.slice(0, pos).reduce((a, s) => a + s.duration, 0)
  const mm = (n: number) => `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`
  const baseName = `${safeFilename(board.project.name)}-第${board.chapter.index}集`
  const hasDialogue = clips.some((s) => s.dialogue.some((d) => d.text.trim()))

  useEffect(() => {
    if (pos >= clips.length) setPos(0)
  }, [clips.length, pos])

  // 镜头被重做 / 新增后，旧的合成结果作废并释放内存
  useEffect(() => {
    if (merged && merged.key !== clipsKey) {
      URL.revokeObjectURL(merged.url)
      if (merged.vttUrl) URL.revokeObjectURL(merged.vttUrl)
      setMerged(null)
    }
  }, [clipsKey, merged])

  const toExportClips = (): ExportClip[] => clips.map((s) => ({ id: s.id, index: s.index, title: s.title, duration: s.duration, dialogue: s.dialogue, video_url: s.video_url }))

  /** 合成整集（预览与下载共用）：返回 Blob；失败时提示并返回 null。 */
  const buildMerged = async (): Promise<Blob | null> => {
    if (mergedReady && merged) return merged.blob
    const exportClips = toExportClips()
    setExporting({ stage: 'load', percent: 0 })
    try {
      const blob = await exportEpisode(exportClips, (p) => setExporting(p))
      const vtt = buildVtt(exportClips)
      const next: Merged = {
        key: clipsKey,
        blob,
        url: URL.createObjectURL(blob),
        vttUrl: vtt ? URL.createObjectURL(new Blob([vtt], { type: 'text/vtt;charset=utf-8' })) : null,
      }
      setMerged(next)
      setShowMerged(true)
      return blob
    } catch (e) {
      message.error(localizeErrorMessage(e instanceof Error ? e.message : String(e), '合成失败，请稍后重试'))
      return null
    } finally {
      setExporting(null)
    }
  }

  const downloadAll = () => {
    clips.forEach((s, i) => {
      window.setTimeout(() => {
        const a = document.createElement('a')
        a.href = s.video_url
        a.download = `${String(s.index).padStart(2, '0')}-${s.title}.mp4`
        a.target = '_blank'
        a.rel = 'noopener'
        document.body.appendChild(a)
        a.click()
        a.remove()
      }, i * 400)
    })
  }

  /** 合成导出：复用已合成的整集，没有就先合成，再下载。 */
  const exportAll = async () => {
    const blob = await buildMerged()
    if (!blob) return
    downloadBlob(blob, `${baseName}.mp4`)
    message.success(`已导出 ${baseName}.mp4（${(blob.size / 1024 / 1024).toFixed(1)} MB）`)
  }

  const exportSrt = () => {
    const srt = buildSrt(clips.map((s) => ({ id: s.id, index: s.index, title: s.title, duration: s.duration, dialogue: s.dialogue, video_url: s.video_url })))
    if (!srt.trim()) {
      message.info('这一集没有对白')
      return
    }
    downloadBlob(new Blob([srt], { type: 'text/plain;charset=utf-8' }), `${baseName}.srt`)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">成片预览</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">
            {mergedReady ? '这是整集拼在一起的效果（带对白字幕）。满意就下载 mp4；不满意的镜头回去重做后再合成一次。' : '先按镜头连播，或点「合成预览」把整集拼成一个视频在这里看；不满意的镜头可以直接回去重做，其余镜头不受影响。'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={<DownloadOutlined />} onClick={downloadAll} disabled={clips.length === 0}>下载全部片段</Button>
          <Button icon={<FileTextOutlined />} onClick={exportSrt} disabled={clips.length === 0 || !hasDialogue}>字幕 .srt</Button>
          {mergedReady ? (
            <Button icon={<ExportOutlined />} type="primary" onClick={() => void exportAll()} data-testid="export-episode">下载整集 mp4</Button>
          ) : (
            <>
              <Button icon={<PlayCircleOutlined />} type="primary" onClick={() => void buildMerged()} disabled={clips.length === 0} loading={exporting !== null} data-testid="merge-preview">
                合成预览
              </Button>
              <Button icon={<ExportOutlined />} onClick={() => void exportAll()} disabled={clips.length === 0} loading={exporting !== null} data-testid="export-episode">
                合成导出
              </Button>
            </>
          )}
          <Button onClick={onNewEpisode}>继续创作下一集</Button>
        </div>
      </div>
      <Modal open={exporting !== null} footer={null} closable={false} maskClosable={false} title="正在合成整集" width={420}>
        {exporting && (
          <div className="flex flex-col gap-2 py-2">
            <div className="flex justify-between text-sm">
              <span>{STAGE_LABEL[exporting.stage]}</span>
              <span className="text-gray-500">{exporting.note ?? ''}</span>
            </div>
            <Progress percent={exporting.percent} showInfo />
            <span className="text-xs text-gray-400">{clips.length} 段 · 共 {total} 秒 · 在你的浏览器里完成，不上传任何内容；首次使用需下载约 31 MB 的合成内核。</span>
          </div>
        )}
      </Modal>
      {clips.length === 0 ? (
        <Empty description="还没有生成好的视频">
          <Button type="primary" onClick={onBackToVideo}>去生成视频</Button>
        </Empty>
      ) : (
        <div className="grid gap-5 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)] items-start">
          <div className="bg-black rounded-xl overflow-hidden w-full max-w-[320px]">
            {mergedReady && merged && showMerged ? (
              <>
                <video key="merged" src={merged.url} controls autoPlay playsInline crossOrigin="anonymous" className="w-full block aspect-[9/16] bg-black" data-testid="merged-player">
                  {merged.vttUrl ? <track kind="subtitles" srcLang="zh" label="对白" src={merged.vttUrl} default /> : null}
                </video>
                <div className="px-3 py-2 text-white text-xs flex justify-between items-center">
                  <span>整集 · {clips.length} 个镜头 · {mm(total)}</span>
                  <Button type="link" size="small" className="px-0 text-white/80" onClick={() => setShowMerged(false)}>逐镜播放</Button>
                </div>
              </>
            ) : (
              <>
                <video
                  ref={videoRef}
                  key={current?.id}
                  src={current?.video_url ?? undefined}
                  controls
                  autoPlay
                  playsInline
                  className="w-full block aspect-[9/16] bg-black"
                  onEnded={() => {
                    if (pos + 1 < clips.length) setPos(pos + 1)
                  }}
                />
                {clips[pos + 1] ? <video src={clips[pos + 1].video_url} preload="auto" muted className="hidden" aria-hidden /> : null}
                <div className="px-3 py-2 text-white text-xs flex justify-between items-center">
                  <span>镜头 {current?.index} · {current?.title}</span>
                  <span className="tabular-nums">{mm(before)} / {mm(total)}</span>
                </div>
                <div className="px-3 pb-3 flex gap-0.5 h-1.5">
                  {clips.map((s, i) => (
                    <i key={s.id} className={`block rounded-full ${i === pos ? 'bg-white' : 'bg-white/30'}`} style={{ flex: s.duration }} />
                  ))}
                </div>
                {mergedReady ? (
                  <div className="px-3 pb-3">
                    <Button size="small" block onClick={() => setShowMerged(true)}>回到整集预览</Button>
                  </div>
                ) : null}
              </>
            )}
          </div>
          <div className="flex flex-col gap-2 min-w-0">
            {clips.map((s, i) => (
              <div
                key={s.id}
                onClick={() => setPos(i)}
                className={`grid grid-cols-[48px_1fr_auto] gap-3 items-center p-2 rounded-lg border cursor-pointer ${i === pos ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white hover:border-blue-300'}`}
              >
                <div className="w-12 h-12 rounded overflow-hidden bg-gray-100">
                  {s.keyframe_url ? <img src={s.keyframe_url} alt="" className="w-full h-full object-cover" /> : <video src={s.video_url} muted className="w-full h-full object-cover" />}
                </div>
                <div className="min-w-0">
                  <div className="font-medium text-sm truncate">{String(s.index).padStart(2, '0')} {s.title}</div>
                  <div className="text-gray-500 text-xs truncate">{s.dialogue[0] ? `${s.dialogue[0].speaker ? s.dialogue[0].speaker + '：' : ''}${s.dialogue[0].text}` : '无对白'}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 text-xs tabular-nums">{s.duration}s</span>
                  <a href={s.video_url} download target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="text-gray-500">
                    <DownloadOutlined />
                  </a>
                </div>
              </div>
            ))}
            <div className="text-gray-400 text-xs mt-1">想重做某个镜头：<Button type="link" size="small" className="px-1" onClick={onBackToVideo}>回到「视频」</Button>点该镜头的「重新生成」。预览里的字幕只在页面上显示，导出的 mp4 不含字幕；需要字幕时把 .srt 一起导入剪辑软件。</div>
          </div>
        </div>
      )}
    </div>
  )
}

export default FinalStep
