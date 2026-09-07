import { afterEach, describe, expect, it } from 'bun:test'

import {
  getCodingWorkspaceCommitDiff,
  getCodingWorkspaceGitDiff,
  getCodingWorkspaceGitHistory,
  getCodingWorkspaceStatus,
  listCodingWorkspaceFiles,
} from '@/api/client'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

describe('workspace API reads', () => {
  it('forwards the query cancellation signal to every Git and workspace read', async () => {
    const signal = new AbortController().signal
    const signals: Array<AbortSignal | null | undefined> = []
    globalThis.fetch = ((_: RequestInfo | URL, init?: RequestInit) => {
      signals.push(init?.signal)
      return Promise.resolve(new Response('{}', { status: 200 }))
    }) as typeof fetch

    await Promise.all([
      listCodingWorkspaceFiles('/workspace', signal),
      getCodingWorkspaceGitDiff('/workspace', undefined, signal),
      getCodingWorkspaceStatus('/workspace', signal),
      getCodingWorkspaceGitHistory('/workspace', 50, null, false, signal),
      getCodingWorkspaceCommitDiff('/workspace', 'abc123', signal),
    ])

    expect(signals).toEqual([signal, signal, signal, signal, signal])
  })
})
