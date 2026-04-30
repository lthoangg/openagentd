/**
 * AgentTabStrip — header tab strip for the `unified` view mode.
 *
 * Each agent gets one of two tab styles:
 *
 *   • Open pane (currently mounted in the tile tree):
 *       [● name ×]   — accent text, status dot, close button on hover
 *
 *   • Minimized (not in the tile tree):
 *       [● name]     — muted, click to open as a brand-new split pane
 *
 * Status dot semantics match the rest of the app: pulsing accent =
 * working, error red = error, success green / muted border = idle.
 *
 * The strip itself is presentational; tile-tree mutations (focus, open,
 * close) flow back to the parent via ``onFocusOpen`` / ``onOpenMinimized``
 * / ``onClose`` callbacks.
 */
import type { AgentStream } from '@/stores/useTeamStore'

interface AgentTabStripProps {
  agentNames: string[]
  agentStreams: Record<string, AgentStream>
  leadName: string | null
  openAgents: string[]
  focusedAgent: string | null
  onFocusOpen: (name: string) => void
  onOpenMinimized: (name: string) => void
  onClose: (name: string) => void
}

export function AgentTabStrip({
  agentNames,
  agentStreams,
  leadName,
  openAgents,
  focusedAgent,
  onFocusOpen,
  onOpenMinimized,
  onClose,
}: AgentTabStripProps) {
  const openSet = new Set(openAgents)

  return (
    <div className="flex items-center gap-0.5 overflow-x-auto">
      {agentNames.map((name) => {
        const stream = agentStreams[name]
        const isOpen = openSet.has(name)
        const isFocused = focusedAgent === name
        const isWorking = stream?.status === 'working'
        const isError = stream?.status === 'error'
        const isLead = name === leadName

        if (isOpen) {
          return (
            <button
              key={name}
              onClick={() => onFocusOpen(name)}
              className={`interactive-weight group flex shrink-0 items-center gap-1.5 rounded-t-lg border-b-2 px-2.5 py-1.5 text-xs transition-all ${
                isFocused
                  ? 'border-b-(--color-accent) bg-(--color-accent-subtle) text-(--color-accent)'
                  : 'border-b-transparent text-(--color-text-2) hover:bg-(--color-accent-dim) hover:text-(--color-text)'
              }`}
            >
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                isError ? 'bg-(--color-error)' : isWorking ? 'animate-pulse bg-(--color-accent)' : 'bg-(--color-success)'
              }`} />
              <span className="max-w-30 truncate">
                {name}{isLead && <span className="ml-1 text-(--color-text-subtle)">·</span>}
              </span>
              <span
                onClick={(e) => { e.stopPropagation(); onClose(name) }}
                role="button"
                aria-label={`Minimize ${name}`}
                title="Minimize pane"
                className={`flex items-center rounded p-0.5 transition-colors ${
                  isFocused
                    ? 'text-(--color-accent) hover:bg-(--color-accent-subtle)'
                    : 'text-(--color-text-subtle) opacity-0 group-hover:opacity-100 hover:text-(--color-text-2)'
                }`}
              >×</span>
            </button>
          )
        }

        return (
          <button
            key={name}
            onClick={() => onOpenMinimized(name)}
            title={`Open ${name} as new split pane`}
            className="flex shrink-0 items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-(--color-text-muted) transition-all hover:bg-(--color-accent-dim) hover:text-(--color-text-2)"
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              isError ? 'bg-(--color-error)' : isWorking ? 'animate-pulse bg-(--color-accent)' : 'bg-(--color-border-strong)'
            }`} />
            <span className="max-w-25 truncate opacity-60">{name}</span>
          </button>
        )
      })}
    </div>
  )
}
