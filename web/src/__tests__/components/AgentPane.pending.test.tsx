import { describe, it, expect, afterEach, mock } from "bun:test"
import { render, screen, cleanup } from "@testing-library/react"
import { AgentPane } from "@/components/AgentPane"
import type { AgentStream } from "@/stores/useTeamStore"
import type { ContentBlock } from "@/api/types"

afterEach(cleanup)

// Mock lucide-react icons to avoid SVG issues in Happy DOM
mock.module("lucide-react", () => new Proxy({}, { get: () => () => null }))

// ── helpers ──────────────────────────────────────────────────────────────────

function makeTextBlock(id: string, content: string): ContentBlock {
  return { id, type: "text", content }
}

function makeUserBlock(id: string, content: string): ContentBlock {
  return { id, type: "user", content }
}

function makeThinkingBlock(id: string, content: string): ContentBlock {
  return { id, type: "thinking", content }
}

function makeStream(overrides: Partial<AgentStream> = {}): AgentStream {
  return {
    blocks: [],
    currentBlocks: [],
    currentText: "",
    currentThinking: "",
    status: "available",
    usage: {
      promptTokens: 0,
      completionTokens: 0,
      totalTokens: 0,
      cachedTokens: 0,
    },
    _completionBase: 0,
    model: null,
    lastError: null,
    ...overrides,
  }
}

function renderPanel(stream: AgentStream) {
  return render(<AgentPane name="researcher" stream={stream} isLead={false} />)
}

// ── tests ────────────────────────────────────────────────────────────────────

describe("AgentPane — pending dots indicator", () => {
  it("shows 3 bounce dots when status=available but currentBlocks has a user block (isPending)", () => {
    const stream = makeStream({
      status: "available",
      currentBlocks: [makeUserBlock("u1", "Hello")],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(3)
  })

  it("shows 3 bounce dots when status=working and currentBlocks has only user blocks", () => {
    const stream = makeStream({
      status: "working",
      currentBlocks: [makeUserBlock("u1", "Hello")],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(3)
  })

  it("does not show bounce dots when status=available and currentBlocks is empty", () => {
    const stream = makeStream({
      status: "available",
      currentBlocks: [],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })

  it("does not show bounce dots when status=working and currentBlocks has a text block", () => {
    const stream = makeStream({
      status: "working",
      currentBlocks: [makeTextBlock("b1", "Response text")],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })

  it("does not show bounce dots when status=working with mixed blocks including text", () => {
    const stream = makeStream({
      status: "working",
      currentBlocks: [
        makeUserBlock("u1", "Hello"),
        makeTextBlock("b1", "Response"),
      ],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })

  it("does not show bounce dots when status=working with thinking block only", () => {
    const stream = makeStream({
      status: "working",
      currentBlocks: [makeThinkingBlock("t1", "Thinking...")],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })

  it("does not show bounce dots when status=working with user and thinking blocks", () => {
    const stream = makeStream({
      status: "working",
      currentBlocks: [
        makeUserBlock("u1", "Hello"),
        makeThinkingBlock("t1", "Thinking..."),
      ],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })

  it("does not show 'Working…' text anywhere", () => {
    const stream = makeStream({
      status: "working",
      currentBlocks: [makeUserBlock("u1", "Hello")],
    })
    renderPanel(stream)
    const workingText = screen.queryByText(/Working/)
    expect(workingText).toBeNull()
  })

  it("shows 'Waiting…' text when available with no blocks", () => {
    const stream = makeStream({
      status: "available",
      currentBlocks: [],
    })
    renderPanel(stream)
    const idleText = screen.getByText("Waiting…")
    expect(idleText).toBeTruthy()
  })

  it("shows agent name in header", () => {
    const stream = makeStream()
    renderPanel(stream)
    const nameEl = screen.getByText("researcher")
    expect(nameEl).toBeTruthy()
  })

  it("does not show bounce dots when status=error", () => {
    const stream = makeStream({
      status: "error",
      currentBlocks: [makeUserBlock("u1", "Hello")],
      lastError: "Something went wrong",
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })

  it("shows error message when status=error", () => {
    const stream = makeStream({
      status: "error",
      currentBlocks: [],
      lastError: "API timeout",
    })
    const { container } = renderPanel(stream)
    // Error message appears in the error box at the bottom
    const errorBox = container.querySelector("div[class*='bg-(--color-error-subtle)']")
    expect(errorBox).toBeTruthy()
    expect(errorBox?.textContent).toContain("API timeout")
  })

  it("shows bounce dots when status=available with user block even if there are finalized blocks", () => {
    const stream = makeStream({
      status: "available",
      blocks: [makeTextBlock("b1", "Previous response")],
      currentBlocks: [makeUserBlock("u1", "New question")],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(3)
  })

  it("does not show bounce dots when status=working with only finalized blocks and no currentBlocks", () => {
    // Regression: `[].every()` returns true, so the working branch of the
    // dots condition must require a non-empty currentBlocks list. Without
    // that guard the dots stuck around after `done` flushed the buffer
    // whenever a stale `working` status briefly survived.
    const stream = makeStream({
      status: "working",
      blocks: [makeTextBlock("b1", "Previous response")],
      currentBlocks: [],
    })
    const { container } = renderPanel(stream)
    const dots = container.querySelectorAll(".animate-bounce")
    expect(dots.length).toBe(0)
  })
})
