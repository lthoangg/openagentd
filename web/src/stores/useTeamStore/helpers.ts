/**
 * Cross-slice helpers for the team store.
 *
 * `WIKI_MUTATING_TOOLS`, `SCHEDULER_MUTATING_TOOLS`, and
 * `TODO_MUTATING_TOOLS` enumerate which tools should trigger TanStack
 * Query cache invalidations on ``tool_end``. Read-only tools (`read`,
 * `ls`, `grep`, `glob`) are intentionally excluded from
 * ``WIKI_MUTATING_TOOLS`` because reads do not invalidate the tree
 * cache.
 *
 * `touchesWiki` decides whether a write/edit/rm tool call landed in
 * the agent's ``wiki/`` root (in which case the wiki query cache is
 * invalidated) or in the session workspace (workspace-files cache).
 * Falls back to a substring check when args are still streaming.
 *
 * `revokeBlobUrlsFromBlocks` releases ObjectURLs created for optimistic
 * file attachments when a ``loadSession`` call replaces the live blocks.
 */
import type { ContentBlock } from '@/api/types'

// Tools that can mutate the wiki tree when their `path` argument targets
// the `wiki/` root.  Read-only tools (`read`, `ls`, `grep`, `glob`) are
// intentionally excluded — reads do not invalidate the tree cache.
export const WIKI_MUTATING_TOOLS = new Set(['write', 'edit', 'rm'])

// Tools that always write to wiki/notes/ — invalidate the wiki tree
// unconditionally on tool_end (no path check needed).
export const NOTE_TOOLS = new Set(['note'])

// Tools that mutate the scheduler.  On tool_end we invalidate the scheduler
// list so the SchedulerPanel reflects the change without a manual refresh.
export const SCHEDULER_MUTATING_TOOLS = new Set(['schedule_task'])

// todo_manage handles all todo mutations (create, update, delete).
export const TODO_MUTATING_TOOLS = new Set(['todo_manage'])

export function touchesWiki(toolName: string, toolArgs: string | undefined): boolean {
  if (!WIKI_MUTATING_TOOLS.has(toolName)) return false
  if (!toolArgs) return false
  try {
    const parsed = JSON.parse(toolArgs) as { path?: unknown }
    const p = typeof parsed.path === 'string' ? parsed.path : ''
    return p.startsWith('wiki/') || p === 'wiki'
  } catch {
    // Args may still be streaming — fall back to substring check
    return toolArgs.includes('"path":"wiki/') || toolArgs.includes('"path": "wiki/')
  }
}

// Helper to revoke blob URLs from blocks to prevent memory leaks
export function revokeBlobUrlsFromBlocks(blocks: ContentBlock[]) {
  for (const block of blocks) {
    if (block.attachments) {
      for (const att of block.attachments) {
        if (att.url?.startsWith('blob:')) {
          URL.revokeObjectURL(att.url)
        }
      }
    }
  }
}
