/**
 * Me check if content ends with a sleep sentinel.
 * Returns the text before the sentinel (may be empty), or null if not present.
 */
export function extractSleepPrefix(content: string): string | null {
  const trimmed = content.trimEnd()
  if (trimmed.endsWith('<sleep>')) return trimmed.slice(0, -'<sleep>'.length).trimEnd()
  if (trimmed.endsWith('[sleep]')) return trimmed.slice(0, -'[sleep]'.length).trimEnd()
  return null
}

/** Me check if content ends with a sleep sentinel */
export function isSleepMessage(content: string): boolean {
  return extractSleepPrefix(content) !== null
}

export function shortId(id: string): string {
  return id.slice(0, 8)
}

export function formatTime(date: Date): string {
  return date.toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: false,
  })
}

export function formatTokens(n: number): string {
  if (n >= 1000) {
    return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  }
  return String(n)
}

/** Human-readable byte size — "523 B", "12.4 KB", "3.1 MB". */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1).replace(/\.0$/, '')} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(1).replace(/\.0$/, '')} GB`
}

export function formatDate(dateStr: string | null): Date {
  if (!dateStr) return new Date()
  return new Date(dateStr)
}

import { isToday, isYesterday, format } from 'date-fns'

// Me format date+time: "Today 14:32", "Yesterday 09:01", or "DD/MM/YYYY 14:32"
export function formatRelativeDate(dateStr: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const time = format(date, 'HH:mm')
  if (isToday(date)) return `Today ${time}`
  if (isYesterday(date)) return `Yesterday ${time}`
  return `${format(date, 'dd/MM/yyyy')} ${time}`
}

import type { ContentBlock } from '@/api/types'

/**
 * Extract copyable text from the last agent turn in a flat block list.
 *
 * A turn starts after the last `user` block. Within the turn, sleep-sentinel
 * text blocks (`<sleep>` / `[sleep]`) are stripped — they are internal signals,
 * not response content. For a text block that ends with a sentinel the prefix
 * before the sentinel is kept (it may still contain real content).
 *
 * Returns empty string when there is no assistant text in the last turn.
 */
export function lastTurnText(blocks: ContentBlock[]): string {
  // Find the index of the last user block — everything after it is the last turn
  let startIdx = 0
  for (let i = blocks.length - 1; i >= 0; i--) {
    if (blocks[i].type === 'user') {
      startIdx = i + 1
      break
    }
  }

  const turnBlocks = blocks.slice(startIdx)
  const parts: string[] = []

  for (const block of turnBlocks) {
    if (block.type !== 'text') continue
    const sleepPrefix = extractSleepPrefix(block.content)
    if (sleepPrefix !== null) {
      // Block ends with a sentinel — keep any real content before it
      if (sleepPrefix.length > 0) parts.push(sleepPrefix)
      // Skip the sentinel itself — it's an internal signal
    } else {
      parts.push(block.content)
    }
  }

  return parts.join('\n\n')
}
