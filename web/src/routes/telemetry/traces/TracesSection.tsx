/**
 * Recent-traces section: wraps ``TracesTable`` with loading/error/empty
 * states keyed off the TanStack Query result.
 */

import type { useTracesQuery } from '@/queries'
import { EmptyTable, SectionHeader } from '../primitives'
import { TracesTable } from './TracesTable'

type TracesQueryResult = ReturnType<typeof useTracesQuery>

export function TracesSection({
  query,
  onSelectTrace,
}: {
  query: TracesQueryResult
  onSelectTrace: (traceId: string) => void
}) {
  return (
    <section>
      <SectionHeader>Recent traces</SectionHeader>
      {query.isLoading ? (
        <EmptyTable label="Loading traces…" />
      ) : query.isError ? (
        <EmptyTable label={`Could not load traces: ${String(query.error)}`} />
      ) : query.data && 'unavailable' in query.data ? (
        // Summary already shows the dedicated unavailable banner; skip here.
        null
      ) : query.data && query.data.traces.length === 0 ? (
        <EmptyTable label="No traces in this window." />
      ) : query.data ? (
        <TracesTable traces={query.data.traces} onSelect={onSelectTrace} />
      ) : null}
    </section>
  )
}
