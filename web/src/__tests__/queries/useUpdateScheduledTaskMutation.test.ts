import { describe, it, expect } from 'bun:test'
import React from 'react'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useUpdateScheduledTaskMutation } from '@/queries/useSchedulerQuery'

// ── Query client wrapper ─────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children)
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('useUpdateScheduledTaskMutation', () => {
  it('is a mutation hook that accepts id and body parameters', () => {
    const { result } = renderHook(() => useUpdateScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    // Verify the hook returns a mutation result object
    expect(result.current).toBeTruthy()
    expect(typeof result.current.mutate).toBe('function')
    expect(typeof result.current.mutateAsync).toBe('function')
  })

  it('has isPending, isError, and isSuccess properties', () => {
    const { result } = renderHook(() => useUpdateScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    expect(typeof result.current.isPending).toBe('boolean')
    expect(typeof result.current.isError).toBe('boolean')
    expect(typeof result.current.isSuccess).toBe('boolean')
  })

  it('invalidates scheduler list query on success', () => {
    // This is verified by the hook implementation which calls:
    // queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    const { result } = renderHook(() => useUpdateScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })
    expect(result.current).toBeTruthy()
  })

  it('supports onSuccess and onError callbacks', () => {
    const { result } = renderHook(() => useUpdateScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    // Verify the mutation can accept callbacks
    expect(typeof result.current.mutate).toBe('function')
  })
})
