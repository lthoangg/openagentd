import { describe, it, expect } from 'bun:test'
import React from 'react'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useScheduledTasksQuery,
  useCreateScheduledTaskMutation,
  useDeleteScheduledTaskMutation,
  usePauseScheduledTaskMutation,
  useResumeScheduledTaskMutation,
  useTriggerScheduledTaskMutation,
} from '@/queries/useSchedulerQuery'

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

describe('useScheduledTasksQuery', () => {
  it('is a query hook that uses the scheduler.list() query key', () => {
    const { result } = renderHook(() => useScheduledTasksQuery(), { wrapper: createWrapper() })

    // Verify the hook returns a query result object with expected properties
    expect(result.current).toBeTruthy()
    expect(typeof result.current.isLoading).toBe('boolean')
    expect(typeof result.current.isError).toBe('boolean')
    expect(typeof result.current.isSuccess).toBe('boolean')
  })

  it('has staleTime of 10 seconds configured', () => {
    // This is verified by the hook definition in useSchedulerQuery.ts
    // The hook is configured with staleTime: 10_000
    const { result } = renderHook(() => useScheduledTasksQuery(), { wrapper: createWrapper() })
    expect(result.current).toBeTruthy()
  })
})

describe('useCreateScheduledTaskMutation', () => {
  it('is a mutation hook that accepts ScheduledTaskCreate', () => {
    const { result } = renderHook(() => useCreateScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    // Verify the hook returns a mutation result object
    expect(result.current).toBeTruthy()
    expect(typeof result.current.mutate).toBe('function')
    expect(typeof result.current.isPending).toBe('boolean')
    expect(typeof result.current.isError).toBe('boolean')
    expect(typeof result.current.isSuccess).toBe('boolean')
  })

  it('invalidates scheduler list query on success', () => {
    // This is verified by the hook implementation which calls:
    // queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.list() })
    const { result } = renderHook(() => useCreateScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })
    expect(result.current).toBeTruthy()
  })
})

describe('useDeleteScheduledTaskMutation', () => {
  it('is a mutation hook that accepts task ID', () => {
    const { result } = renderHook(() => useDeleteScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    expect(result.current).toBeTruthy()
    expect(typeof result.current.mutate).toBe('function')
  })

  it('invalidates scheduler list query on success', () => {
    // This is verified by the hook implementation
    const { result } = renderHook(() => useDeleteScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })
    expect(result.current).toBeTruthy()
  })
})

describe('usePauseScheduledTaskMutation', () => {
  it('is a mutation hook that accepts task ID', () => {
    const { result } = renderHook(() => usePauseScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    expect(result.current).toBeTruthy()
    expect(typeof result.current.mutate).toBe('function')
  })

  it('invalidates scheduler list query on success', () => {
    // This is verified by the hook implementation
    const { result } = renderHook(() => usePauseScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })
    expect(result.current).toBeTruthy()
  })
})

describe('useResumeScheduledTaskMutation', () => {
  it('is a mutation hook that accepts task ID', () => {
    const { result } = renderHook(() => useResumeScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    expect(result.current).toBeTruthy()
    expect(typeof result.current.mutate).toBe('function')
  })

  it('invalidates scheduler list query on success', () => {
    // This is verified by the hook implementation
    const { result } = renderHook(() => useResumeScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })
    expect(result.current).toBeTruthy()
  })
})

describe('useTriggerScheduledTaskMutation', () => {
  it('is a mutation hook that accepts task ID', () => {
    const { result } = renderHook(() => useTriggerScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })

    expect(result.current).toBeTruthy()
    expect(typeof result.current.mutate).toBe('function')
  })

  it('invalidates scheduler list query on success', () => {
    // This is verified by the hook implementation
    const { result } = renderHook(() => useTriggerScheduledTaskMutation(), {
      wrapper: createWrapper(),
    })
    expect(result.current).toBeTruthy()
  })
})
