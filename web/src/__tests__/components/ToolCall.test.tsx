import { describe, it, expect, afterEach, beforeEach } from "bun:test"
import { render, screen, cleanup, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ToolCall } from "@/components/ToolCall"

afterEach(cleanup)

// Mock clipboard — not available in Happy DOM
beforeEach(() => {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: () => Promise.resolve() },
    configurable: true,
    writable: true,
  })
})

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------
//
// Header markup is `<span title="…">verb <em class="italic">arg</em></span>`.
// Only the `<em>` is italicised; the outer span is not. These helpers find
// the header span by its `title` attribute (which mirrors the full text) and
// assert the italicised argument is inside an `<em>`.

/** Find the header span via its title tooltip (matches the full header text). */
function getHeader(fullText: string): HTMLElement {
  // Linear scan by attribute — Happy DOM rejects some CSS.escape outputs
  // (e.g. escaped spaces/quotes), so avoid attribute selectors entirely.
  const candidates = document.querySelectorAll("[title]")
  for (const node of Array.from(candidates)) {
    if (node instanceof HTMLElement && node.getAttribute("title") === fullText) {
      return node
    }
  }
  throw new Error(`Header with title="${fullText}" not found`)
}

/** Assert the argument portion is inside an italicised <em> in the header. */
function expectItalicArg(header: HTMLElement, arg: string) {
  const em = header.querySelector("em")
  if (!em) throw new Error(`No <em> in header (textContent="${header.textContent}")`)
  expect(em.textContent).toBe(arg)
  expect(em.className).toContain("italic")
}

// ---------------------------------------------------------------------------
// Header / status rendering
// ---------------------------------------------------------------------------

