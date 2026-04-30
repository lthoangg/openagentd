import { formatTokens } from '@/utils/format'
import type { AgentStream } from '@/stores/useTeamStore'

interface TeamStatusBarProps {
  sessionId: string | null
  leadName?: string | null
  isWorking?: boolean
  agentStreams: Record<string, AgentStream>
  error?: string | null
}

function StatusDot({ status }: { status: string }) {
  const colorClass =
    status === 'working'
      ? 'bg-(--color-accent)'
      : status === 'error'
        ? 'bg-(--color-error)'
        : 'bg-(--color-success)'
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${colorClass} ${
        status === 'working' ? 'animate-pulse' : ''
      }`}
    />
  )
}

export function TeamStatusBar({
  sessionId,
  leadName,
  isWorking,
  agentStreams,
  error,
}: TeamStatusBarProps) {
  return (
    <div className="flex items-center justify-between border-t border-(--color-border) bg-(--color-bg) px-4 py-1 text-xs text-(--color-text-muted)">
      {/* Left */}
      <div className="flex items-center gap-2">
        {sessionId && (
          <span className="font-mono text-(--color-text-muted)">
            {sessionId.slice(0, 8)}
          </span>
        )}
        {leadName && (
          <span className="text-(--color-text-muted)">lead: {leadName}</span>
        )}
        {isWorking && (
          <span className="flex items-center gap-1 text-(--color-text-2)">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-(--color-accent)" />
            working
          </span>
        )}
      </div>

      {/* Center: error */}
      {error && (
        <span className="max-w-xs truncate text-(--color-error)">
          {error}
        </span>
      )}

      {/* Right: agent pills */}
      <div className="flex items-center gap-1">
        {Object.entries(agentStreams).map(([name, stream]) => (
          <div
            key={name}
            className="flex items-center gap-1 rounded-md bg-(--color-surface-2) px-1.5 py-0.5"
          >
            <StatusDot status={stream.status} />
            <span className="text-(--color-text-2)">{name}</span>
            {stream.usage.totalTokens > 0 && (
              <span className="text-(--color-text-muted)">
                {formatTokens(stream.usage.totalTokens)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
