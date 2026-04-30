import { useQuery } from '@tanstack/react-query'
import { getObservabilitySummary } from '@/api/client'
import { queryKeys } from './keys'

export function useObservabilitySummaryQuery(days: number) {
  return useQuery({
    queryKey: queryKeys.observability.summary(days),
    queryFn: () => getObservabilitySummary(days),
    // Span aggregates evolve slowly; refresh on manual navigation only.
    staleTime: 60_000,
  })
}
