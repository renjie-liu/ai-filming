import type React from 'react'
import { useRef, useState } from 'react'
import { Button, message } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { localizeErrorMessage } from '../../utils/errorMessage'

/**
 * 「上传图片」按钮：选一张本地图片 → 交给 onPick（上传 + 挂载），期间显示 loading。
 *
 * 为什么存在：角色形象、场景参考图、镜头关键帧三处都要「用自己的图替代 AI 生成」，
 * 共用一个按钮避免三份 input[type=file] 样板。
 */
const ImagePickButton: React.FC<{
  onPick: (file: File) => Promise<void>
  children?: React.ReactNode
  size?: 'small' | 'middle'
  disabled?: boolean
  /** 可选文件类型，默认图片；上传视频时传 video/mp4 等 */
  accept?: string
}> = ({ onPick, children = '上传图片', size = 'small', disabled, accept = 'image/*' }) => {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [busy, setBusy] = useState(false)
  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    try {
      await onPick(file)
    } catch (err) {
      message.error(localizeErrorMessage(err instanceof Error ? err.message : String(err), '上传失败，请换一张图片试试'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={(e) => void onChange(e)} />
      <Button size={size} icon={<UploadOutlined />} loading={busy} disabled={disabled} onClick={() => inputRef.current?.click()}>
        {children}
      </Button>
    </>
  )
}

export default ImagePickButton
