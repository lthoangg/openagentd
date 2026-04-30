import { describe, it, expect, afterEach, mock } from "bun:test"
import { render, screen, cleanup } from "@testing-library/react"
import "@testing-library/jest-dom"
import { AgentView } from "@/components/AgentView"
import type { ContentBlock } from "@/api/types"

afterEach(cleanup)

mock.module("lucide-react", () => new Proxy({}, { get: () => () => null }))

// ── helpers ───────────────────────────────────────────────────────────────────

function makeTextBlock(id: string, content: string): ContentBlock {
  return { id, type: "text", content }
}

function makeUserBlock(id: string): ContentBlock {
  return { id, type: "user", content: "hello" }
}

// ── isError / lastError props ─────────────────────────────────────────────────

describe("AgentView — error state", () => {
  it("renders nothing special when isError is false", () => {
    render(
      <AgentView
        blocks={[makeTextBlock("b1", "some output")]}
        currentBlocks={[]}
        isWorking={false}
        isError={false}
        lastError="should not appear"
      />
    )
    expect(screen.queryByText("should not appear")).toBeNull()
  })

  it("renders error box when isError=true and lastError is set", () => {
    render(
      <AgentView
        blocks={[]}
        currentBlocks={[]}
        isWorking={false}
        isError={true}
        lastError="LLM provider unavailable"
      />
    )
    expect(screen.getByText("LLM provider unavailable")).toBeTruthy()
  })

  it("does not render error box when isError=true but lastError is null", () => {
    const { container } = render(
      <AgentView
        blocks={[]}
        currentBlocks={[]}
        isWorking={false}
        isError={true}
        lastError={null}
      />
    )
    // No red error box rendered
    const errorBox = container.querySelector("[class*='color-error']")
    expect(errorBox).toBeNull()
  })

  it("does not render error box when isError is undefined", () => {
    render(
      <AgentView
        blocks={[]}
        currentBlocks={[]}
        isWorking={false}
        lastError="ghost error"
      />
    )
    expect(screen.queryByText("ghost error")).toBeNull()
  })

  it("shows error box alongside existing blocks", () => {
    render(
      <AgentView
        blocks={[makeTextBlock("b1", "partial output")]}
        currentBlocks={[]}
        isWorking={false}
        isError={true}
        lastError="Rate limit hit"
      />
    )
    expect(screen.getByText("partial output")).toBeTruthy()
    expect(screen.getByText("Rate limit hit")).toBeTruthy()
  })

  it("does not show bouncing dots when isError=true", () => {
    // Bouncing dots appear when isWorking=true with only user blocks.
    // Error state should never show dots.
    const { container } = render(
      <AgentView
        blocks={[]}
        currentBlocks={[makeUserBlock("u1")]}
        isWorking={false}
        isError={true}
        lastError="Something went wrong"
      />
    )
    const dots = container.querySelectorAll("[class*='animate-bounce']")
    expect(dots.length).toBe(0)
  })
})

// ── isError prop is optional — no regressions ─────────────────────────────────

describe("AgentView — omitting isError/lastError props", () => {
  it("renders normally without isError or lastError props", () => {
    render(
      <AgentView
        blocks={[makeTextBlock("b1", "hello world")]}
        currentBlocks={[]}
        isWorking={false}
      />
    )
    expect(screen.getByText("hello world")).toBeTruthy()
  })

  it("shows working dots without isError prop", () => {
    const { container } = render(
      <AgentView
        blocks={[]}
        currentBlocks={[makeUserBlock("u1")]}
        isWorking={true}
      />
    )
    const dots = container.querySelectorAll("[class*='animate-bounce']")
    expect(dots.length).toBe(3)
  })
})
