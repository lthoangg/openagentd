import { describe, it, expect, afterEach, mock } from "bun:test"
import "@testing-library/jest-dom"
import { render, screen, cleanup } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AgentView } from "@/components/AgentView"
import { AgentPane } from "@/components/AgentPane"
import type { ContentBlock } from "@/api/types"
import type { AgentStream } from "@/stores/useTeamStore/types"

// Mock Zustand store — provide a full mock so the module stays usable by
// other test files that share this Bun worker process.
const _mockState = {
  sessionId: "test-session-123",
  agentStreams: {},
  activeAgent: null,
  leadName: null,
  agentNames: [],
  sidebarOpen: false,
  isTeamWorking: false,
  isConnected: false,
  error: null,
  _pendingMessages: [] as { id: string; content: string }[],
  _sessionGeneration: 0,
  sessionTitle: null,
  cacheInvalidations: [],
}

const _mockUseTeamStore = Object.assign(
  (selector: (state: typeof _mockState) => unknown) => selector(_mockState),
  {
    getState: () => _mockState,
    setState: (partial: Partial<typeof _mockState>) => Object.assign(_mockState, partial),
    subscribe: () => () => {},
    destroy: () => {},
  }
)

mock.module("@/stores/useTeamStore", () => ({
  useTeamStore: _mockUseTeamStore,
}))

// Mock child components that are not under test
mock.module("@/components/Thinking", () => ({
  Thinking: ({ content }: { content: string }) => <div data-testid="thinking">{content}</div>,
}))

mock.module("@/components/ToolCall", () => ({
  ToolCall: ({ name }: { name: string }) => <div data-testid="tool-call">{name}</div>,
}))

mock.module("@/components/InboxBubble", () => ({
  InboxBubble: ({ content }: { content: string }) => <div data-testid="inbox-bubble">{content}</div>,
}))

mock.module("@/components/ImageAttachment", () => ({
  ImageAttachment: ({ alt }: { alt: string }) => <div data-testid="image-attachment">{alt}</div>,
}))

mock.module("@/components/FileCard", () => ({
  FileCard: ({ name }: { name: string }) => <div data-testid="file-card">{name}</div>,
}))

mock.module("@/components/AssistantTurnFooter", () => ({
  AssistantTurn: ({ blocks, renderBlock }: { blocks: ContentBlock[]; renderBlock: (args: { block: ContentBlock; isStreaming: boolean; isLast: boolean }) => import("react").ReactNode }) => (
    <div data-testid="assistant-turn">
      {blocks.map((block, idx: number) => (
        <div key={idx}>{renderBlock({ block, isStreaming: false, isLast: false })}</div>
      ))}
    </div>
  ),
}))

mock.module("@/components/motion", () => ({
  StreamingCursor: () => <div data-testid="streaming-cursor" />,
}))

mock.module("@/utils/markdown", () => ({
  MarkdownBlock: ({ content }: { content: string }) => <div data-testid="markdown-block">{content}</div>,
}))

afterEach(cleanup)

// ─────────────────────────────────────────────────────────────────────────────
// AgentView UserBubble Tests
// ─────────────────────────────────────────────────────────────────────────────

