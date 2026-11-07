import { useEffect, useMemo, useRef, useState } from 'react'
import type { NavigateFunction } from 'react-router-dom'
import { StudioChaptersService, StudioShotsService } from '../../../services/generated'
import { StudioEntitiesApi } from '../../../services/studioEntities'
import { getCreatorPath } from '../../creator/routes'
import type { TaskUiItem } from './taskUiStore'

/**
 * 任务中心条目的来源标签与跳转目标。
 *
 * 为什么存在：任务只记录关联实体（章节 / 镜头 / 实体），任务中心需要把它翻译成
 * 「章节：第 1 集」这样的人话，并跳到创作页对应的集。
 */

type ResolvedTaskMeta = {
  sourceLabel?: string | null
  navigateTo?: string | null
}

const CHAPTER_RELATION_TYPES = new Set([
  'chapter_division',
  'script_extraction',
  'consistency_check',
  'script_optimization',
  'script_simplification',
])

const SHOT_RELATION_TYPES = new Set(['video', 'shot_first_frame_prompt', 'shot_last_frame_prompt', 'shot_key_frame_prompt'])

const ENTITY_LABELS: Record<string, string> = { actor: '演员', scene: '场景', prop: '道具', costume: '服装', character: '角色' }

function metaKeyForTask(task: TaskUiItem): string | null {
  if (task.navigateRelationType && task.navigateRelationEntityId) {
    return `${task.navigateRelationType}:${task.navigateRelationEntityId}`
  }
  if (task.relationType && task.relationEntityId) {
    return `${task.relationType}:${task.relationEntityId}`
  }
  return null
}

async function resolveTaskMeta(task: TaskUiItem): Promise<ResolvedTaskMeta | null> {
  const relationType = task.navigateRelationType ?? task.relationType
  const relationEntityId = task.navigateRelationEntityId ?? task.relationEntityId
  if (!relationType || !relationEntityId) return null

  if (CHAPTER_RELATION_TYPES.has(relationType)) {
    const res = await StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId: relationEntityId })
    const chapter = res.data
    if (!chapter) return null
    return { sourceLabel: `章节：${chapter.title || relationEntityId}`, navigateTo: getCreatorPath(chapter.project_id, chapter.id) }
  }

  if (SHOT_RELATION_TYPES.has(relationType) || relationType === 'shot') {
    const shotRes = await StudioShotsService.getShotApiV1StudioShotsShotIdGet({ shotId: relationEntityId })
    const shot = shotRes.data
    if (!shot) return null
    const chapterRes = await StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId: shot.chapter_id })
    const chapter = chapterRes.data
    const label = shot.title ? `镜头：${shot.title}（第 ${shot.index} 镜）` : `镜头：${relationEntityId}`
    const step = relationType === 'video' ? 'video' : 'storyboard'
    return { sourceLabel: label, navigateTo: chapter ? getCreatorPath(chapter.project_id, chapter.id, step) : null }
  }

  if (relationType in ENTITY_LABELS) {
    const entityType = relationType as 'actor' | 'scene' | 'prop' | 'costume' | 'character'
    try {
      const res = await StudioEntitiesApi.get(entityType, relationEntityId)
      const data = res.data as Record<string, unknown> | null
      const name = typeof data?.name === 'string' ? data.name.trim() : ''
      const projectId = typeof data?.project_id === 'string' ? data.project_id.trim() : ''
      return {
        sourceLabel: `${ENTITY_LABELS[entityType]}：${name || relationEntityId}`,
        navigateTo: projectId ? getCreatorPath(projectId, null, 'cast') : null,
      }
    } catch {
      return { sourceLabel: `${ENTITY_LABELS[entityType]}：${relationEntityId}`, navigateTo: null }
    }
  }

  // 形象图任务：relation_entity_id 为 "<type>_image:<id>" 形式时只给出标签
  if (relationEntityId.includes(':')) {
    const [assetRelationType, assetId] = relationEntityId.split(':', 2)
    const entityType = assetRelationType.replace(/_image$/, '')
    const label = ENTITY_LABELS[entityType]
    if (!label || !assetId) return null
    return { sourceLabel: `${label}形象：${assetId}`, navigateTo: null }
  }

  return null
}

export function useResolvedTaskCenterTasks(tasks: TaskUiItem[], navigate: NavigateFunction): TaskUiItem[] {
  const [metaMap, setMetaMap] = useState<Record<string, ResolvedTaskMeta>>({})
  const loadingKeysRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    tasks.forEach((task) => {
      const effectiveRelationType = task.navigateRelationType ?? task.relationType
      const effectiveRelationEntityId = task.navigateRelationEntityId ?? task.relationEntityId
      if ((task.sourceLabel && task.onNavigate) || !effectiveRelationType || !effectiveRelationEntityId) return
      const key = metaKeyForTask(task)
      if (!key || metaMap[key] || loadingKeysRef.current.has(key)) return
      loadingKeysRef.current.add(key)
      void resolveTaskMeta(task)
        .then((meta) => {
          if (cancelled || !meta) return
          setMetaMap((current) => ({ ...current, [key]: meta }))
        })
        .finally(() => {
          loadingKeysRef.current.delete(key)
        })
    })
    return () => {
      cancelled = true
    }
  }, [metaMap, tasks])

  return useMemo(
    () =>
      tasks.map((task) => {
        const key = metaKeyForTask(task)
        const meta = key ? metaMap[key] : undefined
        return {
          ...task,
          sourceLabel: task.sourceLabel ?? meta?.sourceLabel ?? null,
          onNavigate: task.onNavigate ?? (meta?.navigateTo ? () => navigate(meta.navigateTo!) : null),
        }
      }),
    [metaMap, navigate, tasks],
  )
}
