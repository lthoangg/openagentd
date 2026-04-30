import { describe, it, expect, afterEach } from "bun:test"
import "@testing-library/jest-dom"
import { render, screen, cleanup } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { InboxBubble } from "@/components/InboxBubble"

afterEach(cleanup)

describe("InboxBubble", () => {
  // ── agent label ─────────────────────────────────────────────────────────────
  it("shows agent name in header", () => {
    render(<InboxBubble content="Hello from worker" fromAgent="worker-1" />)
    expect(screen.getByText("worker-1")).toBeTruthy()
  })

  // ── content rendering ───────────────────────────────────────────────────────

  it("renders short content (under threshold) without collapse button", () => {
    // 3 lines — under COLLAPSE_LINES=5
    const content = "line1\nline2\nline3"
    render(<InboxBubble content={content} fromAgent="bot" />)
    expect(screen.getByText(/line1/)).toBeTruthy()
    // No expand/collapse button
    const btn = screen.queryByRole("button")
    expect(btn).toBeNull()
  })

  it("renders long content (over threshold) with collapse button", () => {
    // 6 lines — over COLLAPSE_LINES=5
    const content = "1\n2\n3\n4\n5\n6"
    render(<InboxBubble content={content} fromAgent="bot" />)
    const btn = screen.getByRole("button")
    expect(btn).toBeTruthy()
  })

  it("collapse button has aria-expanded=false initially", () => {
    const content = "1\n2\n3\n4\n5\n6"
    render(<InboxBubble content={content} fromAgent="bot" />)
    const btn = screen.getByRole("button")
    expect(btn.getAttribute("aria-expanded")).toBe("false")
  })

  it("expands when collapse button is clicked", async () => {
    const user = userEvent.setup()
    const content = "line1\nline2\nline3\nline4\nline5\nline6"
    render(<InboxBubble content={content} fromAgent="bot" />)

    const btn = screen.getByRole("button")
    await user.click(btn)

    expect(btn.getAttribute("aria-expanded")).toBe("true")
  })

  it("shows all content lines after expanding", async () => {
    const user = userEvent.setup()
    const content = "alpha\nbeta\ngamma\ndelta\nepsilon\nzeta"
    render(<InboxBubble content={content} fromAgent="bot" />)

    const btn = screen.getByRole("button")
    await user.click(btn)

    expect(screen.getByText(/zeta/)).toBeTruthy()
  })

  it("collapses again when button is clicked a second time", async () => {
    const user = userEvent.setup()
    const content = "1\n2\n3\n4\n5\n6"
    render(<InboxBubble content={content} fromAgent="bot" />)

    const btn = screen.getByRole("button")
    await user.click(btn) // expand
    await user.click(btn) // collapse

    expect(btn.getAttribute("aria-expanded")).toBe("false")
  })

  // ── prefix stripping ────────────────────────────────────────────────────────

  it("strips [agent-name]: prefixes from content", () => {
    const content = "[worker-1]: This is the actual message"
    render(<InboxBubble content={content} fromAgent="worker-1" />)
    // Me stripped prefix — should not see "[worker-1]:" in content area
    expect(screen.queryByText(/\[worker-1\]:/)).toBeNull()
    expect(screen.getByText(/This is the actual message/)).toBeTruthy()
  })

  it("strips agent prefix from content", () => {
    const content = "[agent-a]: Line one"
    render(<InboxBubble content={content} fromAgent="agent-a" />)
    expect(screen.queryByText(/\[agent-a\]:/)).toBeNull()
    expect(screen.getByText(/Line one/)).toBeTruthy()
  })

  // ── compact mode ────────────────────────────────────────────────────────────

  it("applies compact styling when compact=true", () => {
    const { container } = render(
      <InboxBubble content="msg" fromAgent="bot" compact={true} />
    )
    // Me compact uses max-w-[88%] instead of max-w-[78%]
    const bubble = container.querySelector("div[class*='max-w-[88%]']")
    expect(bubble).toBeTruthy()
  })

  it("applies normal styling when compact=false", () => {
    const { container } = render(
      <InboxBubble content="msg" fromAgent="bot" compact={false} />
    )
    const bubble = container.querySelector("div[class*='max-w-[78%]']")
    expect(bubble).toBeTruthy()
  })

  // ── gradient fade ───────────────────────────────────────────────────────────

  it("shows expand/collapse button when content exceeds threshold (confirms collapse is active)", () => {
    const longContent = "line1\nline2\nline3\nline4\nline5\nline6"
    const { container } = render(
      <InboxBubble content={longContent} fromAgent="bot" />
    )
    // Me confirm button exists (needsCollapse=true)
    const btn = screen.getByRole("button")
    expect(btn).toBeTruthy()
    // Me bubble has overflow-hidden (gradient clips inside)
    const bubble = container.querySelector("div[class*='overflow-hidden']")
    expect(bubble).toBeTruthy()
  })

  it("toggle button switches aria-expanded from false to true on expand", async () => {
    const user = userEvent.setup()
    const longContent = "line1\nline2\nline3\nline4\nline5\nline6"
    render(<InboxBubble content={longContent} fromAgent="bot" />)

    const btn = screen.getByRole("button")
    expect(btn.getAttribute("aria-expanded")).toBe("false")
    await user.click(btn)
    expect(btn.getAttribute("aria-expanded")).toBe("true")
  })

  // ── left-aligned layout ─────────────────────────────────────────────────────

  it("is left-aligned (justify-start)", () => {
    const { container } = render(
      <InboxBubble content="msg" fromAgent="bot" />
    )
    const outer = container.querySelector("div[class*='justify-start']")
    expect(outer).toBeTruthy()
  })

  // ── link handling ──────────────────────────────────────────────────────────

  it("renders markdown links with target blank and rel opener", () => {
    render(
      <InboxBubble
        content="Check [this](https://example.com) link"
        fromAgent="bot"
      />
    )
    const link = screen.getByRole("link", { name: /this/i })
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("opens links in new tab", () => {
    render(
      <InboxBubble
        content="Visit [Google](https://google.com)"
        fromAgent="bot"
      />
    )
    const link = screen.getByRole("link", { name: /google/i })
    expect(link).toHaveAttribute("target", "_blank")
  })
})
