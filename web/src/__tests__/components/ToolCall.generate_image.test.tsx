import { describe, it, expect, afterEach, mock } from "bun:test"
import { render, screen, cleanup } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ToolCall } from "@/components/ToolCall"

// Mock framer-motion to avoid animation complexity in tests
mock.module("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock lucide-react icons to avoid SVG rendering issues
mock.module("lucide-react", () => ({
  ChevronRight: () => null,
  Copy: () => null,
  Check: () => null,
}))

afterEach(cleanup)

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------
//
// Header markup is `<span title="full text">verb <em class="italic">arg</em></span>`.
// These helpers locate the outer header span via its `title` attribute and
// assert the argument portion is inside an italicised `<em>`.

function getHeader(fullText: string): HTMLElement {
  // Linear scan by attribute — Happy DOM rejects some CSS.escape outputs
  const candidates = document.querySelectorAll("[title]")
  for (const node of Array.from(candidates)) {
    if (node instanceof HTMLElement && node.getAttribute("title") === fullText) {
      return node
    }
  }
  throw new Error(`Header with title="${fullText}" not found`)
}

function expectItalicArg(header: HTMLElement, arg: string) {
  const em = header.querySelector("em")
  if (!em) throw new Error(`No <em> in header (textContent="${header.textContent}")`)
  expect(em.textContent).toBe(arg)
  expect(em.className).toContain("italic")
}

// ---------------------------------------------------------------------------
// generate_image header display
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image header", () => {
  it("shows 'Painting' with italicised filename when filename provided without extension", () => {
    const args = JSON.stringify({ prompt: "a red cube", filename: "red-cube" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting red-cube.png")
    expectItalicArg(header, "red-cube.png")
  })

  it("normalises filename ending in .png (case insensitive) to avoid double extension", () => {
    const args = JSON.stringify({ prompt: "a chart", filename: "chart.PNG" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting chart.png")
    expectItalicArg(header, "chart.png")
    // Ensure no double extension like "chart.PNG.png"
    expect(header.textContent).not.toContain("chart.PNG.png")
  })

  it("normalises filename ending in .png (lowercase) correctly", () => {
    const args = JSON.stringify({ prompt: "a diagram", filename: "diagram.png" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting diagram.png")
    expectItalicArg(header, "diagram.png")
  })

  it("strips any trailing extension before appending .png (matches backend sanitiser)", () => {
    const args = JSON.stringify({ prompt: "a photo", filename: "photo.jpg" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    // Backend always saves as PNG regardless of input extension, so the UI
    // must show the true on-disk filename, not ``photo.jpg.png``.
    const header = getHeader("Painting photo.png")
    expectItalicArg(header, "photo.png")
    expect(header.textContent).not.toContain("photo.jpg.png")
  })

  it("shows 'Painting an image…' when filename is omitted", () => {
    const args = JSON.stringify({ prompt: "a cat" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting an image…")
    // No <em> in this case — the entire header is plain text
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Painting an image…' when filename is empty string", () => {
    const args = JSON.stringify({ prompt: "a cat", filename: "" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting an image…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Painting an image…' when filename is whitespace-only", () => {
    const args = JSON.stringify({ prompt: "a cat", filename: "   " })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting an image…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("does not render raw tool name 'generate_image' when args provided", () => {
    const args = JSON.stringify({ prompt: "a cube", filename: "cube" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    expect(screen.queryByText("generate_image")).toBeNull()
  })

  it("shows 'generate_image' as tool name when args is undefined (pending state)", () => {
    render(<ToolCall name="generate_image" done={false} />)
    expect(screen.getByText("generate_image")).toBeTruthy()
  })

  it("shows 'pending' badge when args is undefined", () => {
    render(<ToolCall name="generate_image" done={false} />)
    expect(screen.getByText("pending")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// generate_image args display
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image args display", () => {
  it("shows prompt as formatted args when expanded", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a red cube", filename: "cube" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("a red cube")).toBeTruthy()
  })

  it("shows 'arguments' label for args section (not 'bash')", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a cat", filename: "cat" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("arguments")).toBeTruthy()
    expect(screen.queryByText("bash")).toBeNull()
  })

  it("hides args section when prompt is missing", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ filename: "foo" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    // Should not be expandable (no args, no result)
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("hides args section when prompt is empty string", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "", filename: "foo" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("hides args section when prompt is whitespace-only", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "   ", filename: "foo" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("shows copy button for args when prompt is present", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a dog", filename: "dog" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByLabelText("Copy arguments")).toBeTruthy()
  })

  it("copies only the prompt, not the full JSON", async () => {
    const user = userEvent.setup()
    let copiedText = ""
    const mockWriteText = async (text: string) => {
      copiedText = text
    }
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: mockWriteText },
      writable: true,
    })

    try {
      const args = JSON.stringify({ prompt: "a beautiful sunset", filename: "sunset" })
      render(<ToolCall name="generate_image" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("a beautiful sunset")
      expect(copiedText).not.toContain("prompt")
      expect(copiedText).not.toContain("filename")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("lists single input image filename above prompt when images has one entry", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({
      prompt: "make it red",
      filename: "cube",
      images: ["logo.png"],
    })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    // Blank line separator in whitespace-pre-wrap <pre>; assert on combined text.
    expect(screen.getByText(/images: logo\.png/)).toBeTruthy()
    expect(screen.getByText(/make it red/)).toBeTruthy()
  })

  it("lists comma-joined filenames above prompt when multiple images provided", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({
      prompt: "combine these",
      filename: "out",
      images: ["logo.png", "chart.png", "scene.png"],
    })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(
      screen.getByText(/images: logo\.png, chart\.png, scene\.png/),
    ).toBeTruthy()
    expect(screen.getByText(/combine these/)).toBeTruthy()
  })

  it("omits images line when images is an empty array", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({
      prompt: "a red cube",
      filename: "cube",
      images: [],
    })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("a red cube")).toBeTruthy()
    expect(screen.queryByText(/^images:/)).toBeNull()
  })

  it("ignores empty-string entries in images array", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({
      prompt: "edit",
      filename: "out",
      images: ["", "logo.png", ""],
    })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText(/images: logo\.png/)).toBeTruthy()
  })

  it("copies images line + blank separator + prompt together", async () => {
    const user = userEvent.setup()
    let copiedText = ""
    const mockWriteText = async (text: string) => {
      copiedText = text
    }
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: mockWriteText },
      writable: true,
    })

    try {
      const args = JSON.stringify({
        prompt: "make it red",
        filename: "cube",
        images: ["logo.png", "chart.png"],
      })
      render(<ToolCall name="generate_image" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      await user.click(screen.getByLabelText("Copy arguments"))
      expect(copiedText).toBe("images: logo.png, chart.png\n\nmake it red")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })
})

// ---------------------------------------------------------------------------
// generate_image result suppression
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image result suppression", () => {
  it("suppresses result section even when result is provided", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a cube", filename: "cube" })
    render(
      <ToolCall
        name="generate_image"
        args={args}
        done={true}
        result="![a cube](cube.png)"
      />
    )
    // Expand to see details
    await user.click(screen.getByRole("button"))
    // Result caption should NOT be in the DOM
    expect(screen.queryByText(/^result$/i)).toBeNull()
    // Arguments section should be visible
    expect(screen.getByText("arguments")).toBeTruthy()
    // Result content should NOT be in the DOM
    expect(screen.queryByText("![a cube](cube.png)")).toBeNull()
  })

  it("shows only arguments section when expanded (no result section)", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a landscape", filename: "landscape" })
    render(
      <ToolCall
        name="generate_image"
        args={args}
        done={true}
        result="![landscape](landscape.png)"
      />
    )
    await user.click(screen.getByRole("button"))
    // Only arguments section should be visible
    expect(screen.getByText("arguments")).toBeTruthy()
    // Result section should not exist
    expect(screen.queryByText("result")).toBeNull()
  })

  it("is still expandable when result is provided (because args are present)", () => {
    const args = JSON.stringify({ prompt: "a tree", filename: "tree" })
    render(
      <ToolCall
        name="generate_image"
        args={args}
        done={true}
        result="![tree](tree.png)"
      />
    )
    const btn = screen.getByRole("button")
    // Should be expandable because formattedArgs (prompt) is truthy
    expect(btn.className).not.toContain("cursor-default")
    expect(btn.className).toContain("cursor-pointer")
  })

  it("is not expandable when both args and result are absent", () => {
    const args = JSON.stringify({})
    render(
      <ToolCall
        name="generate_image"
        args={args}
        done={true}
        result="something"
      />
    )
    const btn = screen.getByRole("button")
    // No args, result is suppressed → not expandable
    expect(btn.className).toContain("cursor-default")
  })

  it("does not show result copy button when result is suppressed", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a flower", filename: "flower" })
    render(
      <ToolCall
        name="generate_image"
        args={args}
        done={true}
        result="![flower](flower.png)"
      />
    )
    await user.click(screen.getByRole("button"))
    expect(screen.queryByLabelText("Copy result")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// generate_image expand/collapse
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image expand/collapse", () => {
  it("is expandable when prompt is provided", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a mountain", filename: "mountain" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).not.toContain("cursor-default")
    await user.click(btn)
    expect(screen.getByText("arguments")).toBeTruthy()
  })

  it("is not expandable when no prompt and no result", () => {
    const args = JSON.stringify({ filename: "foo" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
  })

  it("shows chevron when expandable", () => {
    const args = JSON.stringify({ prompt: "a river", filename: "river" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    // When expandable, the header button is interactive
    expect(btn.className).toContain("cursor-pointer")
    expect(btn.className).not.toContain("cursor-default")
  })

  it("does not show chevron when not expandable", () => {
    const args = JSON.stringify({ filename: "foo" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
  })

  it("toggles expanded state on click", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "a sky", filename: "sky" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.getAttribute("aria-expanded")).toBe("false")
    await user.click(btn)
    expect(btn.getAttribute("aria-expanded")).toBe("true")
    await user.click(btn)
    expect(btn.getAttribute("aria-expanded")).toBe("false")
  })
})

// ---------------------------------------------------------------------------
// generate_image status indicators
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image status indicators", () => {
  it("shows pending badge when no args", () => {
    render(<ToolCall name="generate_image" done={false} />)
    expect(screen.getByText("pending")).toBeTruthy()
  })

  it("shows running indicator when running (args set, not done)", () => {
    const args = JSON.stringify({ prompt: "a cloud", filename: "cloud" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    const pulsingDot = btn.querySelector("span.animate-pulse")
    expect(pulsingDot).toBeTruthy()
  })

  it("shows done indicator when done", () => {
    const args = JSON.stringify({ prompt: "a star", filename: "star" })
    render(<ToolCall name="generate_image" args={args} done={true} />)
    const btn = screen.getByRole("button")
    expect(btn).toBeTruthy()
    // Done state: no pending badge
    expect(screen.queryByText("pending")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// generate_image edge cases
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image edge cases", () => {
  it("handles filename with multiple dots (only strips final .png)", () => {
    const args = JSON.stringify({ prompt: "a file", filename: "my.image.file.png" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting my.image.file.png")
    expectItalicArg(header, "my.image.file.png")
  })

  it("handles filename with multiple dots and no .png extension", () => {
    const args = JSON.stringify({ prompt: "a file", filename: "my.image.file" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    // Regex strips only the final trailing extension — ``.file`` is treated
    // as one, so output is ``my.image.png``.
    const header = getHeader("Painting my.image.png")
    expectItalicArg(header, "my.image.png")
  })

  it("handles special characters in filename", () => {
    const args = JSON.stringify({ prompt: "a scene", filename: "my-image_v2" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting my-image_v2.png")
    expectItalicArg(header, "my-image_v2.png")
  })

  it("handles special characters in prompt", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ prompt: "A beautiful sunset with colors: red, orange, yellow!", filename: "sunset" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("A beautiful sunset with colors: red, orange, yellow!")).toBeTruthy()
  })

  it("handles very long prompt", async () => {
    const user = userEvent.setup()
    const longPrompt = "A detailed landscape painting showing a mountain range with snow-capped peaks, a crystal clear lake in the foreground, and a sunset sky with vibrant colors"
    const args = JSON.stringify({ prompt: longPrompt, filename: "landscape" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText(longPrompt)).toBeTruthy()
  })

  it("handles extra fields in args (ignored)", () => {
    const args = JSON.stringify({ prompt: "a scene", filename: "scene", model: "dall-e-3", quality: "hd" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting scene.png")
    expectItalicArg(header, "scene.png")
  })

  it("handles null prompt", () => {
    const args = JSON.stringify({ prompt: null, filename: "foo" })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const btn = screen.getByRole("button")
    // null prompt is treated as missing
    expect(btn.className).toContain("cursor-default")
  })

  it("handles null filename", () => {
    const args = JSON.stringify({ prompt: "a scene", filename: null })
    render(<ToolCall name="generate_image" args={args} done={false} />)
    const header = getHeader("Painting an image…")
    expect(header.querySelector("em")).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// generate_image does not regress other tools
// ---------------------------------------------------------------------------

describe("ToolCall — generate_image does not regress other tools", () => {
  it("shell tool still shows result section (suppressResult defaults to false)", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ command: "ls", description: "list files" })
    render(
      <ToolCall
        name="shell"
        args={args}
        done={true}
        result="file1\nfile2\nfile3"
      />
    )
    await user.click(screen.getByRole("button"))
    // Both sections should be visible
    expect(screen.getByText("bash")).toBeTruthy()
    expect(screen.getByText("result")).toBeTruthy()
    // Result content is wrapped in a span, so use a regex matcher
    expect(screen.getByText(/file1.*file2.*file3/s)).toBeTruthy()
  })

  it("web_search tool still shows result section", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ query: "python asyncio" })
    render(
      <ToolCall
        name="web_search"
        args={args}
        done={true}
        result="Found 1000 results about asyncio"
      />
    )
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("arguments")).toBeTruthy()
    expect(screen.getByText("result")).toBeTruthy()
  })
})
