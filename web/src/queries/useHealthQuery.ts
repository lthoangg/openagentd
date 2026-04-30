import { useQuery } from '@tanstack/react-query'
import { health } from '@/api/client'
import { queryKeys } from './keys'

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: health,
    retry: 3,
    retryDelay: 1000,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  })
}
