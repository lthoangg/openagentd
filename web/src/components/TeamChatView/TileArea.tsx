/**
 * TileArea — recursive tile-tree pane host for the `unified` view mode.
 *
 * Wraps ``TileTree`` with the empty state (a sitting stickman + hint
 * message) and the outer flex/padding chrome. The actual tile recursion
 * and split logic lives in ``../TileTree``; the per-tile-leaf state
 * (open agents, focused agent, swap, close) is owned by
 * ``useTileLayout`` and threaded through here as ``tileLayout``.
 */
import StickmanSit from '@/assets/stickman-sit.svg?react'
import { TileTree } from '../TileTree'
import type { useTileLayout } from '@/hooks/useTileLayout'
import type { AgentStream } from '@/stores/useTeamStore'

interface TileAreaProps {
  tileLayout: ReturnType<typeof useTileLayout>
  agentStreams: Record<string, AgentStream>
  leadName: string | null
}

export function TileArea({ tileLayout, agentStreams, leadName }: TileAreaProps) {
  const { root, focusedAgent, focusAgent, closeAgent, swapAgents } = tileLayout

  if (!root) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <StickmanSit className="text-(--color-text-subtle) opacity-25" width={64} height={64} />
        <p className="text-sm text-(--color-text-muted)">No agent panes open · click a tab above to open one</p>
      </div>
    )
  }

  return (
    <div className="min-h-0 flex-1 p-3">
      <TileTree
        node={root}
        agentStreams={agentStreams}
        leadName={leadName}
        focusedAgent={focusedAgent}
        onFocus={focusAgent}
        onClose={closeAgent}
        onSwap={swapAgents}
      />
    </div>
  )
}
