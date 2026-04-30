/**
 * Status dot — matches the ``AgentCapabilities`` colour vocabulary so a
 * tool call's running state reads consistently with agent-level status.
 */

import type { ToolCallState } from './types'

export function StatusDot({ state }: { state: ToolCallState }) {
  const cls =
    state === 'pending'
      ? 'bg-(--color-text-muted)'
      : state === 'running'
        ? 'bg-(--color-accent) shadow-[0_0_5px_var(--color-accent)] animate-pulse'
        : 'bg-(--color-success)'
  return (
    <span
      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${cls}`}
      aria-hidden
    />
  )
}