describe("AgentView — UserBubble collapse feature", () => {
  // ── Short message (≤10 lines) ────────────────────────────────────────────

  it("shows full content without collapse button for short message (≤10 lines)", () => {
    const shortContent = "line1\nline2\nline3\nline4\nline5"
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: shortContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Full content visible
    expect(screen.getByText(/line1/)).toBeTruthy()
    expect(screen.getByText(/line5/)).toBeTruthy()

    // No expand/collapse button
    const buttons = screen.queryAllByRole("button")
    // Filter out scroll-to-bottom button (if any)
    const collapseButtons = buttons.filter((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseButtons.length).toBe(0)
  })

  it("shows full content for exactly 10 lines without collapse button", () => {
    const tenLines = Array.from({ length: 10 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: tenLines,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // All 10 lines visible
    expect(screen.getByText(/line1/)).toBeTruthy()
    expect(screen.getByText(/line10/)).toBeTruthy()

    // No collapse button
    const buttons = screen.queryAllByRole("button")
    const collapseButtons = buttons.filter((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseButtons.length).toBe(0)
  })

  // ── Long message (>10 lines) ─────────────────────────────────────────────

  it("shows only first 10 lines with collapse button for long message (>10 lines)", () => {
    const elevenLines = Array.from({ length: 11 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: elevenLines,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // First 10 lines visible
    expect(screen.getByText(/line1/)).toBeTruthy()
    expect(screen.getByText(/line10/)).toBeTruthy()

    // Line 11 should NOT be visible (collapsed)
    expect(screen.queryByText(/line11/)).toBeNull()

    // Collapse button exists
    const buttons = screen.queryAllByRole("button")
    const collapseButtons = buttons.filter((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseButtons.length).toBe(1)
  })

  it("collapse button has aria-expanded=false initially", () => {
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseBtn?.getAttribute("aria-expanded")).toBe("false")
  })

  it("collapse button has title='Expand' when collapsed", () => {
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseBtn?.getAttribute("title")).toBe("Expand")
  })

  // ── Expand behavior ──────────────────────────────────────────────────────

  it("expands to show all content when collapse button is clicked", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Initially, line 15 is not visible
    expect(screen.queryByText(/line15/)).toBeNull()

    // Click expand button
    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)
    await user.click(collapseBtn!)

    // Now line 15 is visible
    expect(screen.getByText(/line15/)).toBeTruthy()
  })

  it("changes aria-expanded to true when expanded", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)

    await user.click(collapseBtn!)

    expect(collapseBtn?.getAttribute("aria-expanded")).toBe("true")
  })

  it("changes button title to 'Collapse' when expanded", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)

    await user.click(collapseBtn!)

    expect(collapseBtn?.getAttribute("title")).toBe("Collapse")
  })

  // ── Collapse again ───────────────────────────────────────────────────────

  it("collapses again when button is clicked a second time", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)

    // Expand
    await user.click(collapseBtn!)
    expect(screen.getByText(/line15/)).toBeTruthy()

    // Collapse
    await user.click(collapseBtn!)
    expect(screen.queryByText(/line15/)).toBeNull()
  })

  it("returns to aria-expanded=false when collapsed again", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)

    await user.click(collapseBtn!) // expand
    await user.click(collapseBtn!) // collapse

    expect(collapseBtn?.getAttribute("aria-expanded")).toBe("false")
  })

  // ── Copy button behavior ─────────────────────────────────────────────────

  it("shows copy button when timestamp is provided", () => {
    const content = "Test message"
    const timestamp = new Date()
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        timestamp,
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Copy button should be present (aria-label="Copy message")
    const copyBtn = screen.getByLabelText("Copy message")
    expect(copyBtn).toBeTruthy()
  })

  it("does not show copy button when timestamp is not provided", () => {
    const content = "Test message"
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        // No timestamp
      },
    ]

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Copy button should not be present
    const copyBtn = screen.queryByLabelText("Copy message")
    expect(copyBtn).toBeNull()
  })

  it("copies message content to clipboard when copy button is clicked", async () => {
    const user = userEvent.setup()
    const content = "Test message to copy"
    const timestamp = new Date()
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        timestamp,
      },
    ]

    // Mock clipboard API using defineProperty
    const clipboardWriteText = mock(() => Promise.resolve())
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: clipboardWriteText },
      writable: true,
    })

    render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const copyBtn = screen.getByLabelText("Copy message")
    await user.click(copyBtn)

    expect(clipboardWriteText).toHaveBeenCalledWith(content)
  })

  // ── Timestamp visibility ─────────────────────────────────────────────────

  it("shows timestamp on mouse hover", async () => {
    const user = userEvent.setup()
    const content = "Test message"
    const timestamp = new Date("2026-04-29T12:00:00Z")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        timestamp,
      },
    ]

    const { container } = render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Find the outer wrapper (group div)
    const groupDiv = container.querySelector("div[class*='group']")
    expect(groupDiv).toBeTruthy()

    // Find the timestamp span by looking for the time text
    const timeSpan = screen.getByText("12:00")
    expect(timeSpan.parentElement?.className).toContain("opacity-0")

    // Hover over the group
    await user.hover(groupDiv!)

    // Timestamp should now have opacity-100
    expect(timeSpan.parentElement?.className).toContain("opacity-100")
  })

  it("hides timestamp on mouse leave", async () => {
    const user = userEvent.setup()
    const content = "Test message"
    const timestamp = new Date("2026-04-29T12:00:00Z")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        timestamp,
      },
    ]

    const { container } = render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    const groupDiv = container.querySelector("div[class*='group']")
    const timeSpan = screen.getByText("12:00")

    // Hover in
    await user.hover(groupDiv!)
    expect(timeSpan.parentElement?.className).toContain("opacity-100")

    // Hover out
    await user.unhover(groupDiv!)
    expect(timeSpan.parentElement?.className).toContain("opacity-0")
  })

  // ── Gradient fade overlay ────────────────────────────────────────────────

  it("shows gradient fade overlay when message is collapsed", () => {
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    const { container } = render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Find the gradient fade div (has pointer-events-none and inset-x-0 bottom-0)
    const gradientFade = container.querySelector("div[class*='pointer-events-none'][class*='inset-x-0'][class*='bottom-0']")
    expect(gradientFade).toBeTruthy()
  })

  it("hides gradient fade overlay when message is expanded", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    const { container } = render(<AgentView blocks={blocks} currentBlocks={[]} isWorking={false} />)

    // Initially, gradient fade exists
    let gradientFade = container.querySelector("div[class*='pointer-events-none'][class*='inset-x-0'][class*='bottom-0']")
    expect(gradientFade).toBeTruthy()

    // Click expand
    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)
    await user.click(collapseBtn!)

    // Gradient fade should be gone (removed from DOM)
    gradientFade = container.querySelector("div[class*='pointer-events-none'][class*='inset-x-0'][class*='bottom-0']")
    expect(gradientFade).toBeNull()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// AgentPane UserBubble Tests
