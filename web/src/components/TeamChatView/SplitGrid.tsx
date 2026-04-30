/**
 * SplitGrid — fixed n-pane grid layout for the `split` view mode.
 *
 * All panes (lead included) are treated equally. The "big" slot in each
 * layout goes to ``panelOrder[0]``; the rest fill remaining slots in
 * order. The lead badge still follows the store's designated lead agent
 * wherever it happens to sit. Layouts are hand-tuned for n = 1..6:
 *
 *   1 → fullscreen
 *   2 → side-by-side
 *   3 → big left, two stacked right
 *   4 → 2×2
 *   5 → big left + 2×2 right
 *   6 → 3×2
 *
 * Drag-and-drop reorders the underlying ``panelOrder`` array; visual
 * feedback (dragging / drop-target rings) is delegated to ``AgentPane``.
 */
import type React from 'react'
import { AgentPane } from '../AgentPane'
import type { AgentStream } from '@/stores/useTeamStore'

interface SplitGridProps {
  panelOrder: string[]
  leadName: string | null
  agentStreams: Record<string, AgentStream>
  draggingIdx: number | null
  dropTargetIdx: number | null
  onDragStart: (idx: number) => void
  onDragOver: (e: React.DragEvent<HTMLDivElement>, idx: number) => void
  onDrop: (idx: number) => void
  onDragEnd: () => void
}

export function SplitGrid({
  panelOrder, leadName, agentStreams,
  draggingIdx, dropTargetIdx,
  onDragStart, onDragOver, onDrop, onDragEnd,
}: SplitGridProps) {
  const n = Math.min(panelOrder.length, 6)
  if (n === 0) return null

  const renderPanel = (idx: number, style: React.CSSProperties) => {
    const name = panelOrder[idx]
    if (!name) return null
    const stream = agentStreams[name]
    if (!stream) return null
    return (
      <div key={name} style={style} className="min-h-0">
        <AgentPane
          name={name}
          stream={stream}
          isLead={name === leadName}
          isDragging={draggingIdx === idx}
          isDropTarget={dropTargetIdx === idx && draggingIdx !== idx}
          onDragStart={() => onDragStart(idx)}
          onDragOver={(e) => onDragOver(e, idx)}
          onDrop={() => onDrop(idx)}
          onDragEnd={onDragEnd}
        />
      </div>
    )
  }

  if (n === 1) return <div className="h-full">{renderPanel(0, {})}</div>
  if (n === 2) return (
    <div className="grid h-full gap-3" style={{ gridTemplateColumns: '1fr 1fr' }}>
      {renderPanel(0, { gridColumn: 1, gridRow: 1 })}
      {renderPanel(1, { gridColumn: 2, gridRow: 1 })}
    </div>
  )
  if (n === 3) return (
    <div className="grid h-full gap-3" style={{ gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' }}>
      {renderPanel(0, { gridColumn: 1, gridRow: '1 / 3' })}
      {renderPanel(1, { gridColumn: 2, gridRow: 1 })}
      {renderPanel(2, { gridColumn: 2, gridRow: 2 })}
    </div>
  )
  if (n === 4) return (
    <div className="grid h-full gap-3" style={{ gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr' }}>
      {renderPanel(0, { gridColumn: 1, gridRow: 1 })}
      {renderPanel(1, { gridColumn: 2, gridRow: 1 })}
      {renderPanel(2, { gridColumn: 1, gridRow: 2 })}
      {renderPanel(3, { gridColumn: 2, gridRow: 2 })}
    </div>
  )
  if (n === 5) return (
    <div className="grid h-full gap-3" style={{ gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: '1fr 1fr' }}>
      {renderPanel(0, { gridColumn: 1, gridRow: '1 / 3' })}
      {renderPanel(1, { gridColumn: 2, gridRow: 1 })}
      {renderPanel(2, { gridColumn: 2, gridRow: 2 })}
      {renderPanel(3, { gridColumn: 3, gridRow: 1 })}
      {renderPanel(4, { gridColumn: 3, gridRow: 2 })}
    </div>
  )
  return (
    <div className="grid h-full gap-3" style={{ gridTemplateColumns: '1fr 1fr 1fr', gridTemplateRows: '1fr 1fr' }}>
      {renderPanel(0, { gridColumn: 1, gridRow: 1 })}
      {renderPanel(1, { gridColumn: 2, gridRow: 1 })}
      {renderPanel(2, { gridColumn: 3, gridRow: 1 })}
      {renderPanel(3, { gridColumn: 1, gridRow: 2 })}
      {renderPanel(4, { gridColumn: 2, gridRow: 2 })}
      {renderPanel(5, { gridColumn: 3, gridRow: 2 })}
    </div>
  )
}
