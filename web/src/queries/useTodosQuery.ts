import { useQuery } from '@tanstack/react-query'
import { getTodos } from '@/api/client'
import { queryKeys } from './keys'

export function useTodosQuery(sessionId: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.todos(sessionId ?? ''),
    queryFn: () => getTodos(sessionId as string),
    enabled: !!sessionId,
    staleTime: 5_000,
  })
}
