/**
 * applyCacheInvalidations — pure event-to-invalidation mapping.
 *
 * The team store's SSE reducer enqueues ``CacheInvalidation`` events
 * onto its ``cacheInvalidations`` queue; ``routes/cockpit.tsx`` drains
 * the queue and hands events to ``applyCacheInvalidations``, which
 * translates them to ``queryClient.invalidateQueries`` calls.
 *
 * These tests pin the kind→queryKey mapping.  Any change to a
 * ``queryKeys.*`` factory used by the bridge will surface here.
 */
import { describe, it, expect, mock } from 'bun:test'
import { applyCacheInvalidations } from '@/stores/cache-invalidation-bridge'
import { queryKeys } from '@/queries'
import type { CacheInvalidation } from '@/stores/useTeamStore'

function makeMockClient() {
  return { invalidateQueries: mock(() => Promise.resolve()) }
}

describe('applyCacheInvalidations', () => {
  it('maps `wiki` event to wiki.all()', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'wiki' }])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(1)
    expect(client.invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.wiki.all(),
    })
  })

  it('maps `workspace_files` event to team.files(sessionId)', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'workspace_files', sessionId: 'sid-123' }])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(1)
    expect(client.invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.team.files('sid-123'),
    })
  })

  it('maps `scheduler` event to scheduler.list()', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'scheduler' }])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(1)
    expect(client.invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.scheduler.list(),
    })
  })

  it('maps `todos` event to todos(sessionId)', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'todos', sessionId: 'sid-abc' }])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(1)
    expect(client.invalidateQueries).toHaveBeenCalledWith({
      queryKey: queryKeys.todos('sid-abc'),
    })
  })

  it('uses the exact key shape ["scheduler", "list"] (regression guard)', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'scheduler' }])
    const call = client.invalidateQueries.mock.calls[0][0] as { queryKey: readonly unknown[] }
    expect(call.queryKey).toEqual(['scheduler', 'list'])
  })

  it('uses the exact key shape ["team", "files", sessionId] (regression guard)', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'workspace_files', sessionId: 'sid-xyz' }])
    const call = client.invalidateQueries.mock.calls[0][0] as { queryKey: readonly unknown[] }
    expect(call.queryKey).toEqual(['team', 'files', 'sid-xyz'])
  })

  it('uses the exact key shape ["todos", sessionId] (regression guard)', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [{ kind: 'todos', sessionId: 'sid-xyz' }])
    const call = client.invalidateQueries.mock.calls[0][0] as { queryKey: readonly unknown[] }
    expect(call.queryKey).toEqual(['todos', 'sid-xyz'])
  })

  // ── Multiple-event drains ───────────────────────────────────────────────

  it('processes a batch of events in order, one invalidateQueries call per event', () => {
    const client = makeMockClient()
    const events: CacheInvalidation[] = [
      { kind: 'wiki' },
      { kind: 'scheduler' },
      { kind: 'workspace_files', sessionId: 'sid-1' },
      { kind: 'todos', sessionId: 'sid-1' },
    ]
    applyCacheInvalidations(client, events)
    expect(client.invalidateQueries).toHaveBeenCalledTimes(4)
    expect(client.invalidateQueries.mock.calls[0][0]).toEqual({
      queryKey: queryKeys.wiki.all(),
    })
    expect(client.invalidateQueries.mock.calls[1][0]).toEqual({
      queryKey: queryKeys.scheduler.list(),
    })
    expect(client.invalidateQueries.mock.calls[2][0]).toEqual({
      queryKey: queryKeys.team.files('sid-1'),
    })
    expect(client.invalidateQueries.mock.calls[3][0]).toEqual({
      queryKey: queryKeys.todos('sid-1'),
    })
  })

  it('processes duplicate events (TanStack invalidation is idempotent)', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [
      { kind: 'scheduler' },
      { kind: 'scheduler' },
      { kind: 'scheduler' },
    ])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(3)
    for (let i = 0; i < 3; i += 1) {
      expect(client.invalidateQueries.mock.calls[i][0]).toEqual({
        queryKey: queryKeys.scheduler.list(),
      })
    }
  })

  it('preserves per-event sessionId across mixed sessions', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [
      { kind: 'workspace_files', sessionId: 'sid-A' },
      { kind: 'workspace_files', sessionId: 'sid-B' },
      { kind: 'todos', sessionId: 'sid-A' },
    ])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(3)
    expect(client.invalidateQueries.mock.calls[0][0]).toEqual({
      queryKey: queryKeys.team.files('sid-A'),
    })
    expect(client.invalidateQueries.mock.calls[1][0]).toEqual({
      queryKey: queryKeys.team.files('sid-B'),
    })
    expect(client.invalidateQueries.mock.calls[2][0]).toEqual({
      queryKey: queryKeys.todos('sid-A'),
    })
  })

  // ── Empty queue ─────────────────────────────────────────────────────────

  it('is a no-op for an empty event list', () => {
    const client = makeMockClient()
    applyCacheInvalidations(client, [])
    expect(client.invalidateQueries).toHaveBeenCalledTimes(0)
  })
})
