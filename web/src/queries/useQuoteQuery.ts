import { useQuery } from '@tanstack/react-query'
import { getQuoteOfTheDay } from '@/api/client'
import { queryKeys } from './keys'

export function useQuoteQuery() {
  return useQuery({
    queryKey: queryKeys.quote(),
    queryFn: getQuoteOfTheDay,
    // Cache for 1 hour — the backend already caches per day, this just avoids
    // re-fetching on every component mount within the same browser session.
    staleTime: 60 * 60 * 1000,
    retry: 1,
  })
}
