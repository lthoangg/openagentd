import { useQuery } from '@tanstack/react-query'
import { teamStatus } from '@/api/client'
import { queryKeys } from './keys'
import type { TeamStatusResponse } from '@/api/types'

export function useTeamStatusQuery() {
  return useQuery<TeamStatusResponse | null>({
    queryKey: queryKeys.team.status(),
    queryFn: teamStatus,
    retry: false,
    staleTime: Infinity,
  })
}