// ─────────────────────────────────────────────────────────────────────────────

describe("AgentPane — UserBubble collapse feature", () => {
  const createMockStream = (blocks: ContentBlock[]): AgentStream => ({
    blocks,
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
    model: "gpt-4",
    lastError: null,
  })

  // ── Short message (≤10 lines) ────────────────────────────────────────────

  it("shows full content without collapse button for short message in AgentPane", () => {
    const shortContent = "line1\nline2\nline3\nline4\nline5"
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: shortContent,
        timestamp: new Date(),
      },
    ]

    render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    // Full content visible
    expect(screen.getByText(/line1/)).toBeTruthy()
    expect(screen.getByText(/line5/)).toBeTruthy()

    // No expand/collapse button
    const buttons = screen.queryAllByRole("button")
    const collapseButtons = buttons.filter((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseButtons.length).toBe(0)
  })

  // ── Long message (>10 lines) ─────────────────────────────────────────────

  it("shows only first 10 lines with collapse button for long message in AgentPane", () => {
    const elevenLines = Array.from({ length: 11 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: elevenLines,
        timestamp: new Date(),
      },
    ]

    render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    // First 10 lines visible
    expect(screen.getByText(/line1/)).toBeTruthy()
    expect(screen.getByText(/line10/)).toBeTruthy()

    // Line 11 should NOT be visible (collapsed)
    expect(screen.queryByText(/line11/)).toBeNull()

    // Collapse button exists
    const buttons = screen.queryAllByRole("button")
    const collapseButtons = buttons.filter((btn) => btn.getAttribute("aria-expanded") !== null)
    expect(collapseButtons.length).toBe(1)
  })

  // ── Expand behavior ──────────────────────────────────────────────────────

  it("expands to show all content when collapse button is clicked in AgentPane", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    // Initially, line 15 is not visible
    expect(screen.queryByText(/line15/)).toBeNull()

    // Click expand button
    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)
    await user.click(collapseBtn!)

    // Now line 15 is visible
    expect(screen.getByText(/line15/)).toBeTruthy()
  })

  // ── Collapse again ───────────────────────────────────────────────────────

  it("collapses again when button is clicked a second time in AgentPane", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)

    // Expand
    await user.click(collapseBtn!)
    expect(screen.getByText(/line15/)).toBeTruthy()

    // Collapse
    await user.click(collapseBtn!)
    expect(screen.queryByText(/line15/)).toBeNull()
  })

  // ── Copy button behavior ─────────────────────────────────────────────────

  it("shows copy button when timestamp is provided in AgentPane", () => {
    const content = "Test message"
    const timestamp = new Date()
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        timestamp,
      },
    ]

    render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    const copyBtn = screen.getByLabelText("Copy message")
    expect(copyBtn).toBeTruthy()
  })

  it("does not show copy button when timestamp is not provided in AgentPane", () => {
    const content = "Test message"
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        // No timestamp
      },
    ]

    render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    const copyBtn = screen.queryByLabelText("Copy message")
    expect(copyBtn).toBeNull()
  })

  // ── Timestamp visibility ─────────────────────────────────────────────────

  it("shows timestamp on mouse hover in AgentPane", async () => {
    const user = userEvent.setup()
    const content = "Test message"
    const timestamp = new Date("2026-04-29T12:00:00Z")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content,
        timestamp,
      },
    ]

    const { container } = render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    // Find the outer wrapper (group div)
    const groupDiv = container.querySelector("div[class*='group']")
    expect(groupDiv).toBeTruthy()

    // Find the timestamp span by looking for the time text
    const timeSpan = screen.getByText("12:00")
    expect(timeSpan.parentElement?.className).toContain("opacity-0")

    // Hover over the group
    await user.hover(groupDiv!)

    // Timestamp should now have opacity-100
    expect(timeSpan.parentElement?.className).toContain("opacity-100")
  })

  // ── Gradient fade overlay ────────────────────────────────────────────────

  it("shows gradient fade overlay when message is collapsed in AgentPane", () => {
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    const { container } = render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    // Find the gradient fade div
    const gradientFade = container.querySelector("div[class*='pointer-events-none'][class*='inset-x-0'][class*='bottom-0']")
    expect(gradientFade).toBeTruthy()
  })

  it("hides gradient fade overlay when message is expanded in AgentPane", async () => {
    const user = userEvent.setup()
    const longContent = Array.from({ length: 15 }, (_, i) => `line${i + 1}`).join("\n")
    const blocks: ContentBlock[] = [
      {
        id: "1",
        type: "user",
        content: longContent,
        timestamp: new Date(),
      },
    ]

    const { container } = render(
      <AgentPane
        name="TestAgent"
        stream={createMockStream(blocks)}
        isLead={true}
      />
    )

    // Initially, gradient fade exists
    let gradientFade = container.querySelector("div[class*='pointer-events-none'][class*='inset-x-0'][class*='bottom-0']")
    expect(gradientFade).toBeTruthy()

    // Click expand
    const buttons = screen.queryAllByRole("button")
    const collapseBtn = buttons.find((btn) => btn.getAttribute("aria-expanded") !== null)
    await user.click(collapseBtn!)

    // Gradient fade should be gone
    gradientFade = container.querySelector("div[class*='pointer-events-none'][class*='inset-x-0'][class*='bottom-0']")
    expect(gradientFade).toBeNull()
  })
})