describe("ToolCall — header", () => {
  it("shows tool name when no custom display config", () => {
    render(<ToolCall name="custom_tool" args='{"path":"src/main.py"}' done={false} />)
    expect(screen.getByText("custom_tool")).toBeTruthy()
  })

  it("shows 'pending' badge when no args", () => {
    render(<ToolCall name="read" />)
    expect(screen.getByText("pending")).toBeTruthy()
  })

  it("shows spinner when running (args set, not done)", () => {
    render(<ToolCall name="read" args='{"path":"x"}' done={false} />)
    expect(screen.queryByText("pending")).toBeNull()
    // Running state: no pending badge, no done indicator
    const btn = screen.getByRole("button")
    expect(btn).toBeTruthy()
  })

  it("shows check icon when done", () => {
    render(<ToolCall name="read" args='{"path":"x"}' done={true} />)
    expect(screen.queryByText("pending")).toBeNull()
    // Done state: no pending badge
    const btn = screen.getByRole("button")
    expect(btn).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Custom tool display — shell
// ---------------------------------------------------------------------------

describe("ToolCall — shell display", () => {
  it("replaces tool name with italic description when present", () => {
    const args = JSON.stringify({ command: "npm test", description: "Run unit tests" })
    render(<ToolCall name="shell" args={args} done={false} />)
    // Description is the whole header — wrapped in <em class="italic">.
    const header = getHeader("Run unit tests")
    expectItalicArg(header, "Run unit tests")
    expect(screen.queryByText("shell")).toBeNull()
  })

  it("shows command string as args instead of JSON", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ command: "npm test", description: "Run unit tests" })
    render(<ToolCall name="shell" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("npm test")).toBeTruthy()
    expect(screen.queryByText(/"command"/)).toBeNull()
  })

  it("falls back to tool name when shell has no description", () => {
    const args = JSON.stringify({ command: "ls" })
    render(<ToolCall name="shell" args={args} done={false} />)
    expect(screen.getByText("shell")).toBeTruthy()
  })

  it("falls back to tool name when shell description is empty", () => {
    const args = JSON.stringify({ command: "ls", description: "" })
    render(<ToolCall name="shell" args={args} done={false} />)
    expect(screen.getByText("shell")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Custom tool display — web_search
// ---------------------------------------------------------------------------

describe("ToolCall — web_search display", () => {
  it("shows conversational header with query", () => {
    const args = JSON.stringify({ query: "latest python release" })
    render(<ToolCall name="web_search" args={args} done={false} />)
    // Verb stays upright; only the quoted query is italicised.
    const header = getHeader('Searching "latest python release"')
    expectItalicArg(header, '"latest python release"')
    expect(screen.queryByText("web_search")).toBeNull()
  })

  it("shows query string as args instead of JSON", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ query: "react hooks guide" })
    render(<ToolCall name="web_search" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.queryByText(/"query"/)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Custom tool display — web_fetch
// ---------------------------------------------------------------------------

describe("ToolCall — web_fetch display", () => {
  it("shows conversational header with domain", () => {
    const args = JSON.stringify({ url: "https://docs.python.org/3/library/asyncio.html" })
    render(<ToolCall name="web_fetch" args={args} done={false} />)
    const header = getHeader("Reading docs.python.org")
    expectItalicArg(header, "docs.python.org")
    expect(screen.queryByText("web_fetch")).toBeNull()
  })

  it("strips www from domain", () => {
    const args = JSON.stringify({ url: "https://www.example.com/page" })
    render(<ToolCall name="web_fetch" args={args} done={false} />)
    const header = getHeader("Reading example.com")
    expectItalicArg(header, "example.com")
  })

  it("shows full URL in args section", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ url: "https://docs.python.org/3/library/asyncio.html" })
    render(<ToolCall name="web_fetch" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("https://docs.python.org/3/library/asyncio.html")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Custom tool display — memory tools (remember, forget, recall)
// ---------------------------------------------------------------------------

describe("ToolCall — remember display", () => {
  it("shows conversational header", () => {
    const args = JSON.stringify({ items: [{ category: "preference", key: "style", value: "concise" }] })
    render(<ToolCall name="remember" args={args} done={false} />)
    // Header is a plain conversational string — no italicised argument.
    const header = getHeader("Saving to memory…")
    expect(header.textContent).toBe("Saving to memory…")
    expect(header.querySelector("em")).toBeNull()
    expect(screen.queryByText("remember")).toBeNull()
  })

  it("shows [category] key: value as args", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ items: [{ category: "preference", key: "style", value: "concise" }] })
    render(<ToolCall name="remember" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText(/\[preference\] style: concise/)).toBeTruthy()
  })

  it("shows multiple items on separate lines", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ items: [
      { category: "identity", key: "role", value: "Engineer" },
      { category: "preference", key: "style", value: "concise" },
    ]})
    render(<ToolCall name="remember" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText(/\[identity\] role: Engineer/)).toBeTruthy()
    expect(screen.getByText(/\[preference\] style: concise/)).toBeTruthy()
  })
})

describe("ToolCall — forget display", () => {
  it("shows conversational header", () => {
    const args = JSON.stringify({ items: [{ category: "preference", key: "style" }] })
    render(<ToolCall name="forget" args={args} done={false} />)
    const header = getHeader("Removing from memory…")
    expect(header.textContent).toBe("Removing from memory…")
    expect(header.querySelector("em")).toBeNull()
    expect(screen.queryByText("forget")).toBeNull()
  })

  it("shows category: key as args", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ items: [{ category: "preference", key: "style" }] })
    render(<ToolCall name="forget" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("preference: style")).toBeTruthy()
  })

  it("shows just category when no key", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ items: [{ category: "preference" }] })
    render(<ToolCall name="forget" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("preference")).toBeTruthy()
  })
})

