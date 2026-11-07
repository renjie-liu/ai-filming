import type React from 'react';
import { useEffect, useRef, useState } from 'react'
import { Button, Empty, Tooltip } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { CreatorBoardRead } from '../../../services/generated'

/** 第 5 步 · 成片：按镜头顺序连播、下载片段。 */

const FinalStep: React.FC<{ board: CreatorBoardRead; onBackToVideo: () => void; onNewEpisode: () => void }> = ({ board, onBackToVideo, onNewEpisode }) => {
  const clips = board.shots.filter((s) => s.video_url)
  const [pos, setPos] = useState(0)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const current = clips[pos] ?? clips[0]
  const total = clips.reduce((a, s) => a + s.duration, 0)
  const before = clips.slice(0, pos).reduce((a, s) => a + s.duration, 0)
  const mm = (n: number) => `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`

  useEffect(() => {
    if (pos >= clips.length) setPos(0)
  }, [clips.length, pos])

  const downloadAll = () => {
    clips.forEach((s, i) => {
      window.setTimeout(() => {
        const a = document.createElement('a')
        a.href = s.video_url as string
        a.download = `${String(s.index).padStart(2, '0')}-${s.title}.mp4`
        a.target = '_blank'
        a.rel = 'noopener'
        document.body.appendChild(a)
        a.click()
        a.remove()
      }, i * 400)
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap justify-between items-end gap-3">
        <div>
          <h1 className="text-xl font-bold m-0">成片预览</h1>
          <p className="text-gray-500 text-sm m-0 mt-1 max-w-[60ch]">按镜头顺序连播。不满意的镜头可以直接回去重做，其余镜头不受影响。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button icon={<DownloadOutlined />} onClick={downloadAll} disabled={clips.length === 0}>下载全部片段</Button>
          <Tooltip title="第二阶段提供：浏览器内拼接导出 mp4">
            <Button disabled>合成导出</Button>
          </Tooltip>
          <Button type="primary" onClick={onNewEpisode}>继续创作下一集</Button>
        </div>
      </div>
      {clips.length === 0 ? (
        <Empty description="还没有生成好的视频">
          <Button type="primary" onClick={onBackToVideo}>去生成视频</Button>
        </Empty>
      ) : (
        <div className="grid gap-5 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)] items-start">
          <div className="bg-black rounded-xl overflow-hidden w-full max-w-[320px]">
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
            <div className="px-3 py-2 text-white text-xs flex justify-between">
              <span>镜头 {current?.index} · {current?.title}</span>
              <span className="tabular-nums">{mm(before)} / {mm(total)}</span>
            </div>
            <div className="px-3 pb-3 flex gap-0.5 h-1.5">
              {clips.map((s, i) => (
                <i key={s.id} className={`block rounded-full ${i === pos ? 'bg-white' : 'bg-white/30'}`} style={{ flex: s.duration }} />
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-2 min-w-0">
            {clips.map((s, i) => (
              <div
                key={s.id}
                onClick={() => setPos(i)}
                className={`grid grid-cols-[48px_1fr_auto] gap-3 items-center p-2 rounded-lg border cursor-pointer ${i === pos ? 'border-blue-500 bg-blue-50' : 'border-gray-200 bg-white hover:border-blue-300'}`}
              >
                <div className="w-12 h-12 rounded overflow-hidden bg-gray-100">
                  {s.keyframe_url ? <img src={s.keyframe_url} alt="" className="w-full h-full object-cover" /> : <video src={s.video_url ?? undefined} muted className="w-full h-full object-cover" />}
                </div>
                <div className="min-w-0">
                  <div className="font-medium text-sm truncate">{String(s.index).padStart(2, '0')} {s.title}</div>
                  <div className="text-gray-500 text-xs truncate">{s.dialogue[0] ? `${s.dialogue[0].speaker ? s.dialogue[0].speaker + '：' : ''}${s.dialogue[0].text}` : '无对白'}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 text-xs tabular-nums">{s.duration}s</span>
                  <a href={s.video_url ?? '#'} download target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="text-gray-500">
                    <DownloadOutlined />
                  </a>
                </div>
              </div>
            ))}
            <div className="text-gray-400 text-xs mt-1">想重做某个镜头：<Button type="link" size="small" className="px-1" onClick={onBackToVideo}>回到「视频」</Button>点该镜头的「重新生成」。</div>
          </div>
        </div>
      )}
    </div>
  )
}

export default FinalStep
