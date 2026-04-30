/**
 * usePanelDnD — drag-and-drop reorder state for the split-view grid.
 *
 * Owns three pieces of state:
 *   - ``panelOrder``    — the mutable order shown in ``SplitGrid``
 *   - ``draggingIdx``   — index of the pane currently being dragged
 *   - ``dropTargetIdx`` — index the drag is hovering over
 *
 * `panelOrder` is initialized lazily from `agentNames` (with the lead
 * floated to the front) the first time agents arrive — subsequent
 * mutations preserve user reorderings even as `agentNames` changes,
 * because the effect only seeds when the order is empty.
 *
 * Returns the four DOM event handlers (``onDragStart`` / ``onDragOver``
 * / ``onDrop`` / ``onDragEnd``) plus the live state, ready to be passed
 * through to ``SplitGrid`` as props.
 */
import { useCallback, useEffect, useState } from 'react'

interface UsePanelDnDArgs {
  agentNames: string[]
  leadName: string | null
}

export interface PanelDnD {
  panelOrder: string[]
  draggingIdx: number | null
  dropTargetIdx: number | null
  onDragStart: (idx: number) => void
  onDragOver: (e: React.DragEvent<HTMLDivElement>, idx: number) => void
  onDrop: (idx: number) => void
  onDragEnd: () => void
}

export function usePanelDnD({ agentNames, leadName }: UsePanelDnDArgs): PanelDnD {
  const [panelOrder, setPanelOrder] = useState<string[]>([])
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null)
  const [dropTargetIdx, setDropTargetIdx] = useState<number | null>(null)

  // Seed the order when agents first arrive, lead floated to front.
  // Once seeded, user reorderings via drag are preserved; subsequent
  // changes to ``agentNames`` (e.g. an agent joining mid-session) do
  // *not* re-seed because the guard checks for an empty ``panelOrder``.
  // The set-state-in-effect lint is intentional here: we need to
  // observe an external prop arriving before we can compute the seed,
  // and the alternative (a ref-flag pattern) is strictly more code for
  // the same observable behaviour.
  useEffect(() => {
    if (agentNames.length > 0 && panelOrder.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setPanelOrder(
        leadName
          ? [leadName, ...agentNames.filter((n) => n !== leadName)]
          : [...agentNames]
      )
    }
  }, [agentNames, leadName, panelOrder.length])

  const onDragStart = useCallback((idx: number) => setDraggingIdx(idx), [])
  const onDragOver = useCallback(
    (e: React.DragEvent<HTMLDivElement>, idx: number) => {
      e.preventDefault()
      setDropTargetIdx(idx)
    },
    [],
  )
  const onDrop = useCallback(
    (targetIdx: number) => {
      if (draggingIdx === null || draggingIdx === targetIdx) {
        setDraggingIdx(null)
        setDropTargetIdx(null)
        return
      }
      setPanelOrder((prev) => {
        const next = [...prev]
        const [moved] = next.splice(draggingIdx, 1)
        next.splice(targetIdx, 0, moved)
        return next
      })
      setDraggingIdx(null)
      setDropTargetIdx(null)
    },
    [draggingIdx],
  )
  const onDragEnd = useCallback(() => {
    setDraggingIdx(null)
    setDropTargetIdx(null)
  }, [])

  return {
    panelOrder,
    draggingIdx,
    dropTargetIdx,
    onDragStart,
    onDragOver,
    onDrop,
    onDragEnd,
  }
}