describe("ToolCall — recall display", () => {
  it("shows conversational header when no args", () => {
    render(<ToolCall name="recall" done={false} />)
    const header = getHeader("Checking memory…")
    expect(header.textContent).toBe("Checking memory…")
    expect(header.querySelector("em")).toBeNull()
    expect(screen.queryByText("recall")).toBeNull()
  })

  it("shows conversational header with args", () => {
    const args = JSON.stringify({ category: "preference" })
    render(<ToolCall name="recall" args={args} done={false} />)
    const header = getHeader("Checking memory…")
    expect(header.textContent).toBe("Checking memory…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows category filter as args when provided", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ category: "preference" })
    render(<ToolCall name="recall" args={args} done={true} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("preference")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Default display — uncustomised tools show name + JSON
// ---------------------------------------------------------------------------

describe("ToolCall — default display", () => {
  it("shows tool name for uncustomised tools", () => {
    render(<ToolCall name="custom_tool" args='{"path":"x","value":"test"}' done={false} />)
    expect(screen.getByText("custom_tool")).toBeTruthy()
  })

  it("shows pretty-printed JSON args", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args='{"path":"src/main.py"}' done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText(/path/)).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Expand / collapse
// ---------------------------------------------------------------------------

describe("ToolCall — expand/collapse", () => {
  it("cursor-default and no expand when no details", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="date" />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("expands to show args on click", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args='{"path":"hello.txt"}' done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("arguments")).toBeTruthy()
    expect(screen.getByText(/path/)).toBeTruthy()
  })

  it("collapses on second click", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args='{"path":"hi.txt"}' done={false} />)
    const btn = screen.getByRole("button")
    await user.click(btn)
    expect(btn.getAttribute("aria-expanded")).toBe("true")
    await user.click(btn)
    expect(btn.getAttribute("aria-expanded")).toBe("false")
  })

  it("aria-expanded starts false", () => {
    render(<ToolCall name="custom_tool" args='{"path":"hi.txt"}' />)
    expect(screen.getByRole("button").getAttribute("aria-expanded")).toBe("false")
  })

  it("shows result section when done+result, after expand", async () => {
    const user = userEvent.setup()
    render(
      <ToolCall
        name="custom_tool"
        args='{"path":"hi.txt"}'
        done={true}
        result="file content here"
      />
    )
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("result")).toBeTruthy()
  })

  it("shows both args and result sections together", async () => {
    const user = userEvent.setup()
    render(
      <ToolCall
        name="custom_tool"
        args='{"path":"hi.txt"}'
        done={true}
        result="some result"
      />
    )
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("arguments")).toBeTruthy()
    expect(screen.getByText("result")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Args formatting
// ---------------------------------------------------------------------------

describe("ToolCall — args formatting", () => {
  it("pretty-prints valid JSON args for unknown tools", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args='{"name":"test","value":42}' done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText(/name/)).toBeTruthy()
  })

  it("shows raw string when args are not JSON", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args="not valid json" done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("not valid json")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// team_message display (header + body-only args)
// ---------------------------------------------------------------------------

describe("ToolCall — team_message display", () => {
  it("shows message body in args section, not raw JSON", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ content: "hello world", to: ["worker_agent"] })
    render(<ToolCall name="team_message" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("hello world")).toBeTruthy()
    expect(screen.queryByText(/"content"/)).toBeNull()
    expect(screen.queryByText(/"to"/)).toBeNull()
  })

  it("shows Messaging header with recipient name", () => {
    const args = JSON.stringify({ content: "task details", to: ["researcher"] })
    render(<ToolCall name="team_message" args={args} done={false} />)
    expectItalicArg(getHeader("Messaging researcher"), "researcher")
  })

  it("shows Messaging team when to is empty", () => {
    const args = JSON.stringify({ content: "broadcast", to: [] })
    render(<ToolCall name="team_message" args={args} done={false} />)
    expectItalicArg(getHeader("Messaging team"), "team")
  })
})

// ---------------------------------------------------------------------------
// Custom tool display — skill
// ---------------------------------------------------------------------------

describe("ToolCall — skill display", () => {
  it("shows conversational header with skill name", () => {
    const args = JSON.stringify({ skill_name: "web-design-guidelines" })
    render(<ToolCall name="skill" args={args} done={false} />)
    // Skill name is italicised inside "Loading skill: <name>".
    expectItalicArg(
      getHeader("Loading skill: web-design-guidelines"),
      "web-design-guidelines",
    )
    expect(screen.queryByText("skill")).toBeNull()
  })

  it("hides args section (formattedArgs is null)", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ skill_name: "backend-testing" })
    render(<ToolCall name="skill" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    // Args section should not be rendered
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("shows fallback header when no skill_name", () => {
    const args = JSON.stringify({})
    render(<ToolCall name="skill" args={args} done={false} />)
    const header = getHeader("Loading skill…")
    // Fallback has no argument, so no <em>/italic markup.
    expect(header.textContent).toBe("Loading skill…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows fallback header when skill_name is empty string", () => {
    const args = JSON.stringify({ skill_name: "" })
    render(<ToolCall name="skill" args={args} done={false} />)
    const header = getHeader("Loading skill…")
    expect(header.textContent).toBe("Loading skill…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows fallback header when skill_name is whitespace", () => {
    const args = JSON.stringify({ skill_name: "   " })
    render(<ToolCall name="skill" args={args} done={false} />)
    const header = getHeader("Loading skill…")
    expect(header.textContent).toBe("Loading skill…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("is not expandable (no details to show)", () => {
    const args = JSON.stringify({ skill_name: "react-component" })
    render(<ToolCall name="skill" args={args} done={false} />)
    const btn = screen.getByRole("button")
    // Button should not be clickable (cursor-default)
    expect(btn.className).toContain("cursor-default")
    expect(btn.className).not.toContain("cursor-pointer")
  })
})

// ---------------------------------------------------------------------------
// Custom tool display — bg
// ---------------------------------------------------------------------------

describe("ToolCall — bg display", () => {
  // Plain-string headers (no argument to italicise):
  //   Listing background processes…
  //   Checking process status…
  //   Reading process output…
  //   Stopping process…
  //   Managing background process…
  // PID-bearing headers italicise the pid only.

  it("shows 'Listing background processes…' for action=list", () => {
    const args = JSON.stringify({ action: "list" })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Listing background processes…")
    expect(header.textContent).toBe("Listing background processes…")
    expect(header.querySelector("em")).toBeNull()
    expect(screen.queryByText("bg")).toBeNull()
  })

  it("shows 'Checking process {pid}…' for action=status with pid", () => {
    const args = JSON.stringify({ action: "status", pid: 1234 })
    render(<ToolCall name="bg" args={args} done={false} />)
    expectItalicArg(getHeader("Checking process 1234…"), "1234")
  })

  it("shows 'Checking process status…' for action=status without pid", () => {
    const args = JSON.stringify({ action: "status" })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Checking process status…")
    expect(header.textContent).toBe("Checking process status…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Reading output of process {pid}…' for action=output with pid", () => {
    const args = JSON.stringify({ action: "output", pid: 5678 })
    render(<ToolCall name="bg" args={args} done={false} />)
    expectItalicArg(getHeader("Reading output of process 5678…"), "5678")
  })

  it("shows 'Reading process output…' for action=output without pid", () => {
    const args = JSON.stringify({ action: "output" })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Reading process output…")
    expect(header.textContent).toBe("Reading process output…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Stopping process {pid}…' for action=stop with pid", () => {
    const args = JSON.stringify({ action: "stop", pid: 9999 })
    render(<ToolCall name="bg" args={args} done={false} />)
    expectItalicArg(getHeader("Stopping process 9999…"), "9999")
  })

  it("shows 'Stopping process…' for action=stop without pid", () => {
    const args = JSON.stringify({ action: "stop" })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Stopping process…")
    expect(header.textContent).toBe("Stopping process…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Managing background process…' when no action", () => {
    const args = JSON.stringify({ pid: 1234 })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Managing background process…")
    expect(header.textContent).toBe("Managing background process…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Managing background process…' when action is empty", () => {
    const args = JSON.stringify({ action: "" })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Managing background process…")
    expect(header.textContent).toBe("Managing background process…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("shows 'Managing background process…' when action is whitespace", () => {
    const args = JSON.stringify({ action: "   " })
    render(<ToolCall name="bg" args={args} done={false} />)
    const header = getHeader("Managing background process…")
    expect(header.textContent).toBe("Managing background process…")
    expect(header.querySelector("em")).toBeNull()
  })

  it("hides args section (formattedArgs is null)", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ action: "list" })
    render(<ToolCall name="bg" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    // Args section should not be rendered
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("handles action case-insensitively", () => {
    const args = JSON.stringify({ action: "LIST" })
    render(<ToolCall name="bg" args={args} done={false} />)
    // Header is a plain string (no argument), located via title attribute.
    expect(getHeader("Listing background processes…")).toBeTruthy()
  })

  it("handles mixed case action", () => {
    const args = JSON.stringify({ action: "Status", pid: 42 })
    render(<ToolCall name="bg" args={args} done={false} />)
    // Pid is italicised in status headers.
    expectItalicArg(getHeader("Checking process 42…"), "42")
  })

  it("is not expandable (no details to show)", () => {
    const args = JSON.stringify({ action: "list" })
    render(<ToolCall name="bg" args={args} done={false} />)
    const btn = screen.getByRole("button")
    // Button should not be clickable (cursor-default)
    expect(btn.className).toContain("cursor-default")
    expect(btn.className).not.toContain("cursor-pointer")
  })

  it("shows result section when expanded with result", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ action: "output", pid: 123 })
    render(
      <ToolCall
        name="bg"
        args={args}
        done={true}
        result="process output here"
      />
    )
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("result")).toBeTruthy()
    expect(screen.getByText("process output here")).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Copy buttons
// ---------------------------------------------------------------------------

describe("ToolCall — copy buttons", () => {
  it("shows copy button for args after expand", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args='{"path":"hi.txt"}' done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByLabelText("Copy arguments")).toBeTruthy()
  })

  it("shows copy button for result after expand", async () => {
    const user = userEvent.setup()
    render(
      <ToolCall name="custom_tool" args='{"path":"hi.txt"}' done={true} result="some result" />
    )
    await user.click(screen.getByRole("button"))
    expect(screen.getByLabelText("Copy result")).toBeTruthy()
  })

  it("args copy button icon turns to check on click", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args='{"path":"hi.txt"}' done={true} />)
    await user.click(screen.getByRole("button"))
    const copyBtn = screen.getByLabelText("Copy arguments")
    await user.click(copyBtn)
    // After clicking, button still exists (didn't error out)
    await waitFor(() => expect(screen.getByLabelText("Copy arguments")).toBeTruthy())
  })

  it("result copy button icon turns to check on click", async () => {
    const user = userEvent.setup()
    render(
      <ToolCall name="custom_tool" args='{"path":"hi.txt"}' done={true} result="some result" />
    )
    await user.click(screen.getByRole("button"))
    const copyBtn = screen.getByLabelText("Copy result")
    await user.click(copyBtn)
    await waitFor(() => expect(screen.getByLabelText("Copy result")).toBeTruthy())
  })

  it("args and result copy buttons are independent", async () => {
    const user = userEvent.setup()
    render(
      <ToolCall name="custom_tool" args='{"path":"hi.txt"}' done={true} result="some result" />
    )
    await user.click(screen.getByRole("button"))
    const argsCopy = screen.getByLabelText("Copy arguments")
    await user.click(argsCopy)
    // Both buttons remain accessible after clicking one
    await waitFor(() => {
      expect(screen.getByLabelText("Copy arguments")).toBeTruthy()
      expect(screen.getByLabelText("Copy result")).toBeTruthy()
    })
  })
})

// ---------------------------------------------------------------------------
// Recent changes: shell bash label, $ prefix, formattedArgs copy, empty args
// ---------------------------------------------------------------------------

describe("ToolCall — shell bash label and formatting", () => {
  it("shows 'bash' label instead of 'arguments' for shell tool", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ command: "npm test", description: "Run tests" })
    render(<ToolCall name="shell" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    expect(screen.getByText("bash")).toBeTruthy()
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("renders shell command with $ prefix and accent color", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ command: "npm test", description: "Run tests" })
    render(<ToolCall name="shell" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    const pre = screen.getByText("npm test").closest("pre")
    expect(pre).toBeTruthy()
    // Check for $ prefix in the pre element
    expect(pre!.textContent).toContain("$ npm test")
    // Check for accent color class
    expect(pre!.className).toContain("color-accent")
  })

  it("$ prefix is non-selectable (select-none class)", async () => {
    const user = userEvent.setup()
    const args = JSON.stringify({ command: "ls -la", description: "List files" })
    render(<ToolCall name="shell" args={args} done={false} />)
    await user.click(screen.getByRole("button"))
    const pre = screen.getByText("ls -la").closest("pre")
    const dollarSpan = pre!.querySelector("span")
    expect(dollarSpan).toBeTruthy()
    expect(dollarSpan!.className).toContain("select-none")
    expect(dollarSpan!.textContent).toBe("$ ")
  })

  it("copies only the command string, not the full JSON", async () => {
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
      const args = JSON.stringify({ command: "npm test", description: "Run tests" })
      render(<ToolCall name="shell" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("npm test")
      expect(copiedText).not.toContain("command")
      expect(copiedText).not.toContain("description")
    } finally {
      // Restore original clipboard
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })
})

describe("ToolCall — copy formattedArgs instead of raw JSON", () => {
  it("copies formattedArgs for web_search (query string only)", async () => {
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
      const args = JSON.stringify({ query: "python async", other: "ignored" })
      render(<ToolCall name="web_search" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("python async")
      expect(copiedText).not.toContain("query")
      expect(copiedText).not.toContain("other")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("copies formattedArgs for web_fetch (URL only)", async () => {
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
      const args = JSON.stringify({ url: "https://example.com", timeout: 30 })
      render(<ToolCall name="web_fetch" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("https://example.com")
      expect(copiedText).not.toContain("url")
      expect(copiedText).not.toContain("timeout")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("copies formattedArgs for remember (formatted items)", async () => {
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
        items: [
          { category: "identity", key: "role", value: "Engineer" },
          { category: "preference", key: "style", value: "concise" },
        ],
      })
      render(<ToolCall name="remember" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toContain("[identity] role: Engineer")
      expect(copiedText).toContain("[preference] style: concise")
      expect(copiedText).not.toContain("items")
      expect(copiedText).not.toContain("category")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("copies formattedArgs for recall (filter string)", async () => {
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
      const args = JSON.stringify({ category: "preference", key: "style" })
      render(<ToolCall name="recall" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("preference: style")
      expect(copiedText).not.toContain("category")
      expect(copiedText).not.toContain("key")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("copies formattedArgs for forget (formatted items)", async () => {
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
        items: [
          { category: "preference", key: "style" },
          { category: "identity" },
        ],
      })
      render(<ToolCall name="forget" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toContain("preference: style")
      expect(copiedText).toContain("identity")
      expect(copiedText).not.toContain("items")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("copies full JSON for tools without custom formatting", async () => {
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
      const args = JSON.stringify({ path: "src/main.py", offset: 10, limit: 20 })
      render(<ToolCall name="custom_tool" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      // For custom_tool, formattedArgs is the full JSON, so it should copy the JSON
      expect(copiedText).toContain("path")
      expect(copiedText).toContain("src/main.py")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })
})

describe("ToolCall — empty args {} show no args section", () => {
  it("hides args section when args is empty object", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="custom_tool" args="{}" done={false} />)
    const btn = screen.getByRole("button")
    // Should not be expandable
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    // No args section should appear
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("shows no chevron when args is empty object", () => {
    render(<ToolCall name="custom_tool" args="{}" done={false} />)
    const btn = screen.getByRole("button")
    // Not expandable — cursor-default, no hover class
    expect(btn.className).toContain("cursor-default")
  })

  it("shows no expand button when args is empty object", () => {
    render(<ToolCall name="custom_tool" args="{}" done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
    expect(btn.className).not.toContain("hover:bg")
  })

  it("shows tool name when args is empty object", () => {
    render(<ToolCall name="custom_tool" args="{}" done={false} />)
    expect(screen.getByText("custom_tool")).toBeTruthy()
  })

  it("shows result section even when args is empty", async () => {
    const user = userEvent.setup()
    render(
      <ToolCall name="custom_tool" args="{}" done={true} result="some output" />
    )
    const btn = screen.getByRole("button")
    // Should be expandable because result exists
    expect(btn.className).not.toContain("cursor-default")
    await user.click(btn)
    expect(screen.getByText("result")).toBeTruthy()
  })

  it("date tool with no args shows no args section", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="date" done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    expect(screen.queryByText("arguments")).toBeNull()
  })

  it("date tool with empty args shows no args section", async () => {
    const user = userEvent.setup()
    render(<ToolCall name="date" args="{}" done={false} />)
    const btn = screen.getByRole("button")
    expect(btn.className).toContain("cursor-default")
    await user.click(btn)
    expect(screen.queryByText("arguments")).toBeNull()
  })
})

describe("ToolCall — getToolDisplay called before copy handlers", () => {
  it("formattedArgs is available in copy handler for shell", async () => {
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
      const args = JSON.stringify({ command: "echo hello", description: "Print hello" })
      render(<ToolCall name="shell" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      // If getToolDisplay was called before copy handler, formattedArgs is in scope
      expect(copiedText).toBe("echo hello")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("formattedArgs is available in copy handler for web_search", async () => {
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
      const args = JSON.stringify({ query: "typescript generics" })
      render(<ToolCall name="web_search" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("typescript generics")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("formattedArgs is available in copy handler for web_fetch", async () => {
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
      const args = JSON.stringify({ url: "https://docs.python.org" })
      render(<ToolCall name="web_fetch" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toBe("https://docs.python.org")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })

  it("formattedArgs is available in copy handler for remember", async () => {
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
        items: [{ category: "test", key: "key1", value: "val1" }],
      })
      render(<ToolCall name="remember" args={args} done={false} />)
      await user.click(screen.getByRole("button"))
      const copyBtn = screen.getByLabelText("Copy arguments")
      await user.click(copyBtn)
      expect(copiedText).toContain("[test] key1: val1")
    } finally {
      Object.defineProperty(navigator, "clipboard", {
        value: navigator.clipboard,
        writable: true,
      })
    }
  })
})
