/**
 * /telemetry — standalone top-level page.
 *
 * Two modes driven by local state:
 *   - No trace selected: aggregates (totals, latency, breakdowns) + traces list.
 *   - Trace selected: waterfall view with optional span attribute side panel.
 *
 * All data comes from OTEL span JSONL files, aggregated through DuckDB on the
 * backend.  When the `[otel]` extra isn't installed the backend returns a
 * structured 503 that we surface as a dedicated empty state.
 */

import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import {
  useObservabilitySummaryQuery,
  useTraceDetailQuery,
  useTracesQuery,
} from '@/queries'
import { useIsMobile } from '@/hooks/use-mobile'
import { formatShortId } from '@/utils/telemetryFormat'
import { ErrorState, LoadingState, PageHeader, UnavailableState } from './chrome'
import { SummaryView } from './summary/SummaryView'
import { TracesSection } from './traces/TracesSection'
import { SpanDetailPanel } from './waterfall/SpanDetailPanel'
import { Waterfall } from './waterfall/Waterfall'

type WindowDays = 1 | 7 | 30 | 90

const RANGES: { value: WindowDays; label: string }[] = [
  { value: 1, label: '24 h' },
  { value: 7, label: '7 d' },
  { value: 30, label: '30 d' },
  { value: 90, label: '90 d' },
]

export function TelemetryPage() {
  const [days, setDays] = useState<WindowDays>(7)
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-(--color-bg) text-(--color-text)">
      {selectedTraceId ? (
        <TraceDetailRoute
          traceId={selectedTraceId}
          onBack={() => setSelectedTraceId(null)}
        />
      ) : (
        <SummaryRoute
          days={days}
          onChangeDays={setDays}
          onSelectTrace={setSelectedTraceId}
        />
      )}
    </div>
  )
}

// ── Summary route ────────────────────────────────────────────────────────────

function SummaryRoute({
  days,
  onChangeDays,
  onSelectTrace,
}: {
  days: WindowDays
  onChangeDays: (d: WindowDays) => void
  onSelectTrace: (traceId: string) => void
}) {
  const summary = useObservabilitySummaryQuery(days)
  const traces = useTracesQuery(days, 50, 0)
  const isFetching = summary.isFetching || traces.isFetching

  return (
    <>
      <PageHeader
        isFetching={isFetching}
        right={
          <>
            <div className="flex items-center gap-1 rounded-lg border border-(--color-border) bg-(--color-surface) p-0.5">
              {RANGES.map((r) => (
                <button
                  key={r.value}
                  onClick={() => onChangeDays(r.value)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    days === r.value
                      ? 'bg-(--color-accent-subtle) text-(--color-accent)'
                      : 'text-(--color-text-muted) hover:text-(--color-text)'
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <Link
              to="/"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text-2)"
              aria-label="Back to home"
              title="Back to home"
            >
              <ArrowLeft size={15} />
            </Link>
          </>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {summary.isLoading ? (
          <LoadingState label="Loading span aggregates…" />
        ) : summary.isError ? (
          <ErrorState
            message={String(summary.error)}
            onRetry={() => summary.refetch()}
          />
        ) : summary.data && 'unavailable' in summary.data ? (
          <UnavailableState payload={summary.data} />
        ) : summary.data ? (
          <div className="flex flex-col gap-6">
            <SummaryView data={summary.data} />
            <TracesSection
              query={traces}
              onSelectTrace={onSelectTrace}
            />
          </div>
        ) : null}
      </div>
    </>
  )
}

// ── Trace detail route ──────────────────────────────────────────────────────

function TraceDetailRoute({
  traceId,
  onBack,
}: {
  traceId: string
  onBack: () => void
}) {
  const isMobile = useIsMobile()
  const { data, isLoading, isError, error, refetch, isFetching } =
    useTraceDetailQuery(traceId)
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  const selectedSpan =
    data?.spans.find((s) => s.span_id === selectedSpanId) ?? null

  return (
    <>
      <PageHeader
        isFetching={isFetching}
        left={
          <button
            onClick={onBack}
            className="flex h-7 w-7 items-center justify-center rounded-md text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
            aria-label="Back to list"
          >
            <ArrowLeft size={14} />
          </button>
        }
        subtitle={`Trace ${formatShortId(traceId)}`}
        right={
          <Link
            to="/"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text-2)"
            aria-label="Back to home"
            title="Back to home"
          >
            <ArrowLeft size={15} />
          </Link>
        }
      />

      {/* On mobile: span detail overlays the waterfall full-width (absolute).
          On desktop: span detail is a fixed-width flex sibling on the right. */}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        <div className="min-w-0 flex-1 overflow-y-auto p-5">
          {isLoading ? (
            <LoadingState label="Loading trace…" />
          ) : isError ? (
            <ErrorState
              message={String(error)}
              onRetry={() => refetch()}
            />
          ) : !data ? (
            <div className="rounded-xl border border-(--color-border) bg-(--color-surface-2) p-6 text-center">
              <p className="text-sm font-medium text-(--color-text)">
                Trace not found
              </p>
              <p className="mt-1 text-xs text-(--color-text-muted)">
                This trace may have expired from the retention window.
              </p>
            </div>
          ) : (
            <Waterfall
              spans={data.spans}
              selectedSpanId={selectedSpanId}
              onSelectSpan={setSelectedSpanId}
            />
          )}
        </div>
        {selectedSpan && (
          isMobile ? (
            // Full-width overlay on mobile
            <div className="absolute inset-0 z-10 overflow-y-auto bg-(--color-surface)">
              <SpanDetailPanel
                span={selectedSpan}
                onClose={() => setSelectedSpanId(null)}
                fullWidth
              />
            </div>
          ) : (
            <SpanDetailPanel
              span={selectedSpan}
              onClose={() => setSelectedSpanId(null)}
            />
          )
        )}
      </div>
    </>
  )
}
