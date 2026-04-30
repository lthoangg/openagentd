/**
 * Tests for useTileLayout hook and the exported collectAgents helper.
 *
 * Strategy:
 * - collectAgents is a pure exported function → tested directly.
 * - useTileLayout actions (openAgent, splitRight, splitDown, closeAgent,
 *   swapAgents, focusAgent) are tested via renderHook from @testing-library/react.
 * - localStorage is stubbed with a simple in-memory map so persistence
 *   does not leak between tests.
 *
 * KEY FIX: All agentNames arrays are declared as `const` OUTSIDE the renderHook
 * callback so the reference is stable across renders. Inline array literals like
 * `agentNames: ["lead", "worker"]` inside the callback create a new reference on
 * every render, which triggers the pruneStaleAgents useEffect → setLayout →
 * re-render → new array → infinite loop.
 */

import { describe, it, expect, beforeEach, afterEach } from "bun:test"
import { renderHook, act } from "@testing-library/react"
import { collectAgents, useTileLayout } from "@/hooks/useTileLayout"
import type { TileNode, LeafNode, SplitNode } from "@/hooks/useTileLayout"

// ── localStorage stub ─────────────────────────────────────────────────────────

const store: Record<string, string> = {}
const localStorageStub = {
  getItem: (k: string) => store[k] ?? null,
  setItem: (k: string, v: string) => { store[k] = v },
  removeItem: (k: string) => { delete store[k] },
  clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
}

beforeEach(() => {
  localStorageStub.clear()
  Object.defineProperty(globalThis, "localStorage", {
    value: localStorageStub,
    writable: true,
    configurable: true,
  })
})

afterEach(() => {
  localStorageStub.clear()
})

// ── helpers ───────────────────────────────────────────────────────────────────

function leaf(name: string): LeafNode {
  return { type: "leaf", agentName: name }
}

function split(a: TileNode, b: TileNode, dir: "h" | "v" = "h"): SplitNode {
  return { type: "split", dir, ratio: 0.5, a, b }
}

// ── collectAgents ─────────────────────────────────────────────────────────────

describe("collectAgents", () => {
  it("returns [] for null", () => {
    expect(collectAgents(null)).toEqual([])
  })

  it("returns [name] for a single leaf", () => {
    expect(collectAgents(leaf("alpha"))).toEqual(["alpha"])
  })

  it("returns both names for a split of two leaves", () => {
    const node = split(leaf("alpha"), leaf("beta"))
    expect(collectAgents(node)).toEqual(["alpha", "beta"])
  })

  it("returns names left-to-right depth-first for a nested split", () => {
    // (alpha | (beta | gamma))
    const node = split(leaf("alpha"), split(leaf("beta"), leaf("gamma")))
    expect(collectAgents(node)).toEqual(["alpha", "beta", "gamma"])
  })

  it("handles three-level nesting", () => {
    // ((alpha | beta) | (gamma | delta))
    const node = split(
      split(leaf("alpha"), leaf("beta")),
      split(leaf("gamma"), leaf("delta")),
    )
    expect(collectAgents(node)).toEqual(["alpha", "beta", "gamma", "delta"])
  })

  it("handles a deeply nested right-skewed tree", () => {
    // (a | (b | (c | d)))
    const node = split(
      leaf("a"),
      split(leaf("b"), split(leaf("c"), leaf("d"))),
    )
    expect(collectAgents(node)).toEqual(["a", "b", "c", "d"])
  })

  it("handles a deeply nested left-skewed tree", () => {
    // (((a | b) | c) | d)
    const node = split(
      split(split(leaf("a"), leaf("b")), leaf("c")),
      leaf("d"),
    )
    expect(collectAgents(node)).toEqual(["a", "b", "c", "d"])
  })
})

// ── useTileLayout — initial state ─────────────────────────────────────────────

