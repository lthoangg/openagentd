/**
 * Tests for the sandbox deny-list settings — API client + page rendering.
 */
import { describe, it, expect, mock } from 'bun:test'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { getSandboxSettings, updateSandboxSettings } from '@/api/client'
import { SandboxSettingsPage } from '@/routes/settings.sandbox'

// ── API client ──────────────────────────────────────────────────────────────

describe('getSandboxSettings', () => {
  it('returns the parsed deny-list', async () => {
    const original = globalThis.fetch
    globalThis.fetch = mock(
      async () =>
        new Response(JSON.stringify({ denied_patterns: ['**/.env'] }), {
          status: 200,
        }),
    )
    try {
      const result = await getSandboxSettings()
      expect(result).toEqual({ denied_patterns: ['**/.env'] })
    } finally {
      globalThis.fetch = original
    }
  })

  it('throws on non-ok response', async () => {
    const original = globalThis.fetch
    globalThis.fetch = mock(async () => new Response(null, { status: 500 }))
    try {
      await getSandboxSettings()
      expect.unreachable('should throw')
    } catch (err) {
      expect(err).toBeInstanceOf(Error)
    } finally {
      globalThis.fetch = original
    }
  })
})

describe('updateSandboxSettings', () => {
  it('PUTs JSON body and returns the response', async () => {
    const captured: { url?: string; init?: RequestInit } = {}
    const original = globalThis.fetch
    globalThis.fetch = mock(async (url: RequestInfo | URL, init?: RequestInit) => {
      captured.url = String(url)
      captured.init = init
      return new Response(JSON.stringify({ denied_patterns: ['**/foo'] }), {
        status: 200,
      })
    })
    try {
      const result = await updateSandboxSettings({ denied_patterns: ['**/foo'] })
      expect(result.denied_patterns).toEqual(['**/foo'])
      expect(captured.url).toContain('/api/settings/sandbox')
      expect(captured.init?.method).toBe('PUT')
      expect(JSON.parse(String(captured.init?.body))).toEqual({
        denied_patterns: ['**/foo'],
      })
    } finally {
      globalThis.fetch = original
    }
  })
})

// ── Page rendering ──────────────────────────────────────────────────────────

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <SandboxSettingsPage />
    </QueryClientProvider>,
  )
}

describe('SandboxSettingsPage', () => {
  it('renders pattern rows from the server', async () => {
    const original = globalThis.fetch
    globalThis.fetch = mock(
      async () =>
        new Response(JSON.stringify({ denied_patterns: ['**/.env', 'db/**'] }), {
          status: 200,
        }),
    )
    try {
      renderPage()
      const inputs = await waitFor(() => {
        const found = screen.getAllByRole('textbox')
        if (found.length < 2) throw new Error('not yet')
        return found
      })
      expect((inputs[0] as HTMLInputElement).value).toBe('**/.env')
      expect((inputs[1] as HTMLInputElement).value).toBe('db/**')
    } finally {
      globalThis.fetch = original
    }
  })

  it('adds a new empty row when "Add pattern" is clicked', async () => {
    const original = globalThis.fetch
    globalThis.fetch = mock(
      async () =>
        new Response(JSON.stringify({ denied_patterns: ['**/.env'] }), {
          status: 200,
        }),
    )
    try {
      renderPage()
      // wait for the loaded row
      await waitFor(() => screen.getAllByRole('textbox'))

      const addBtn = screen.getByRole('button', { name: /add pattern/i })
      fireEvent.click(addBtn)

      const inputs = screen.getAllByRole('textbox')
      expect(inputs.length).toBe(2)
      expect((inputs[1] as HTMLInputElement).value).toBe('')
    } finally {
      globalThis.fetch = original
    }
  })

  it('shows empty-state when server returns no patterns', async () => {
    const original = globalThis.fetch
    globalThis.fetch = mock(
      async () =>
        new Response(JSON.stringify({ denied_patterns: [] }), { status: 200 }),
    )
    try {
      renderPage()
      await waitFor(() => {
        expect(screen.getByText(/no patterns/i)).toBeTruthy()
      })
    } finally {
      globalThis.fetch = original
    }
  })
})
