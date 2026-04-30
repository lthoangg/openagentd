/**
 * Shape of the team chat store.
 *
 * `AgentStream` carries everything needed to render one agent pane:
 * finalized blocks (committed at end-of-turn), the in-flight
 * ``currentBlocks`` accumulator, scratch text/thinking buffers, status,
 * usage, and the model identifier.
 *
 * `_completionBase` is the cumulative completion-token total committed
 * from prior turns. The SSE ``completion_tokens`` field is a running
 * total *within* one turn, so we add it to the base to get the
 * session-wide total.
 *
 * `CacheInvalidation` is a domain event signalling that some piece of
 * server-state changed and TanStack Query should refetch. The SSE
 * reducer pushes events onto ``cacheInvalidations``; a React-side
 * bridge in ``routes/team.tsx`` drains the queue via
 * ``_drainCacheInvalidations`` and performs the actual
 * ``queryClient.invalidateQueries`` calls. This keeps the store free
 * of TanStack imports.
 *
 * State and Actions are exported separately so individual modules
 * (defaults, sse-reducer, the store creator) can take exactly the slice
 * they need without depending on the full union.
 */
import type { ContentBlock, AgentUsage } from '@/api/types'

/** A message waiting to be dispatched after the current agent turn completes. */
export interface PendingMessage {
  id: string
  content: string
  files?: File[]
}

export type CacheInvalidation =
  | { kind: 'wiki' }
  | { kind: 'workspace_files'; sessionId: string }
  | { kind: 'scheduler' }
  | { kind: 'todos'; sessionId: string }

export interface AgentStream {
  /** Finalized blocks from previous turns (flushed on each 'done' event). */
  blocks: ContentBlock[]
  /** Live blocks accumulating during the current turn. */
  currentBlocks: ContentBlock[]
  currentText: string
  currentThinking: string
  status: 'available' | 'working' | 'error'
  usage: AgentUsage
  /** Committed completionTokens from all prior turns — SSE completion_tokens is a
   *  running total within one turn, so we accumulate across turns here. */
  _completionBase: number
  model: string | null
  lastError: string | null
}

export interface TeamStoreState {
  agentStreams: Record<string, AgentStream>
  activeAgent: string | null
  leadName: string | null
  agentNames: string[]
  sidebarOpen: boolean
  sessionId: string | null
  sessionTitle: string | null
  isTeamWorking: boolean
  isConnected: boolean
  error: string | null
  _pendingMessages: PendingMessage[]
  /** Bumped on every newSession() so stale async loadSession calls can be discarded. */
  _sessionGeneration: number
  /**
   * Domain events emitted by the SSE reducer that signal server-state
   * has changed and TanStack Query caches need invalidation. Drained
   * by the cache bridge in ``routes/team.tsx`` via
   * ``_drainCacheInvalidations``. Two ``tool_end`` events arriving in
   * one batch both push, so this is a queue rather than a single
   * field.
   */
  cacheInvalidations: CacheInvalidation[]
}

export interface TeamStoreActions {
  sendMessage: (content: string, files?: File[]) => Promise<void>
  stopTeam: () => Promise<void>
  connectStream: () => AbortController
  loadTeamStatus: () => Promise<void>
  loadSession: (sessionId: string) => Promise<void>
  setActiveAgent: (name: string) => void
  cycleActiveAgent: (dir: 'next' | 'prev') => void
  toggleSidebar: () => void
  newSession: () => void
  /** Remove a queued message by id (user clicked ×). */
  removePendingMessage: (id: string) => void
  _handleSSEEvent: (type: string, data: unknown) => void
  /**
   * Atomically returns the current ``cacheInvalidations`` queue and
   * empties it. Called by the cache bridge on every state change that
   * grows the queue. Atomic (single ``set`` call) to avoid races with
   * incoming SSE events that would push between a read and a clear.
   */
  _drainCacheInvalidations: () => CacheInvalidation[]
  _abortController: AbortController | null
}

export type TeamStore = TeamStoreState & TeamStoreActions
