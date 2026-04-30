import { useQuery } from '@tanstack/react-query'
import { listTeamAgents } from '@/api/client'
import { queryKeys } from './keys'

/** Team mode — GET /team/agents */
export function useTeamAgentsQuery() {
  return useQuery({
    queryKey: [...queryKeys.agents(), 'team'],
    queryFn: listTeamAgents,
    staleTime: 30_000,
  })
}
