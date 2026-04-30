import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listScheduledTasks,
  createScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  pauseScheduledTask,
  resumeScheduledTask,
  triggerScheduledTask,
} from '@/api/client'
import type { ScheduledTaskCreate } from '@/api/types'
import { queryKeys } from './keys'

/** GET /scheduler/tasks — list all scheduled tasks */
export function useScheduledTasksQuery() {
  return useQuery({
    queryKey: queryKeys.scheduler.list(),
    queryFn: listScheduledTasks,
    staleTime: 10_000,
  })
}

/** POST /scheduler/tasks — create a new scheduled task */
export function useCreateScheduledTaskMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ScheduledTaskCreate) => createScheduledTask(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    },
  })
}

/** PUT /scheduler/tasks/{id} — update an existing scheduled task */
export function useUpdateScheduledTaskMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ScheduledTaskCreate> }) =>
      updateScheduledTask(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    },
  })
}

/** DELETE /scheduler/tasks/{id} — delete a scheduled task */
export function useDeleteScheduledTaskMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteScheduledTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    },
  })
}

/** POST /scheduler/tasks/{id}/pause — pause a scheduled task */
export function usePauseScheduledTaskMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => pauseScheduledTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    },
  })
}

/** POST /scheduler/tasks/{id}/resume — resume a scheduled task */
export function useResumeScheduledTaskMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => resumeScheduledTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    },
  })
}

/** POST /scheduler/tasks/{id}/trigger — trigger a scheduled task immediately */
export function useTriggerScheduledTaskMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => triggerScheduledTask(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    },
  })
}
