import { describe, it, expect, afterEach, mock } from "bun:test"
import { render, cleanup } from "@testing-library/react"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"

afterEach(cleanup)

/**
 * Trigger a Ctrl+<key> keydown on window and return whether preventDefault
 * was called (the hook only prevents when a handler fires).
 */
function pressCtrl(key: string, opts: { meta?: boolean } = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    key,
    ctrlKey: true,
    metaKey: opts.meta ?? false,
    bubbles: true,
    cancelable: true,
  })
  window.dispatchEvent(event)
  return event
}

/** Minimal component that registers the given shortcut map. */
function Harness({ shortcuts }: { shortcuts: Partial<Record<string, () => void>> }) {
  useKeyboardShortcuts(shortcuts)
  return null
}

describe("useKeyboardShortcuts", () => {
  it("invokes the handler for a registered Ctrl+<key>", () => {
    const onDot = mock(() => {})
    render(<Harness shortcuts={{ ".": onDot }} />)

    pressCtrl(".")

    expect(onDot).toHaveBeenCalledTimes(1)
  })

  it("calls preventDefault when a handler fires", () => {
    render(<Harness shortcuts={{ ".": () => {} }} />)

    const event = pressCtrl(".")

    expect(event.defaultPrevented).toBe(true)
  })

  it("ignores keys that are not registered", () => {
    const onDot = mock(() => {})
    render(<Harness shortcuts={{ ".": onDot }} />)

    const event = pressCtrl("k")

    expect(onDot).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it("ignores presses without Ctrl", () => {
    const onDot = mock(() => {})
    render(<Harness shortcuts={{ ".": onDot }} />)

    // Meta (Cmd) alone — hook should skip it.
    const event = new KeyboardEvent("keydown", {
      key: ".",
      ctrlKey: false,
      metaKey: true,
      bubbles: true,
      cancelable: true,
    })
    window.dispatchEvent(event)

    expect(onDot).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it("ignores Ctrl+Meta combos to avoid clashing with OS shortcuts", () => {
    const onDot = mock(() => {})
    render(<Harness shortcuts={{ ".": onDot }} />)

    pressCtrl(".", { meta: true })

    expect(onDot).not.toHaveBeenCalled()
  })

  it("lowercases the key before lookup (Ctrl+Shift+A → 'a')", () => {
    const onA = mock(() => {})
    render(<Harness shortcuts={{ a: onA }} />)

    // Holding Shift sends key="A"; hook should still match the lowercase "a".
    window.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "A",
        ctrlKey: true,
        bubbles: true,
        cancelable: true,
      }),
    )

    expect(onA).toHaveBeenCalledTimes(1)
  })

  it("removes the listener on unmount", () => {
    const onDot = mock(() => {})
    const view = render(<Harness shortcuts={{ ".": onDot }} />)

    view.unmount()
    pressCtrl(".")

    expect(onDot).not.toHaveBeenCalled()
  })

  it("uses the latest shortcut map without re-subscribing", () => {
    const first = mock(() => {})
    const second = mock(() => {})
    const view = render(<Harness shortcuts={{ ".": first }} />)

    pressCtrl(".")
    expect(first).toHaveBeenCalledTimes(1)

    // Re-render with a new handler for the same key — the ref should swap.
    view.rerender(<Harness shortcuts={{ ".": second }} />)

    pressCtrl(".")
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)
  })
})

describe("useKeyboardShortcuts — focus-chat-input contract", () => {
  // TeamChatView uses `'i': () => window.dispatchEvent(new CustomEvent('focus-chat-input'))`
  // to decouple the shortcut from the input ref. This test locks in that contract.

  it("Ctrl+I fires a 'focus-chat-input' CustomEvent", () => {
    const listener = mock(() => {})
    window.addEventListener("focus-chat-input", listener)

    render(
      <Harness
        shortcuts={{
          "i": () => window.dispatchEvent(new CustomEvent("focus-chat-input")),
        }}
      />,
    )

    pressCtrl("i")

    expect(listener).toHaveBeenCalledTimes(1)
    window.removeEventListener("focus-chat-input", listener)
  })
})
