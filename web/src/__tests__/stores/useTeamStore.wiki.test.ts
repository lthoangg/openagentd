import { describe, it, expect, beforeEach } from "bun:test"
import { useTeamStore } from "@/stores/useTeamStore"

/**
 * Wiki invalidation is driven by tool_end events whose tool is a
 * mutating filesystem op (`write`, `edit`, `rm`) AND whose `path` argument
 * targets the `wiki/` tree.
 *
 * Arguments are captured from the preceding `tool_start` event and stored
 * on the tool block.  The `tool_end` handler looks up the block by
 * `tool_call_id` and inspects `toolArgs`, then pushes a domain event
 * onto ``cacheInvalidations``.  The React-side bridge in
 * ``routes/cockpit.tsx`` translates queue events into TanStack Query
 * invalidations; those tests live in ``cache-invalidation-bridge.test.ts``.
 *
 * These tests assert on the queue contents directly, so the store
 * stays decoupled from TanStack Query.
 */

function primeBlock(
  agent: string,
  toolName: string,
  toolCallId: string,
  args: Record<string, unknown>,
) {
  const state = useTeamStore.getState()
  state._handleSSEEvent("tool_call", { name: toolName, agent, tool_call_id: toolCallId })
  state._handleSSEEvent("tool_start", {
    name: toolName,
    agent,
    tool_call_id: toolCallId,
    arguments: JSON.stringify(args),
  })
}

describe("useTeamStore — wiki invalidation", () => {
  beforeEach(() => {
    useTeamStore.setState({
      agentStreams: {},
      activeAgent: null,
      leadName: null,
      agentNames: [],
      sidebarOpen: false,
      sessionId: null,
      sessionTitle: null,
      isTeamWorking: false,
      isConnected: false,
      error: null,
      _pendingMessages: [],
      _sessionGeneration: 0,
      cacheInvalidations: [],
    })
  })

  it("emits wiki invalidation when `write` targets wiki/system/USER.md", () => {
    primeBlock("claude", "write", "tc-1", { path: "wiki/system/USER.md", content: "..." })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "write",
      agent: "claude",
      tool_call_id: "tc-1",
      result: "Written 12 bytes to wiki/system/USER.md",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([{ kind: "wiki" }])
  })

  it("emits wiki invalidation when `edit` targets wiki/topics/*.md", () => {
    primeBlock("claude", "edit", "tc-2", {
      path: "wiki/topics/auth.md",
      old_string: "a",
      new_string: "b",
    })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "edit",
      agent: "claude",
      tool_call_id: "tc-2",
      result: "Edit applied successfully to wiki/topics/auth.md",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([{ kind: "wiki" }])
  })

  it("emits wiki invalidation when `rm` targets wiki/notes/*.md", () => {
    primeBlock("claude", "rm", "tc-3", { path: "wiki/notes/2026-04-17-abc.md" })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "rm",
      agent: "claude",
      tool_call_id: "tc-3",
      result: "Removed file: wiki/notes/2026-04-17-abc.md",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([{ kind: "wiki" }])
  })

  it("emits workspace_files (not wiki) when `write` targets workspace paths and a session is active", () => {
    useTeamStore.setState({ sessionId: "sess-abc" })
    primeBlock("claude", "write", "tc-4", { path: "notes/scratch.md", content: "..." })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "write",
      agent: "claude",
      tool_call_id: "tc-4",
      result: "Written 12 bytes to notes/scratch.md",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([
      { kind: "workspace_files", sessionId: "sess-abc" },
    ])
  })

  it("emits NOTHING when `write` targets workspace paths but no session is active", () => {
    primeBlock("claude", "write", "tc-4b", { path: "notes/scratch.md", content: "..." })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "write",
      agent: "claude",
      tool_call_id: "tc-4b",
      result: "Written 12 bytes to notes/scratch.md",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([])
  })

  it("emits NOTHING when `read` targets wiki/ (read is not mutating)", () => {
    primeBlock("claude", "read", "tc-5", { path: "wiki/system/USER.md" })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "read",
      agent: "claude",
      tool_call_id: "tc-5",
      result: "file contents",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([])
  })

  it("emits NOTHING when `grep` scans wiki/", () => {
    primeBlock("claude", "grep", "tc-6", { pattern: "foo", directory: "wiki" })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "grep",
      agent: "claude",
      tool_call_id: "tc-6",
      result: "no matches",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([])
  })

  it("emits NOTHING when a non-filesystem tool runs", () => {
    primeBlock("claude", "web_search", "tc-7", { query: "openagentd wiki" })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "web_search",
      agent: "claude",
      tool_call_id: "tc-7",
      result: "search results",
    })
    expect(useTeamStore.getState().cacheInvalidations).toEqual([])
  })

  it("still updates the tool block state on tool_end even when emitting an invalidation", () => {
    primeBlock("claude", "write", "tc-8", { path: "wiki/topics/x.md", content: "y" })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "write",
      agent: "claude",
      tool_call_id: "tc-8",
      result: "Written",
    })

    const agentStream = useTeamStore.getState().agentStreams["claude"]
    expect(agentStream).toBeDefined()
    const block = agentStream.currentBlocks.find((b) => b.toolCallId === "tc-8")
    expect(block).toBeDefined()
    expect(block!.toolDone).toBe(true)
    expect(block!.toolResult).toBe("Written")
    expect(useTeamStore.getState().cacheInvalidations).toEqual([{ kind: "wiki" }])
  })

  it("queues one event per tool_end across rapid-fire wiki mutations", () => {
    const state = useTeamStore.getState()
    for (let i = 0; i < 4; i++) {
      const agent = i % 2 === 0 ? "claude" : "gpt4"
      const tcid = `tc-rapid-${i}`
      primeBlock(agent, "write", tcid, {
        path: `wiki/notes/2026-04-${10 + i}-abc.md`,
        content: "x",
      })
      state._handleSSEEvent("tool_end", {
        name: "write",
        agent,
        tool_call_id: tcid,
        result: "Written",
      })
    }
    expect(useTeamStore.getState().cacheInvalidations).toEqual([
      { kind: "wiki" },
      { kind: "wiki" },
      { kind: "wiki" },
      { kind: "wiki" },
    ])
  })

  it("_drainCacheInvalidations returns and clears the queue atomically", () => {
    primeBlock("claude", "write", "tc-drain", { path: "wiki/topics/x.md", content: "y" })
    useTeamStore.getState()._handleSSEEvent("tool_end", {
      name: "write",
      agent: "claude",
      tool_call_id: "tc-drain",
      result: "Written",
    })
    expect(useTeamStore.getState().cacheInvalidations).toHaveLength(1)

    const drained = useTeamStore.getState()._drainCacheInvalidations()
    expect(drained).toEqual([{ kind: "wiki" }])
    expect(useTeamStore.getState().cacheInvalidations).toEqual([])

    // A second drain on an empty queue is a no-op.
    expect(useTeamStore.getState()._drainCacheInvalidations()).toEqual([])
  })
})
