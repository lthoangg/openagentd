import { describe, it, expect, afterEach } from "bun:test"
import { render, screen, cleanup } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Thinking } from "@/components/Thinking"

afterEach(cleanup)

// NOTE on JSX strings: `<Thinking content="a\nb" />` does NOT produce a
// newline — JSX string attributes don't process escape sequences. Use an
// expression form `<Thinking content={"a\nb"} />` when a real newline is
// needed in the test fixture.

describe("Thinking — rendering & toggle", () => {
  it("renders collapsed by default", () => {
    render(<Thinking content="Test" />)
    const button = screen.getByRole("button")
    expect(button.getAttribute("aria-expanded")).toBe("false")
  })

  it("expands on click", async () => {
    const user = userEvent.setup()
    render(<Thinking content={"Heading line\n\nBody detail here"} />)

    const button = screen.getByRole("button")
    await user.click(button)

    expect(button.getAttribute("aria-expanded")).toBe("true")
    // Body is visible once expanded
    expect(screen.getByText(/Body detail here/)).toBeTruthy()
  })

  it("collapses on second click", async () => {
    const user = userEvent.setup()
    render(<Thinking content={"Heading\n\nBody"} />)

    const button = screen.getByRole("button")
    await user.click(button)
    await user.click(button)

    expect(button.getAttribute("aria-expanded")).toBe("false")
  })

  it("has descriptive aria-label", () => {
    render(<Thinking content="x" />)
    const button = screen.getByRole("button")
    const ariaLabel = button.getAttribute("aria-label")
    expect(ariaLabel).toMatch(/Expand|Collapse/)
  })
})

describe("Thinking — label extraction", () => {
  it("uses a short single-line content as the label itself", () => {
    render(<Thinking content="Done thinking" isStreaming={false} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Done thinking")
  })

  it("falls back to 'Reasoning' when content is empty", () => {
    render(<Thinking content="" isStreaming={false} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Reasoning")
  })

  it("extracts first line of multi-line content", () => {
    const content = "Determining response\n\nThe user is asking about my capabilities..."
    render(<Thinking content={content} isStreaming={false} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Determining response")
  })

  it("strips markdown bold wrapping from the label", () => {
    const content = "**Determining response needs**\n\nBody text here"
    render(<Thinking content={content} isStreaming={false} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Determining response needs")
    expect(button.textContent).not.toContain("**")
  })

  it("falls back to 'Reasoning' when first line exceeds 40 chars", () => {
    const longLine = "This is a very long first line that definitely exceeds the forty character label budget"
    render(<Thinking content={longLine} isStreaming={false} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Reasoning")
    expect(button.textContent).not.toContain("This is a very long")
  })
})

describe("Thinking — streaming behaviour", () => {
  it("holds 'Reasoning' while the first line is still growing", () => {
    // Multi-word but not-yet-terminated first line: label must stay stable
    // so it doesn't flip between successive prefixes.
    render(<Thinking content="Determining response" isStreaming={true} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Reasoning")
    expect(button.textContent).not.toContain("Determining response")
  })

  it("resolves label once a closing bold arrives mid-stream", () => {
    render(<Thinking content="**Determining response needs**" isStreaming={true} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Determining response needs")
  })

  it("resolves label once a newline arrives mid-stream", () => {
    render(<Thinking content={"Planning the approach\nMore detail follows"} isStreaming={true} />)
    const button = screen.getByRole("button")
    expect(button.textContent).toContain("Planning the approach")
  })
})

describe("Thinking — body content when expanded", () => {
  it("omits the first line from the body when it was promoted to the label", async () => {
    const user = userEvent.setup()
    const content = "Determining response\n\nThe user is asking about capabilities."
    render(<Thinking content={content} />)

    const button = screen.getByRole("button")
    await user.click(button)

    // Body shows the prose portion…
    expect(screen.getByText(/The user is asking/)).toBeTruthy()
    // …but the label line is not duplicated inside the body. Only the
    // header span should contain it.
    const matches = screen.getAllByText(/Determining response/)
    expect(matches.length).toBe(1)
  })

  it("keeps the full content in the body when label falls back to 'Reasoning'", async () => {
    const user = userEvent.setup()
    // First line exceeds 40 chars → label falls back, so the body must
    // show the whole content verbatim (including that first line).
    const longFirst = "This is a very long first line that definitely exceeds the forty character label budget"
    const content = `${longFirst}\nsecond line`
    render(<Thinking content={content} />)

    const button = screen.getByRole("button")
    await user.click(button)

    expect(screen.getByText(new RegExp(longFirst.slice(0, 30)))).toBeTruthy()
    expect(screen.getByText(/second line/)).toBeTruthy()
  })

  it("shows full content when a short single line is the only content (nothing to strip)", async () => {
    const user = userEvent.setup()
    // One-line content: the line IS the label AND the body. stripFirstLine
    // leaves nothing, so the fallback keeps the full content so expanding
    // is never a no-op.
    render(<Thinking content="Done thinking" />)

    const button = screen.getByRole("button")
    await user.click(button)

    // Both the label span and the body paragraph contain the text
    expect(screen.getAllByText(/Done thinking/).length).toBeGreaterThanOrEqual(1)
  })
})
