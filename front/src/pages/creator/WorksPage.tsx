import type React from 'react';
import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Empty, Form, Input, Modal, Popconfirm, Segmented, Spin, Tag, message } from 'antd'
import { CheckOutlined, DeleteOutlined, PlusOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { StudioProjectsService } from '../../services/generated'
import type { ProjectOverviewRead, ProjectStyleOptionsRead, StylePresetRead } from '../../services/generated'
import { useIsMobile } from '../../hooks/useIsMobile'
import SetupStatusBanner from '../aiStudio/models/SetupStatusBanner'
import { useSetupStatus } from '../aiStudio/models/useSetupStatus'
import { getCreatorPath } from './routes'

/** 作品列表：每个作品一张卡（封面、进度），「新建作品」直接进入创作页。 */

type CreateForm = { name: string; style_prompt?: string; ratio: string }

/** 新建作品弹窗里的风格卡片：按分组切换，点一张即选中；选中的风格决定整部作品所有形象 / 关键帧 / 视频的画面质感。 */
const StylePresetPicker: React.FC<{
  options: ProjectStyleOptionsRead
  value: string | undefined
  onChange: (key: string) => void
  isMobile: boolean
}> = ({ options, value, onChange, isMobile }) => {
  const groups = options.preset_groups?.length ? options.preset_groups : Array.from(new Set((options.presets ?? []).map((p) => p.group)))
  const selected = (options.presets ?? []).find((p) => p.key === value)
  const [group, setGroup] = useState<string>(selected?.group ?? groups[0] ?? '')
  useEffect(() => {
    if (selected && selected.group !== group) setGroup(selected.group)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.key])
  const visible = (options.presets ?? []).filter((p) => p.group === group)
  return (
    <div className="flex flex-col gap-2">
      <Segmented size="small" value={group} onChange={(v) => setGroup(String(v))} options={groups.map((g) => ({ value: g, label: g }))} />
      <div className={`grid gap-2 ${isMobile ? 'grid-cols-2' : 'grid-cols-3'}`} data-testid="style-preset-grid">
        {visible.map((p: StylePresetRead) => {
          const active = p.key === value
          return (
            <button
              key={p.key}
              type="button"
              data-testid={`style-preset-${p.key}`}
              onClick={() => onChange(p.key)}
              className={`text-left rounded-lg border px-3 py-2 transition-colors ${active ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500' : 'border-gray-200 hover:border-blue-300 bg-white'}`}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="font-medium text-sm truncate">{p.label}</span>
                {active ? <CheckOutlined className="text-blue-600 text-xs" /> : null}
              </div>
              <div className="text-xs text-gray-500 mt-0.5 leading-snug line-clamp-2">{p.blurb}</div>
              {p.tags?.length ? <div className="text-[11px] text-gray-400 mt-1 truncate">{p.tags.join(' · ')}</div> : null}
            </button>
          )
        })}
      </div>
      {selected ? <div className="text-xs text-gray-500 leading-relaxed">画面：{selected.prompt}</div> : null}
    </div>
  )
}

const WorksPage: React.FC = () => {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [items, setItems] = useState<ProjectOverviewRead[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [styleOptions, setStyleOptions] = useState<ProjectStyleOptionsRead | null>(null)
  const [styleLoading, setStyleLoading] = useState(true)
  const [preset, setPreset] = useState<string | undefined>(undefined)
  const [form] = Form.useForm<CreateForm>()
  const { loading: setupLoading, status: setupStatus } = useSetupStatus()

  const load = async () => {
    setLoading(true)
    try {
      const res = await StudioProjectsService.listProjectsOverviewApiV1StudioProjectsOverviewGet()
      setItems(res.data ?? [])
    } catch {
      message.error('加载作品失败')
    } finally {
      setLoading(false)
    }
  }
  const loadStyles = async () => {
    setStyleLoading(true)
    try {
      const res = await StudioProjectsService.getProjectStyleOptionsApiV1StudioProjectsStyleOptionsGet()
      setStyleOptions(res.data ?? null)
    } catch {
      setStyleOptions(null)
    } finally {
      setStyleLoading(false)
    }
  }
  useEffect(() => {
    void load()
    void loadStyles()
  }, [])

  const presetsByKey = useMemo(() => new Map((styleOptions?.presets ?? []).map((p) => [p.key, p])), [styleOptions])

  const openCreate = () => {
    form.setFieldsValue({ name: '', style_prompt: '', ratio: '9:16' })
    setPreset(styleOptions?.default_preset ?? styleOptions?.presets?.[0]?.key)
    setOpen(true)
  }

  const create = async () => {
    const values = await form.validateFields()
    const chosen = preset ? presetsByKey.get(preset) : undefined
    if (!chosen) {
      message.warning('先选一种画面风格')
      return
    }
    setCreating(true)
    try {
      const id = crypto.randomUUID()
      await StudioProjectsService.createProjectApiV1StudioProjectsPost({
        requestBody: {
          id,
          name: values.name.trim(),
          description: '',
          style: chosen.style as never,
          visual_style: chosen.visual_style as never,
          style_preset: chosen.key,
          style_prompt: values.style_prompt?.trim() || null,
          default_video_ratio: values.ratio,
        },
      })
      setOpen(false)
      navigate(getCreatorPath(id, null, 'script'))
    } catch (e) {
      message.error(e instanceof Error ? e.message : '创建失败')
    } finally {
      setCreating(false)
    }
  }

  const remove = async (id: string) => {
    try {
      await StudioProjectsService.deleteProjectApiV1StudioProjectsProjectIdDelete({ projectId: id })
      message.success('已删除')
      await load()
    } catch {
      message.error('删除失败')
    }
  }

  return (
    <div className={`h-full overflow-auto ${isMobile ? 'p-3' : 'p-6'}`}>
      <div className="mx-auto max-w-[1200px] flex flex-col gap-4">
        <SetupStatusBanner status={setupStatus?.ready ? null : setupStatus} loading={setupLoading && !setupStatus} />
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold m-0">我的作品</h1>
            <p className="text-gray-500 text-sm m-0 mt-1">粘贴剧本，五步出片：剧本 → 角色场景 → 分镜 → 视频 → 成片。</p>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建作品</Button>
        </div>
        {loading ? (
          <div className="py-16 grid place-items-center"><Spin /></div>
        ) : items.length === 0 ? (
          <Card>
            <Empty description="还没有作品">
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建第一个作品</Button>
            </Empty>
          </Card>
        ) : (
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
            <div
              onClick={openCreate}
              className="rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-500 hover:text-blue-600 text-gray-500 cursor-pointer grid place-items-center aspect-[3/4] sm:aspect-auto sm:min-h-[260px]"
            >
              <div className="text-center">
                <PlusOutlined className="text-2xl" />
                <div className="mt-2 text-sm">新建作品</div>
              </div>
            </div>
            {items.map((p) => (
              <Card
                key={p.id}
                hoverable
                size="small"
                bodyStyle={{ padding: 12 }}
                onClick={() => navigate(getCreatorPath(p.id, p.latest_chapter_id))}
                cover={
                  <div className="relative aspect-[3/4] sm:aspect-[4/5] bg-gray-100 overflow-hidden rounded-t-lg">
                    {p.cover_url ? (
                      <img src={p.cover_url} alt="" className="absolute inset-0 w-full h-full object-cover" />
                    ) : (
                      <div className="absolute inset-0 grid place-items-center text-gray-300"><VideoCameraOutlined className="text-3xl" /></div>
                    )}
                    <div className="absolute left-2 top-2 flex gap-1">
                      <Tag className="m-0" color="default">{p.style_label || p.style}</Tag>
                    </div>
                  </div>
                }
              >
                <div className="font-medium truncate">{p.name}</div>
                <div className="text-xs text-gray-500 mt-1 tabular-nums">
                  {p.chapter_count} 集 · {p.shot_count} 镜头 · 视频 {p.video_count}/{p.shot_count}
                </div>
                <div className="flex justify-between items-center mt-2">
                  <span className="text-xs text-gray-400">{p.visual_style}</span>
                  <Popconfirm title="删除这个作品？所有镜头和生成结果都会一起删除。" okText="删除" cancelText="取消" onConfirm={() => void remove(p.id)} onPopupClick={(e) => e.stopPropagation()}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                  </Popconfirm>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Modal
        open={open}
        title="新建作品"
        okText="创建并开始"
        cancelText="取消"
        onOk={() => void create()}
        onCancel={() => setOpen(false)}
        confirmLoading={creating}
        destroyOnClose
        width={isMobile ? undefined : 720}
      >
        <Form form={form} layout="vertical" className="mt-3">
          <Form.Item name="name" label="作品名" rules={[{ required: true, message: '给作品起个名字' }]}>
            <Input id="work-name" placeholder="例如：大厂的神" maxLength={60} autoFocus />
          </Form.Item>
          <Form.Item label="画面风格" required extra="选一种整部作品统一的画面质感；之后的形象、关键帧、视频都按它生成。">
            {styleLoading ? (
              <div className="py-6 grid place-items-center"><Spin size="small" /></div>
            ) : styleOptions?.presets?.length ? (
              <StylePresetPicker options={styleOptions} value={preset} onChange={setPreset} isMobile={isMobile} />
            ) : (
              <div className="text-sm text-gray-500">
                风格列表加载失败。<Button type="link" size="small" onClick={() => void loadStyles()}>重试</Button>
              </div>
            )}
          </Form.Item>
          <Form.Item name="style_prompt" label="风格补充（可选）">
            <Input.TextArea rows={2} maxLength={200} placeholder="例如：整体偏青橙色调，多用逆光；主角服装以黑白为主" />
          </Form.Item>
          <Form.Item name="ratio" label="比例">
            <Segmented options={[{ label: '竖屏 9:16', value: '9:16' }, { label: '横屏 16:9', value: '16:9' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default WorksPage
