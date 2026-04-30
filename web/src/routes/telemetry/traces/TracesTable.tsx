/**
 * Recent traces table — header rendered by ``TracesSection``.  Each row is
 * clickable; the parent owns the selection state.
 */

import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import type { TraceListItem } from '@/api/client'
import {
  formatCompact,
  formatInt,
  formatMs,
  formatShortId,
  timeAgo,
} from '@/utils/telemetryFormat'
import { Td, Th } from '../primitives'

export function TracesTable({
  traces,
  onSelect,
}: {
  traces: TraceListItem[]
  onSelect: (traceId: string) => void
}) {
  // "Now" is captured once per TracesTable mount via a lazy useState initializer
  // — keeps the render pure (no Date.now() call during render) while still
  // giving fresh labels whenever the table unmounts/remounts on refetch.
  const [now] = useState(() => Date.now())
  return (
    <div className="overflow-x-auto rounded-lg border border-(--color-border) bg-(--color-surface)">
      <table className="min-w-[640px] w-full text-xs">
        <thead>
          <tr className="border-b border-(--color-border) bg-(--color-surface-2)">
            <Th>When</Th>
            <Th>Session</Th>
            <Th>Agent</Th>
            <Th>Model</Th>
            <Th align="right">Duration</Th>
            <Th align="right">LLM</Th>
            <Th align="right">Tools</Th>
            <Th align="right">Tokens (in / out)</Th>
            <Th align="right">Status</Th>
            <Th />
          </tr>
        </thead>
        <tbody>
          {traces.map((t) => (
            <tr
              key={t.trace_id}
              onClick={() => onSelect(t.trace_id)}
              className="cursor-pointer border-b border-(--color-border) transition-colors last:border-b-0 hover:bg-(--color-accent-subtle)/40"
            >
              <Td>
                <span title={new Date(t.start_ms).toLocaleString()}>
                  {timeAgo(t.start_ms, now)}
                </span>
              </Td>
              <Td muted mono>
                {t.session_id ? formatShortId(t.session_id) : '—'}
              </Td>
              <Td>{t.agent_name ?? '—'}</Td>
              <Td muted>{t.model ?? '—'}</Td>
              <Td align="right">{formatMs(t.duration_ms)}</Td>
              <Td align="right">{formatInt(t.llm_calls)}</Td>
              <Td align="right">{formatInt(t.tool_calls)}</Td>
              <Td align="right" muted>
                {formatCompact(t.input_tokens)} / {formatCompact(t.output_tokens)}
              </Td>
              <Td align="right">
                {t.error ? (
                  <span className="rounded bg-(--color-danger-subtle) px-1.5 py-0.5 text-[10px] font-medium text-(--color-danger)">
                    error
                  </span>
                ) : (
                  <span className="text-(--color-text-muted)">ok</span>
                )}
              </Td>
              <Td align="right">
                <ChevronRight size={14} className="text-(--color-text-muted)" />
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
