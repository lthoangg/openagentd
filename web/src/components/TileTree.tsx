/**
 * TileTree — recursive tmux-style tile layout for the unified view.
 *
 * A Leaf node renders an AgentPane.
 * A Split node renders two TileTree children separated by a divider,
 * laid out horizontally (dir='h') or vertically (dir='v').
 *
 * Focus ring is shown on the leaf whose agentName === focusedAgent.
 * Drag-and-drop: dragging a pane header onto another leaf swaps their positions.
 */

import { useCallback, useState } from 'react'
import { AgentPane } from './AgentPane'
import type { TileNode } from '@/hooks/useTileLayout'
import type { AgentStream } from '@/stores/useTeamStore'

interface TileTreeProps {
  node: TileNode
  agentStreams: Record<string, AgentStream>
  leadName: string | null
  focusedAgent: string | null
  onFocus: (name: string) => void
  onClose: (name: string) => void
  onSwap: (nameA: string, nameB: string) => void
}

export function TileTree({
  node,
  agentStreams,
  leadName,
  focusedAgent,
  onFocus,
  onClose,
  onSwap,
}: TileTreeProps) {
  if (node.type === 'leaf') {
    return (
      <LeafPane
        agentName={node.agentName}
        agentStreams={agentStreams}
        leadName={leadName}
        focusedAgent={focusedAgent}
        onFocus={onFocus}
        onClose={onClose}
        onSwap={onSwap}
      />
    )
  }

  // Split node — lay out two children
  const isHorizontal = node.dir === 'h'
  const aSize = `${(node.ratio * 100).toFixed(1)}%`
  const bSize = `${((1 - node.ratio) * 100).toFixed(1)}%`

  const containerStyle: React.CSSProperties = isHorizontal
    ? { display: 'flex', flexDirection: 'row', width: '100%', height: '100%', gap: '6px' }
    : { display: 'flex', flexDirection: 'column', width: '100%', height: '100%', gap: '6px' }

  const aStyle: React.CSSProperties = isHorizontal
    ? { width: aSize, height: '100%', minWidth: 0 }
    : { width: '100%', height: aSize, minHeight: 0 }

  const bStyle: React.CSSProperties = isHorizontal
    ? { width: bSize, height: '100%', minWidth: 0 }
    : { width: '100%', height: bSize, minHeight: 0 }

  return (
    <div style={containerStyle}>
      <div style={aStyle}>
        <TileTree
          node={node.a}
          agentStreams={agentStreams}
          leadName={leadName}
          focusedAgent={focusedAgent}
          onFocus={onFocus}
          onClose={onClose}
          onSwap={onSwap}
        />
      </div>
      <div style={bStyle}>
        <TileTree
          node={node.b}
          agentStreams={agentStreams}
          leadName={leadName}
          focusedAgent={focusedAgent}
          onFocus={onFocus}
          onClose={onClose}
          onSwap={onSwap}
        />
      </div>
    </div>
  )
}

// ── LeafPane ──────────────────────────────────────────────────────────────────

interface LeafPaneProps {
  agentName: string
  agentStreams: Record<string, AgentStream>
  leadName: string | null
  focusedAgent: string | null
  onFocus: (name: string) => void
  onClose: (name: string) => void
  onSwap: (nameA: string, nameB: string) => void
}

function LeafPane({
  agentName,
  agentStreams,
  leadName,
  focusedAgent,
  onFocus,
  onClose,
  onSwap,
}: LeafPaneProps) {
  const stream = agentStreams[agentName]
  const isFocused = focusedAgent === agentName
  const isLead = agentName === leadName

  const [isDropTarget, setIsDropTarget] = useState(false)

  const handleFocus = useCallback(() => onFocus(agentName), [agentName, onFocus])
  const handleClose = useCallback(() => onClose(agentName), [agentName, onClose])

  // ── Drag handlers (source) ─────────────────────────────────────────────────

  const handleDragStart = useCallback((e: React.DragEvent) => {
    e.dataTransfer.setData('text/plain', agentName)
    e.dataTransfer.effectAllowed = 'move'
  }, [agentName])

  // ── Drop handlers (target) ─────────────────────────────────────────────────

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setIsDropTarget(true)
  }, [])

  const handleDragLeave = useCallback(() => setIsDropTarget(false), [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDropTarget(false)
    const dragged = e.dataTransfer.getData('text/plain')
    if (dragged && dragged !== agentName) {
      onSwap(dragged, agentName)
    }
  }, [agentName, onSwap])

  const handleDragEnd = useCallback(() => setIsDropTarget(false), [])

  if (!stream) return null

  return (
    <div
      className="h-full"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <AgentPane
        name={agentName}
        stream={stream}
        isLead={isLead}
        isFocused={isFocused}
        isDropTarget={isDropTarget}
        onClose={handleClose}
        onFocus={handleFocus}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      />
    </div>
  )
}