describe("useTileLayout — initial state", () => {
  it("starts with null root when no sessionId and no leadName", () => {
    // STABLE: empty array declared outside callback
    const agentNames: string[] = []
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: null, agentNames })
    )
    expect(result.current.root).toBeNull()
    expect(result.current.focusedAgent).toBeNull()
    expect(result.current.openAgents).toEqual([])
  })

  it("seeds lead agent leaf when leadName is provided with no sessionId", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )
    expect(result.current.root).not.toBeNull()
    expect(result.current.openAgents).toEqual(["lead"])
    expect(result.current.focusedAgent).toBe("lead")
  })

  it("restores saved layout from localStorage for a known sessionId", () => {
    const saved = {
      root: leaf("lead"),
      focusedAgent: "lead",
    }
    localStorageStub.setItem("oa-tile-layout-sess-1", JSON.stringify(saved))

    // STABLE: array declared outside callback
    const agentNames = ["lead"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: "sess-1", leadName: "lead", agentNames })
    )
    expect(result.current.openAgents).toEqual(["lead"])
    expect(result.current.focusedAgent).toBe("lead")
  })

  it("seeds lead-only layout for new sessionId with no saved layout", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: "new-sess", leadName: "lead", agentNames })
    )
    expect(result.current.openAgents).toEqual(["lead"])
    expect(result.current.focusedAgent).toBe("lead")
  })
})

// ── useTileLayout — openAgent ─────────────────────────────────────────────────

describe("useTileLayout — openAgent", () => {
  it("opens a minimized agent as a new split alongside the focused pane", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.openAgent("worker") })

    expect(result.current.openAgents).toContain("lead")
    expect(result.current.openAgents).toContain("worker")
    expect(result.current.focusedAgent).toBe("worker")
  })

  it("just focuses an agent that is already open (no duplicate pane)", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.openAgent("worker") })
    const countAfterFirst = result.current.openAgents.length

    act(() => { result.current.focusAgent("lead") })
    act(() => { result.current.openAgent("worker") })

    // Length unchanged — no duplicate inserted
    expect(result.current.openAgents.length).toBe(countAfterFirst)
    expect(result.current.focusedAgent).toBe("worker")
  })
})

// ── useTileLayout — splitRight ────────────────────────────────────────────────

describe("useTileLayout — splitRight", () => {
  it("inserts new agent to the right of the focused pane (h split, side:after)", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })

    const agents = result.current.openAgents
    expect(agents).toEqual(["lead", "worker"])  // lead first (a), worker second (b)
    expect(result.current.focusedAgent).toBe("worker")
  })

  it("focuses agent that is already open instead of inserting duplicate", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    act(() => { result.current.focusAgent("lead") })
    act(() => { result.current.splitRight("lead", "worker") })

    expect(result.current.openAgents.length).toBe(2)
    expect(result.current.focusedAgent).toBe("worker")
  })
})

// ── useTileLayout — splitDown ─────────────────────────────────────────────────

describe("useTileLayout — splitDown", () => {
  it("inserts new agent below the focused pane (v split)", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitDown("lead", "worker") })

    expect(result.current.openAgents).toContain("lead")
    expect(result.current.openAgents).toContain("worker")

    // Root should be a v-split
    const root = result.current.root
    expect(root?.type).toBe("split")
    if (root?.type === "split") {
      expect(root.dir).toBe("v")
    }
  })

  it("focuses agent that is already open instead of inserting duplicate", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitDown("lead", "worker") })
    act(() => { result.current.focusAgent("lead") })
    act(() => { result.current.splitDown("lead", "worker") })

    expect(result.current.openAgents.length).toBe(2)
    expect(result.current.focusedAgent).toBe("worker")
  })
})

// ── useTileLayout — closeAgent ────────────────────────────────────────────────

describe("useTileLayout — closeAgent", () => {
  it("removes an agent pane from the tree", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    expect(result.current.openAgents).toContain("worker")

    act(() => { result.current.closeAgent("worker") })
    expect(result.current.openAgents).not.toContain("worker")
    expect(result.current.openAgents).toContain("lead")
  })

  it("transfers focus to adjacent agent when focused pane is closed", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    expect(result.current.focusedAgent).toBe("worker")

    act(() => { result.current.closeAgent("worker") })
    expect(result.current.focusedAgent).toBe("lead")
  })

  it("returns null root when the only pane is closed", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )
    expect(result.current.openAgents).toEqual(["lead"])

    act(() => { result.current.closeAgent("lead") })
    expect(result.current.root).toBeNull()
    expect(result.current.focusedAgent).toBeNull()
  })

  it("collapses parent split when one child is removed", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    expect(result.current.root?.type).toBe("split")

    act(() => { result.current.closeAgent("worker") })
    // Root should now be a leaf (split collapsed)
    expect(result.current.root?.type).toBe("leaf")
  })
})

// ── useTileLayout — focusAgent ────────────────────────────────────────────────

