import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listTeamSessions, deleteTeamSession } from '@/api/client'
import type { SessionPageResponse } from '@/api/types'
import { queryKeys } from './keys'

const PAGE_SIZE = 20

export function useTeamSessionsQuery() {
  return useInfiniteQuery({
    queryKey: queryKeys.team.sessions.infinite(),
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      listTeamSessions(pageParam, PAGE_SIZE),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: SessionPageResponse) =>
      lastPage.has_more ? lastPage.next_cursor : undefined,
  })
}

export function useDeleteTeamSessionMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteTeamSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.team.sessions.all() })
    },
  })
}
