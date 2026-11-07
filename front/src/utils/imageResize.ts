/**
 * 浏览器端把图片缩到指定最长边并转成 JPEG。
 *
 * 为什么存在：Vercel 函数请求体上限约 4.5 MB，手机直出的照片经常超过；
 * 形象图 / 关键帧只需要 2K 以内，所以上传前先在本地缩一遍，顺便统一成 JPEG。
 * 非图片或解码失败时原样返回，由后端决定是否接受。
 */
export async function downscaleImage(file: File, maxEdge = 2048, quality = 0.9): Promise<File> {
  if (!file.type.startsWith('image/') || file.type === 'image/gif') return file
  const bitmap = await loadBitmap(file).catch(() => null)
  if (!bitmap) return file
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const needsResize = scale < 1
  const needsReencode = file.type !== 'image/jpeg' || file.size > 3.5 * 1024 * 1024
  if (!needsResize && !needsReencode) return file
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(bitmap.width * scale))
  canvas.height = Math.max(1, Math.round(bitmap.height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) return file
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
  if (!blob) return file
  const base = file.name.replace(/\.[^.]+$/, '') || 'image'
  return new File([blob], `${base}.jpg`, { type: 'image/jpeg' })
}

async function loadBitmap(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if ('createImageBitmap' in window) return createImageBitmap(file)
  const url = URL.createObjectURL(file)
  try {
    return await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('decode failed'))
      img.src = url
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}
