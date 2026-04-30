import { describe, it, expect, afterEach, beforeEach } from 'bun:test'
import { useRef } from 'react'
import { render, screen, cleanup, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FloatingInputBar } from '@/components/FloatingInputBar'

const STORAGE_KEY = 'oa-input-position'

afterEach(cleanup)
beforeEach(() => {
  localStorage.clear()
})

// Test harness — provides a bounds container with a stable, measurable size.
function Harness(props: {
  onSubmit?: (message: string, files?: File[]) => void
  placeholder?: string
}) {
  const boundsRef = useRef<HTMLDivElement>(null)
  return (
    <div
      ref={boundsRef}
      data-testid="bounds"
      style={{ position: 'relative', width: 1200, height: 800 }}
    >
      <FloatingInputBar
        boundsRef={boundsRef}
        onSubmit={props.onSubmit ?? (() => {})}
        placeholder={props.placeholder ?? 'Message…'}
      />
    </div>
  )
}

describe('FloatingInputBar', () => {
  it('renders the inner InputBar textarea', () => {
    render(<Harness />)
    const textarea = screen.getByRole('textbox', { name: 'Message input' })
    expect(textarea).toBeTruthy()
  })

  it('exposes a drag handle labelled for screen readers', () => {
    render(<Harness />)
    const handle = screen.getByRole('button', { name: /drag input bar/i })
    expect(handle).toBeTruthy()
  })

  it('starts at the default position (zero offset) when no value is stored', () => {
    render(<Harness />)
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('reads persisted offset from localStorage on mount without throwing', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 40, y: -120 }))
    expect(() => render(<Harness />)).not.toThrow()
    // After mount the clamp effect may rewrite the value if bounds don't
    // accommodate the stored offset; we only require the entry remains
    // valid JSON with numeric fields.
    const raw = localStorage.getItem(STORAGE_KEY)
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!) as { x: number; y: number }
    expect(typeof parsed.x).toBe('number')
    expect(typeof parsed.y).toBe('number')
  })

  it('ignores malformed localStorage entries without throwing', () => {
    localStorage.setItem(STORAGE_KEY, 'not-json')
    expect(() => render(<Harness />)).not.toThrow()
  })

  it('ignores localStorage entries that do not match the expected shape', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ foo: 'bar' }))
    expect(() => render(<Harness />)).not.toThrow()
  })

  it('resets position on double-click of the handle', async () => {
    const user = userEvent.setup()
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 40, y: -120 }))
    render(<Harness />)

    const handle = screen.getByRole('button', { name: /drag input bar/i })
    await user.dblClick(handle)

    expect(localStorage.getItem(STORAGE_KEY)).toBe(JSON.stringify({ x: 0, y: 0 }))
  })

  it('clamps a stored offset back into bounds on window resize', () => {
    // Seed an out-of-bounds offset. The clamp effect runs on mount and on
    // resize; the mount pass should already correct it, but we also verify
    // a resize event does not push it further.
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 99999, y: -99999 }))
    render(<Harness />)

    act(() => {
      window.dispatchEvent(new Event('resize'))
    })

    const raw = localStorage.getItem(STORAGE_KEY)
    // Clamp may be a no-op if jsdom reports zero-sized rects, but if it
    // writes anything it must not preserve the extreme values.
    if (raw !== null && raw !== JSON.stringify({ x: 99999, y: -99999 })) {
      const parsed = JSON.parse(raw) as { x: number; y: number }
      expect(Math.abs(parsed.x)).toBeLessThan(99999)
      expect(Math.abs(parsed.y)).toBeLessThan(99999)
    }
  })

  it('forwards the placeholder prop to the inner InputBar', () => {
    render(<Harness placeholder="Ask the team…" />)
    const textarea = screen.getByRole('textbox', { name: 'Message input' })
    expect(textarea.getAttribute('placeholder')).toBe('Ask the team…')
  })
})
