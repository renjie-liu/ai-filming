import type React from 'react';
import { useEffect, useState } from 'react'
import { Button, Card, Empty, Form, Input, Modal, Popconfirm, Segmented, Select, Spin, Tag, message } from 'antd'
import { DeleteOutlined, PlusOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { StudioProjectsService } from '../../services/generated'
import type { ProjectOverviewRead, ProjectStyleOptionsRead } from '../../services/generated'
import { useIsMobile } from '../../hooks/useIsMobile'
import SetupStatusBanner from '../aiStudio/models/SetupStatusBanner'
import { useSetupStatus } from '../aiStudio/models/useSetupStatus'
import { getCreatorPath } from './routes'

/** 作品列表：每个作品一张卡（封面、进度），「新建作品」直接进入创作页。 */

type CreateForm = { name: string; visual_style: string; style: string; ratio: string }

const WorksPage: React.FC = () => {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const [items, setItems] = useState<ProjectOverviewRead[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [styleOptions, setStyleOptions] = useState<ProjectStyleOptionsRead | null>(null)
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
  useEffect(() => {
    void load()
    StudioProjectsService.getProjectStyleOptionsApiV1StudioProjectsStyleOptionsGet()
      .then((res) => setStyleOptions(res.data ?? null))
      .catch(() => setStyleOptions(null))
  }, [])

  const visualStyle = Form.useWatch('visual_style', form)
  const styles = styleOptions?.styles_by_visual_style?.[visualStyle ?? ''] ?? []
  useEffect(() => {
    if (!visualStyle || !styleOptions) return
    const def = styleOptions.default_style_by_visual_style?.[visualStyle]
    const current = form.getFieldValue('style')
    if (!styles.some((s) => s.value === current)) form.setFieldValue('style', def ?? styles[0]?.value)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visualStyle, styleOptions])

  const openCreate = () => {
    const firstVisual = styleOptions?.visual_styles?.[0]?.value ?? '现实'
    form.setFieldsValue({ name: '', visual_style: firstVisual, style: styleOptions?.default_style_by_visual_style?.[firstVisual] ?? '', ratio: '9:16' })
    setOpen(true)
  }

  const create = async () => {
    const values = await form.validateFields()
    setCreating(true)
    try {
      const id = crypto.randomUUID()
      await StudioProjectsService.createProjectApiV1StudioProjectsPost({
        requestBody: { id, name: values.name.trim(), description: '', style: values.style as never, visual_style: values.visual_style as never, default_video_ratio: values.ratio },
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
                      <Tag className="m-0" color="default">{p.visual_style}</Tag>
                    </div>
                  </div>
                }
              >
                <div className="font-medium truncate">{p.name}</div>
                <div className="text-xs text-gray-500 mt-1 tabular-nums">
                  {p.chapter_count} 集 · {p.shot_count} 镜头 · 视频 {p.video_count}/{p.shot_count}
                </div>
                <div className="flex justify-between items-center mt-2">
                  <span className="text-xs text-gray-400">{p.style}</span>
                  <Popconfirm title="删除这个作品？所有镜头和生成结果都会一起删除。" okText="删除" cancelText="取消" onConfirm={() => void remove(p.id)} onPopupClick={(e) => e.stopPropagation()}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                  </Popconfirm>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Modal open={open} title="新建作品" okText="创建并开始" cancelText="取消" onOk={() => void create()} onCancel={() => setOpen(false)} confirmLoading={creating} destroyOnClose>
        <Form form={form} layout="vertical" className="mt-3">
          <Form.Item name="name" label="作品名" rules={[{ required: true, message: '给作品起个名字' }]}>
            <Input id="work-name" placeholder="例如：大厂的神" maxLength={60} autoFocus />
          </Form.Item>
          <Form.Item name="visual_style" label="画面">
            <Segmented options={(styleOptions?.visual_styles ?? [{ value: '现实', label: '真人实拍' }]).map((o) => ({ value: o.value, label: o.label }))} />
          </Form.Item>
          <Form.Item name="style" label="题材">
            <Select options={styles.map((s) => ({ value: s.value, label: s.label }))} />
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
