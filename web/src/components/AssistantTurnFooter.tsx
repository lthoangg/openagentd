/**
 * Footer rendered at the bottom of a completed assistant turn, plus the
 * `AssistantTurn` wrapper that groups a turn's blocks and decides when to
 * show the footer.
 *
 * Used by both the compact pane (split / unified) and the wide single-agent
 * view. Each view passes its own `renderBlock` so the per-view block visuals
 * (e.g. compact vs roomy `UserBubble`) stay independent.
 */
import { useState, type ReactNode } from 'react'
import { Copy, Check } from 'lucide-react'
import { formatTime, lastTurnText } from '@/utils/format'
import type { ContentBlock } from '@/api/types'

export interface AssistantTurnFooterProps {
  /** Blocks belonging to a single assistant turn (no user blocks inside). */
  turnBlocks: ContentBlock[]
  /** Visual density: 'compact' for narrow panes, 'roomy' for the wide view. */
  size?: 'compact' | 'roomy'
}

export function AssistantTurnFooter({ turnBlocks, size = 'compact' }: AssistantTurnFooterProps) {
  const [copied, setCopied] = useState(false)
  // Me lastTurnText walks back to the previous user block; pass the turn directly
  const textContent = lastTurnText(turnBlocks)
  const lastBlock = turnBlocks[turnBlocks.length - 1]
  const timestamp = lastBlock?.timestamp

  if (!textContent && !timestamp) return null

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(textContent)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }

  const wrapperClass = size === 'roomy' ? 'mt-1 flex items-center gap-1.5' : 'mt-0.5 flex items-center gap-1'
  const iconSize = size === 'roomy' ? 11 : 10

  return (
    <div className={wrapperClass}>
      {textContent && (
        <button
          onClick={handleCopy}
          className="rounded p-0.5 text-(--color-text-muted) transition-colors hover:text-(--color-text-2)"
          aria-label="Copy response"
          title="Copy"
        >
          {copied
            ? <Check size={iconSize} className="text-(--color-success)" />
            : <Copy size={iconSize} />}
        </button>
      )}
      {timestamp && <span className="text-(--color-text-subtle) text-xs">{formatTime(timestamp)}</span>}
    </div>
  )
}

export interface AssistantTurnProps {
  /** Blocks belonging to this turn (no user blocks inside). */
  blocks: ContentBlock[]
  /** Absolute index of `blocks[0]` in the parent's full block list. */
  startIndex: number
  /** Number of finalized blocks (i.e. `stream.blocks.length`); blocks at or
   *  past this index are still in-flight when `isWorking` is true. */
  finalizedCount: number
  /** True while the agent is actively streaming. */
  isWorking: boolean
  /** True when this turn has no user block after it (i.e. trailing). Only
   *  trailing turns can be "live"; any turn followed by a user message is
   *  finalized regardless of `isWorking`. */
  isTrailingTurn: boolean
  /** Total length of the parent's full block list (for `isLast` cursor). */
  totalBlocks: number
  /** Per-view block renderer. */
  renderBlock: (args: { block: ContentBlock; isStreaming: boolean; isLast: boolean }) => ReactNode
  /** Footer density. */
  size?: 'compact' | 'roomy'
}

export function AssistantTurn({
  blocks,
  startIndex,
  finalizedCount,
  isWorking,
  isTrailingTurn,
  totalBlocks,
  renderBlock,
  size = 'compact',
}: AssistantTurnProps) {
  const turnIsStreaming = isWorking && isTrailingTurn

  return (
    <div className="space-y-2">
      {blocks.map((block, j) => {
        const absoluteIdx = startIndex + j
        const isStreaming = isWorking && absoluteIdx >= finalizedCount
        return (
          <div key={block.id}>
            {renderBlock({
              block,
              isStreaming,
              isLast: absoluteIdx === totalBlocks - 1,
            })}
          </div>
        )
      })}
      {!turnIsStreaming && <AssistantTurnFooter turnBlocks={blocks} size={size} />}
    </div>
  )
}
