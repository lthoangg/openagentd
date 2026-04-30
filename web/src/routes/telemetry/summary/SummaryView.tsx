/**
 * Aggregate summary panels (totals, latency, daily turns, by-model, by-tool).
 * Renders the data shape returned by `useObservabilitySummaryQuery`.
 */

import { Info } from 'lucide-react'
import type { ObservabilitySummary } from '@/api/client'
import {
  formatCompact,
  formatInt,
  formatMs,
} from '@/utils/telemetryFormat'
import { EmptyTable, SectionHeader, Stat, Table } from '../primitives'
import { DailyBars } from './DailyBars'

export function SummaryView({ data }: { data: ObservabilitySummary }) {
  const sampled = data.sample_ratio < 1.0
  const { totals, latency_ms } = data

  return (
    <div className="flex flex-col gap-5">
      {sampled && (
        <div className="flex items-start gap-2 rounded-lg border border-(--color-border) bg-(--color-accent-subtle)/40 p-3">
          <Info size={14} className="mt-0.5 shrink-0 text-(--color-accent)" />
          <p className="text-xs text-(--color-text-2)">
            Spans are sampled at <strong>{Math.round(data.sample_ratio * 100)}%</strong>.
            Figures for non-error, non-slow spans are approximate. Set{' '}
            <code className="rounded bg-(--color-surface) px-1 py-0.5 text-[10px]">
              OTEL_SPAN_SAMPLE_RATIO=1.0
            </code>{' '}
            to disable sampling.
          </p>
        </div>
      )}

      <section>
        <SectionHeader>Totals</SectionHeader>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Turns" value={formatInt(totals.turns)} />
          <Stat label="LLM calls" value={formatInt(totals.llm_calls)} />
          <Stat label="Tool calls" value={formatInt(totals.tool_calls)} />
          <Stat label="Input tokens" value={formatCompact(totals.input_tokens)} />
          <Stat label="Output tokens" value={formatCompact(totals.output_tokens)} />
          <Stat
            label="Errors"
            value={formatInt(totals.errors)}
            tone={totals.errors > 0 ? 'danger' : undefined}
          />
        </div>
      </section>

      <section>
        <SectionHeader>Latency</SectionHeader>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Turn p50" value={formatMs(latency_ms.turn_p50)} />
          <Stat label="Turn p95" value={formatMs(latency_ms.turn_p95)} />
          <Stat label="LLM p50" value={formatMs(latency_ms.llm_p50)} />
          <Stat label="LLM p95" value={formatMs(latency_ms.llm_p95)} />
        </div>
      </section>

      <section>
        <SectionHeader>Turns per day</SectionHeader>
        <DailyBars rows={data.daily_turns} />
      </section>

      <section>
        <SectionHeader>By model</SectionHeader>
        {data.by_model.length === 0 ? (
          <EmptyTable label="No LLM calls recorded in this window." />
        ) : (
          <Table
            headers={['Model', 'Calls', 'Input', 'Output', 'p95 ms']}
            rows={data.by_model.map((m) => [
              m.model,
              formatInt(m.calls),
              formatCompact(m.input_tokens),
              formatCompact(m.output_tokens),
              formatMs(m.p95_ms),
            ])}
            align={['left', 'right', 'right', 'right', 'right']}
          />
        )}
      </section>

      <section>
        <SectionHeader>By tool</SectionHeader>
        {data.by_tool.length === 0 ? (
          <EmptyTable label="No tool invocations recorded in this window." />
        ) : (
          <Table
            headers={['Tool', 'Calls', 'Errors', 'p95 ms']}
            rows={data.by_tool.map((t) => [
              t.tool,
              formatInt(t.calls),
              t.errors > 0 ? (
                <span className="text-(--color-danger)">{formatInt(t.errors)}</span>
              ) : (
                '0'
              ),
              formatMs(t.p95_ms),
            ])}
            align={['left', 'right', 'right', 'right']}
          />
        )}
      </section>
    </div>
  )
}
