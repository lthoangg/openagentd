import { useQuery } from '@tanstack/react-query'
import { listTraces, getTraceDetail } from '@/api/client'
import { queryKeys } from './keys'

/** Paginated list of ``agent_run`` spans (one row per turn). */
export function useTracesQuery(days: number, limit = 50, offset = 0) {
  return useQuery({
    queryKey: queryKeys.observability.traces(days, limit, offset),
    queryFn: () => listTraces(days, limit, offset),
    // Traces are append-only — moderate staleness is fine.
    staleTime: 30_000,
  })
}

/** Full span tree for one trace.  ``null`` when the trace has expired. */
export function useTraceDetailQuery(traceId: string | null) {
  return useQuery({
    queryKey: queryKeys.observability.trace(traceId ?? ''),
    queryFn: () => getTraceDetail(traceId!),
    // Only fetch when a trace is selected.
    enabled: traceId !== null && traceId !== '',
    // Historical data — never goes stale inside a session.
    staleTime: Infinity,
  })
}
