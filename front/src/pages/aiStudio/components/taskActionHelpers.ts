import { message } from 'antd'
import { toChineseErrorMessage } from '../../../utils/errorMessage'
import { FilmService } from '../../../services/generated'
import type { TaskStatus } from '../../../services/generated'
import type { RelationTaskState } from '../../creator/relationTasks'

type AsyncTaskCreateLike = {
  task_id: string
  status: TaskStatus
  reused?: boolean | null
}

type AsyncTaskCreateResponse<T extends AsyncTaskCreateLike> = {
  data?: T | null
  message?: string | null
}

type ExecuteAsyncTaskCreateOptions<T extends AsyncTaskCreateLike> = {
  request: () => Promise<AsyncTaskCreateResponse<T>>
  trackTaskData: (
    data: { task_id: string; status: TaskStatus },
    options?: { cancelRequested?: boolean }
  ) => RelationTaskState | null
  startedMessage: string
  reusedMessage: string
  fallbackErrorMessage: string
  emptyDataErrorMessage?: string
  getErrorMessage?: (error: unknown, fallbackErrorMessage: string) => string
}

/** 任务类操作的默认错误提示：提取后端错误并转换为中文（无法识别时使用 fallbackErrorMessage）。 */
export function defaultTaskActionErrorMessage(error: unknown, fallbackErrorMessage: string): string {
  return toChineseErrorMessage(error, fallbackErrorMessage)
}

type TaskCancelReadLike = {
  task_id?: string | null
  status?: TaskStatus | null
  cancel_requested?: boolean | null
  effective_immediately?: boolean | null
}

type TaskCancelResponse<T extends TaskCancelReadLike> = {
  data?: T | null
  message?: string | null
}

type ExecuteTaskCancelOptions<T extends TaskCancelReadLike> = {
  taskId: string
  reason?: string
  applyCancelData: (data?: T | null) => RelationTaskState | null
  cancelledImmediatelyMessage: string
  cancelRequestedMessage: string
  fallbackErrorMessage: string
  getErrorMessage?: (error: unknown, fallbackErrorMessage: string) => string
}

type NotifyExistingTaskOptions = {
  runningMessage: string
  cancellingMessage: string
}

export async function executeAsyncTaskCreate<T extends AsyncTaskCreateLike>({
  request,
  trackTaskData,
  startedMessage,
  reusedMessage,
  fallbackErrorMessage,
  emptyDataErrorMessage,
  getErrorMessage = defaultTaskActionErrorMessage,
}: ExecuteAsyncTaskCreateOptions<T>): Promise<T | null> {
  try {
    const res = await request()
    const data = res.data
    if (!data) {
      message.error(res.message || emptyDataErrorMessage || fallbackErrorMessage)
      return null
    }
    trackTaskData({ task_id: data.task_id, status: data.status })
    message.success(data.reused ? reusedMessage : startedMessage)
    return data
  } catch (error) {
    message.error(getErrorMessage(error, fallbackErrorMessage))
    return null
  }
}

export async function executeTaskCancel<T extends TaskCancelReadLike>({
  taskId,
  reason,
  applyCancelData,
  cancelledImmediatelyMessage,
  cancelRequestedMessage,
  fallbackErrorMessage,
  getErrorMessage = defaultTaskActionErrorMessage,
}: ExecuteTaskCancelOptions<T>): Promise<T | null> {
  try {
    const res = (await FilmService.cancelTaskApiV1FilmTasksTaskIdCancelPost({
      taskId,
      requestBody: { reason },
    })) as TaskCancelResponse<T>
    const data = res.data
    applyCancelData(data)
    message.success(data?.effective_immediately ? cancelledImmediatelyMessage : cancelRequestedMessage)
    return data ?? null
  } catch (error) {
    message.error(getErrorMessage(error, fallbackErrorMessage))
    return null
  }
}

export function notifyExistingTask(
  task: Pick<RelationTaskState, 'cancelRequested'> | null | undefined,
  options: NotifyExistingTaskOptions,
): boolean {
  if (!task) return false
  message.info(task.cancelRequested ? options.cancellingMessage : options.runningMessage)
  return true
}
