/**
 * useTileLayout — binary tile tree for tmux-style agent pane splitting.
 *
 * Data model
 * ----------
 * A TileNode is either:
 *   - Leaf  { type:'leaf', agentName }        — a single agent pane
 *   - Split { type:'split', dir, a, b, ratio } — two child nodes split h or v
 *
 * The tree is stored in localStorage keyed by sessionId so the layout is
 * restored when the user navigates back to the same session.
 *
 * New session → reset to single lead-agent leaf (or null if no lead known yet).
 */

import { useState, useCallback, useEffect, useRef } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export type SplitDir = 'h' | 'v' // h = side-by-side (left|right), v = stacked (top|bottom)

export interface LeafNode {
  type: 'leaf'
  agentName: string
}

export interface SplitNode {
  type: 'split'
  dir: SplitDir
  /** ratio of first child (0–1) */
  ratio: number
  a: TileNode
  b: TileNode
}

export type TileNode = LeafNode | SplitNode

export interface TileLayout {
  root: TileNode | null
  focusedAgent: string | null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeLeaf(agentName: string): LeafNode {
  return { type: 'leaf', agentName }
}

/** Collect all agent names currently in the tree */
export function collectAgents(node: TileNode | null): string[] {
  if (!node) return []
  if (node.type === 'leaf') return [node.agentName]
  return [...collectAgents(node.a), ...collectAgents(node.b)]
}

/**
 * Insert a new leaf into the tree by splitting the focused agent's pane.
 * If the focused agent isn't found (or root is null), the new agent becomes the root.
 */
/**
 * side: 'after'  → new agent appears after  (right/below) the focused pane [default]
 *       'before' → new agent appears before (left/above)  the focused pane
 */
function insertAgent(
  root: TileNode | null,
  focusedAgent: string | null,
  newAgent: string,
  dir: SplitDir,
  side: 'before' | 'after' = 'after',
): TileNode {
  if (!root) return makeLeaf(newAgent)

  const newLeaf = makeLeaf(newAgent)

  function walk(node: TileNode): TileNode {
    if (node.type === 'leaf') {
      if (node.agentName === focusedAgent) {
        return {
          type: 'split',
          dir,
          ratio: 0.5,
          a: side === 'before' ? newLeaf : node,
          b: side === 'before' ? node    : newLeaf,
        }
      }
      return node
    }
    return { ...node, a: walk(node.a), b: walk(node.b) }
  }

  const updated = walk(root)
  if (updated === root) {
    // Focused agent not found — append after root
    return { type: 'split', dir, ratio: 0.5, a: root, b: newLeaf }
  }
  return updated
}

/**
 * Remove a leaf from the tree. When a split loses one child, it's replaced by
 * its remaining child (collapse the split).
 * Returns null if the tree becomes empty.
 */
function removeAgent(root: TileNode | null, agentName: string): TileNode | null {
  if (!root) return null
  if (root.type === 'leaf') {
    return root.agentName === agentName ? null : root
  }

  const newA = removeAgent(root.a, agentName)
  const newB = removeAgent(root.b, agentName)

  if (newA === null && newB === null) return null
  if (newA === null) return newB
  if (newB === null) return newA
  return { ...root, a: newA, b: newB }
}

/**
 * Replace all stale agent names (no longer in agentNames) with the lead agent.
 * If a stale agent is the only leaf, replace it with the lead.
 * If lead is not in agentNames, return current tree unchanged.
 */
function pruneStaleAgents(
  root: TileNode | null,
  validAgents: string[],
  leadName: string | null,
): TileNode | null {
  if (!root) return null
  const validSet = new Set(validAgents)

  function walk(node: TileNode): TileNode | null {
    if (node.type === 'leaf') {
      if (validSet.has(node.agentName)) return node
      // Stale — replace with lead if possible, otherwise remove
      if (leadName && validSet.has(leadName)) return makeLeaf(leadName)
      return null
    }
    const newA = walk(node.a)
    const newB = walk(node.b)
    if (!newA && !newB) return null
    if (!newA) return newB
    if (!newB) return newA
    return { ...node, a: newA, b: newB }
  }

  return walk(root)
}

/**
 * Swap two leaf nodes by name anywhere in the tree.
 * Used for drag-and-drop reordering.
 */
function swapLeaves(root: TileNode | null, nameA: string, nameB: string): TileNode | null {
  if (!root || nameA === nameB) return root

  function walk(node: TileNode): TileNode {
    if (node.type === 'leaf') {
      if (node.agentName === nameA) return makeLeaf(nameB)
      if (node.agentName === nameB) return makeLeaf(nameA)
      return node
    }
    return { ...node, a: walk(node.a), b: walk(node.b) }
  }

  return walk(root)
}

/** Find the agent name adjacent to the given one (for focus transfer after close) */
function findAdjacentAgent(root: TileNode | null, agentName: string): string | null {
  if (!root) return null
  const agents = collectAgents(root)
  const idx = agents.indexOf(agentName)
  if (idx === -1) return agents[0] ?? null
  if (idx > 0) return agents[idx - 1]
  if (idx < agents.length - 1) return agents[idx + 1]
  return null
}

// ── Persistence ───────────────────────────────────────────────────────────────

function storageKey(sessionId: string): string {
  return `oa-tile-layout-${sessionId}`
}

function saveLayout(sessionId: string, layout: TileLayout): void {
  try {
    localStorage.setItem(storageKey(sessionId), JSON.stringify(layout))
  } catch {
    // ignore quota errors
  }
}

function loadLayout(sessionId: string): TileLayout | null {
  try {
    const raw = localStorage.getItem(storageKey(sessionId))
    if (!raw) return null
    return JSON.parse(raw) as TileLayout
  } catch {
    return null
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

interface UseTileLayoutOptions {
  sessionId: string | null
  leadName: string | null
  agentNames: string[]
}

interface UseTileLayoutReturn {
  root: TileNode | null
  focusedAgent: string | null
  openAgents: string[]
  /** Open a minimized agent into a new split pane alongside the focused one */
  openAgent: (name: string, dir?: SplitDir) => void
  /** Split the pane of the given agent — new pane appears to the RIGHT */
  splitRight: (name: string, newAgent: string) => void
  /** Split the pane of the given agent — new pane appears BELOW */
  splitDown: (name: string, newAgent: string) => void
  /** Close/minimize an agent pane (remove from tile tree) */
  closeAgent: (name: string) => void
  /** Set focus to a given agent */
  focusAgent: (name: string) => void
  /** Swap two agent panes (drag-and-drop reorder) */
  swapAgents: (nameA: string, nameB: string) => void
  /** Update ratio of a split node (for resize handles) */
  setRatio: (path: string[], ratio: number) => void
}

export function useTileLayout({
  sessionId,
  leadName,
  agentNames,
}: UseTileLayoutOptions): UseTileLayoutReturn {
  const [layout, setLayout] = useState<TileLayout>({ root: null, focusedAgent: null })

  // Track the previous sessionId to detect session changes
  const prevSessionIdRef = useRef<string | null>(null)

  // ── Initialize / restore on session change ──────────────────────────────

  useEffect(() => {
    if (prevSessionIdRef.current === sessionId) return
    prevSessionIdRef.current = sessionId

    if (!sessionId) {
      // New session (no id yet): reset to null, will seed when leadName arrives
      setLayout({ root: null, focusedAgent: null }) // eslint-disable-line react-hooks/set-state-in-effect
      return
    }

    // Try to restore saved layout for this session
    const saved = loadLayout(sessionId)
    if (saved) {
      setLayout(saved)
    } else {
      // New session with id — seed with lead agent if known
      if (leadName) {
        setLayout({ root: makeLeaf(leadName), focusedAgent: leadName })
      } else {
        setLayout({ root: null, focusedAgent: null })
      }
    }
  }, [sessionId, leadName])

  // ── Seed lead agent when it becomes known (first load) ─────────────────

  useEffect(() => {
    if (!leadName) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLayout((prev) => {
      // Only seed if root is null (not yet seeded)
      if (prev.root !== null) return prev
      return { root: makeLeaf(leadName), focusedAgent: leadName }
    })
  }, [leadName])

  // ── Prune stale agents when agent roster changes ────────────────────────

  useEffect(() => {
    if (agentNames.length === 0) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLayout((prev) => {
      const pruned = pruneStaleAgents(prev.root, agentNames, leadName)
      const openSet = new Set(collectAgents(pruned))
      const focused =
        prev.focusedAgent && openSet.has(prev.focusedAgent)
          ? prev.focusedAgent
          : collectAgents(pruned)[0] ?? null
      return { root: pruned, focusedAgent: focused }
    })
  }, [agentNames, leadName])

  // ── Persist to localStorage whenever layout changes ─────────────────────

  useEffect(() => {
    if (sessionId) saveLayout(sessionId, layout)
  }, [sessionId, layout])

  // ── Actions ─────────────────────────────────────────────────────────────

  const openAgent = useCallback(
    (name: string, dir: SplitDir = 'h') => {
      setLayout((prev) => {
        // If already open, just focus it
        if (collectAgents(prev.root).includes(name)) {
          return { ...prev, focusedAgent: name }
        }
        const newRoot = insertAgent(prev.root, prev.focusedAgent, name, dir)
        return { root: newRoot, focusedAgent: name }
      })
    },
    [],
  )

  const splitRight = useCallback((name: string, newAgent: string) => {
    setLayout((prev) => {
      if (collectAgents(prev.root).includes(newAgent)) {
        return { ...prev, focusedAgent: newAgent }
      }
      const newRoot = insertAgent(prev.root, name, newAgent, 'h', 'after')
      return { root: newRoot, focusedAgent: newAgent }
    })
  }, [])

  const splitDown = useCallback((name: string, newAgent: string) => {
    setLayout((prev) => {
      if (collectAgents(prev.root).includes(newAgent)) {
        return { ...prev, focusedAgent: newAgent }
      }
      const newRoot = insertAgent(prev.root, name, newAgent, 'v', 'after')
      return { root: newRoot, focusedAgent: newAgent }
    })
  }, [])

  const closeAgent = useCallback((name: string) => {
    setLayout((prev) => {
      const adjacent = findAdjacentAgent(prev.root, name)
      const newRoot = removeAgent(prev.root, name)
      const newFocused =
        prev.focusedAgent === name
          ? adjacent && collectAgents(newRoot).includes(adjacent)
            ? adjacent
            : collectAgents(newRoot)[0] ?? null
          : prev.focusedAgent
      return { root: newRoot, focusedAgent: newFocused }
    })
  }, [])

  const focusAgent = useCallback((name: string) => {
    setLayout((prev) => ({ ...prev, focusedAgent: name }))
  }, [])

  const swapAgents = useCallback((nameA: string, nameB: string) => {
    setLayout((prev) => {
      const newRoot = swapLeaves(prev.root, nameA, nameB)
      return { ...prev, root: newRoot }
    })
  }, [])

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const setRatio = useCallback((_path: string[], _ratio: number) => {
    // Ratio adjustment via resize handles — no-op for now (future enhancement)
  }, [])

  // ── Derived ─────────────────────────────────────────────────────────────

  const openAgents = collectAgents(layout.root)

  return {
    root: layout.root,
    focusedAgent: layout.focusedAgent,
    openAgents,
    openAgent,
    splitRight,
    splitDown,
    closeAgent,
    focusAgent,
    swapAgents,
    setRatio,
  }
}
