import type { FFmpeg as FFmpegInstance } from '@ffmpeg/ffmpeg'
import type { CreatorShotRead } from '../../services/generated'

/**
 * 成片合成导出：在浏览器里用 ffmpeg.wasm 把各镜头的 mp4 按顺序拼成一个文件，另附对白字幕 .srt。
 *
 * 为什么在浏览器做：Vercel 函数里没有 ffmpeg，也放不下几十 MB 的视频往返；Seedance 出的片段编码参数一致，
 * `concat` 复用流（-c copy）不重新编码，几秒钟就能拼完。参数不一致时退回重新编码（慢，但能出片）。
 * ffmpeg 内核（约 31 MB）随前端一起部署在 /ffmpeg/ 下，首次加载后由浏览器缓存。
 */

export type ExportStage = 'load' | 'fetch' | 'concat' | 'encode' | 'done'
export type ExportProgress = { stage: ExportStage; percent: number; note?: string }
export type ExportClip = Pick<CreatorShotRead, 'id' | 'index' | 'title' | 'duration' | 'dialogue'> & { video_url: string }

let instance: Promise<FFmpegInstance> | null = null

/** 加载并缓存 ffmpeg 实例（内核文件从本站 /ffmpeg/ 取，避免跨域与 CDN 不可达）。 */
async function loadFFmpeg(onProgress?: (p: ExportProgress) => void): Promise<FFmpegInstance> {
  if (instance) return instance
  instance = (async () => {
    onProgress?.({ stage: 'load', percent: 0, note: '首次使用需要下载约 31 MB 的合成内核' })
    const [{ FFmpeg }, { toBlobURL }] = await Promise.all([import('@ffmpeg/ffmpeg'), import('@ffmpeg/util')])
    const base = `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/$/, '')}/ffmpeg`
    const ffmpeg = new FFmpeg()
    const coreURL = await toBlobURL(`${base}/ffmpeg-core.js`, 'text/javascript')
    onProgress?.({ stage: 'load', percent: 30 })
    const wasmURL = await toBlobURL(`${base}/ffmpeg-core.wasm`, 'application/wasm')
    onProgress?.({ stage: 'load', percent: 80 })
    await ffmpeg.load({ coreURL, wasmURL })
    onProgress?.({ stage: 'load', percent: 100 })
    return ffmpeg
  })()
  instance.catch(() => {
    instance = null
  })
  return instance
}

/** 把成片（mp4 片段）按镜头顺序拼成一个 mp4；返回 Blob。 */
export async function exportEpisode(clips: ExportClip[], onProgress?: (p: ExportProgress) => void): Promise<Blob> {
  if (clips.length === 0) throw new Error('还没有生成好的视频片段')
  const ffmpeg = await loadFFmpeg(onProgress)
  const { fetchFile } = await import('@ffmpeg/util')
  const names: string[] = []
  for (let i = 0; i < clips.length; i += 1) {
    onProgress?.({ stage: 'fetch', percent: Math.round((i / clips.length) * 100), note: `下载片段 ${i + 1}/${clips.length}` })
    const name = `clip${String(i).padStart(3, '0')}.mp4`
    await ffmpeg.writeFile(name, await fetchFile(clips[i].video_url))
    names.push(name)
  }
  await ffmpeg.writeFile('list.txt', names.map((n) => `file '${n}'`).join('\n'))

  const handler = ({ progress }: { progress: number }) => onProgress?.({ stage: 'concat', percent: Math.max(0, Math.min(100, Math.round(progress * 100))) })
  ffmpeg.on('progress', handler)
  try {
    onProgress?.({ stage: 'concat', percent: 0, note: '拼接片段' })
    let code = await ffmpeg.exec(['-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-movflags', '+faststart', '-y', 'out.mp4'])
    if (code !== 0) {
      // 片段编码参数不一致（例如混入了上传的视频）：重新编码一遍，慢但能出片
      onProgress?.({ stage: 'encode', percent: 0, note: '片段参数不一致，正在重新编码（较慢）' })
      code = await ffmpeg.exec([
        '-f', 'concat', '-safe', '0', '-i', 'list.txt',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-ar', '44100', '-movflags', '+faststart', '-y', 'out.mp4',
      ])
      if (code !== 0) throw new Error('合成失败：片段无法拼接，请先确认每个镜头的视频都能单独播放')
    }
    const data = await ffmpeg.readFile('out.mp4')
    const bytes = typeof data === 'string' ? new TextEncoder().encode(data) : new Uint8Array(data as Uint8Array)
    if (bytes.byteLength === 0) throw new Error('合成失败：输出为空')
    onProgress?.({ stage: 'done', percent: 100 })
    return new Blob([bytes], { type: 'video/mp4' })
  } finally {
    ffmpeg.off('progress', handler)
    for (const n of [...names, 'list.txt', 'out.mp4']) {
      try {
        await ffmpeg.deleteFile(n)
      } catch {
        /* 文件可能不存在 */
      }
    }
  }
}

function srtTime(seconds: number): string {
  const ms = Math.round(seconds * 1000)
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const r = ms % 1000
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(r).padStart(3, '0')}`
}

/**
 * 按镜头顺序生成对白字幕：每个镜头的时长在它的几句对白之间平均分配。
 * 没有精确的语音时间轴，这是给剪辑软件用的起点；镜头没有对白则跳过。
 */
export function buildSrt(clips: ExportClip[]): string {
  const blocks: string[] = []
  let offset = 0
  let n = 1
  for (const clip of clips) {
    const lines = clip.dialogue.filter((d) => d.text.trim())
    const duration = Math.max(1, clip.duration || 4)
    if (lines.length > 0) {
      const slice = duration / lines.length
      lines.forEach((line, i) => {
        const start = offset + slice * i
        const end = Math.min(offset + duration, start + slice)
        blocks.push(`${n}\n${srtTime(start)} --> ${srtTime(end)}\n${line.speaker ? `${line.speaker}：` : ''}${line.text.trim()}\n`)
        n += 1
      })
    }
    offset += duration
  }
  return blocks.join('\n')
}

/** 触发浏览器下载。 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** 文件名里去掉路径分隔符等不安全字符。 */
export function safeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '') || 'episode'
}