describe("useTileLayout — focusAgent", () => {
  it("sets focusedAgent without changing the tree", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    act(() => { result.current.focusAgent("lead") })

    expect(result.current.focusedAgent).toBe("lead")
    expect(result.current.openAgents).toEqual(["lead", "worker"])  // tree unchanged
  })

  it("can cycle focus between multiple open panes", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker1", "worker2"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker1") })
    act(() => { result.current.splitRight("worker1", "worker2") })

    act(() => { result.current.focusAgent("lead") })
    expect(result.current.focusedAgent).toBe("lead")

    act(() => { result.current.focusAgent("worker2") })
    expect(result.current.focusedAgent).toBe("worker2")

    act(() => { result.current.focusAgent("worker1") })
    expect(result.current.focusedAgent).toBe("worker1")
  })
})

// ── useTileLayout — swapAgents ────────────────────────────────────────────────

describe("useTileLayout — swapAgents", () => {
  it("swaps two open agent panes in the tree", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    expect(result.current.openAgents).toEqual(["lead", "worker"])

    act(() => { result.current.swapAgents("lead", "worker") })
    expect(result.current.openAgents).toEqual(["worker", "lead"])  // positions swapped
  })

  it("is a no-op when swapping an agent with itself", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    const before = result.current.openAgents.slice()

    act(() => { result.current.swapAgents("lead", "lead") })
    expect(result.current.openAgents).toEqual(before)
  })

  it("swapping is reversible — double swap restores original order", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    const original = result.current.openAgents.slice()

    act(() => { result.current.swapAgents("lead", "worker") })
    act(() => { result.current.swapAgents("lead", "worker") })

    expect(result.current.openAgents).toEqual(original)
  })
})

// ── useTileLayout — three-pane tree ──────────────────────────────────────────

describe("useTileLayout — three-pane layouts", () => {
  it("can split twice to get three open panes", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker1", "worker2"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker1") })
    act(() => { result.current.splitRight("worker1", "worker2") })

    expect(result.current.openAgents).toHaveLength(3)
    expect(result.current.openAgents).toContain("lead")
    expect(result.current.openAgents).toContain("worker1")
    expect(result.current.openAgents).toContain("worker2")
  })

  it("closing the middle pane leaves the other two", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker1", "worker2"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker1") })
    act(() => { result.current.splitRight("worker1", "worker2") })
    act(() => { result.current.closeAgent("worker1") })

    expect(result.current.openAgents).not.toContain("worker1")
    expect(result.current.openAgents).toContain("lead")
    expect(result.current.openAgents).toContain("worker2")
  })

  it("can mix splitRight and splitDown in a three-pane layout", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker1", "worker2"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker1") })
    act(() => { result.current.splitDown("worker1", "worker2") })

    expect(result.current.openAgents).toHaveLength(3)
    expect(result.current.openAgents).toContain("lead")
    expect(result.current.openAgents).toContain("worker1")
    expect(result.current.openAgents).toContain("worker2")
  })
})

// ── useTileLayout — localStorage persistence ──────────────────────────────────

describe("useTileLayout — persistence", () => {
  it("saves layout to localStorage when a pane is opened", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: "sess-42", leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })

    const raw = localStorageStub.getItem("oa-tile-layout-sess-42")
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(collectAgents(parsed.root)).toContain("worker")
  })

  it("does not write to localStorage when sessionId is null", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: null, leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })

    // No key should have been written
    const keys = Object.keys(store)
    expect(keys.filter((k) => k.startsWith("oa-tile-layout-"))).toHaveLength(0)
  })

  it("persists focusedAgent to localStorage", () => {
    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: "sess-focus", leadName: "lead", agentNames })
    )

    act(() => { result.current.splitRight("lead", "worker") })
    act(() => { result.current.focusAgent("lead") })

    const raw = localStorageStub.getItem("oa-tile-layout-sess-focus")
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.focusedAgent).toBe("lead")
  })

  it("restores both root and focusedAgent from localStorage", () => {
    const saved = {
      root: split(leaf("lead"), leaf("worker")),
      focusedAgent: "worker",
    }
    localStorageStub.setItem("oa-tile-layout-sess-restore", JSON.stringify(saved))

    // STABLE: array declared outside callback
    const agentNames = ["lead", "worker"]
    const { result } = renderHook(() =>
      useTileLayout({ sessionId: "sess-restore", leadName: "lead", agentNames })
    )

    expect(result.current.openAgents).toEqual(["lead", "worker"])
    expect(result.current.focusedAgent).toBe("worker")
  })
})
