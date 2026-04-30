/**
 * Thinking — quiet, aside-style reasoning trace.
 *
 * Visual language:
 *   - No container/background/border chrome. A single left rule
 *     (`border-l` in `--color-border`) with left padding marks the block as
 *     a margin note, not a card.
 *   - Trigger is text-only: chevron + label + optional streaming dots.
 *     No brain/icon clichés.
 *
 * Label behaviour:
 *   - Default: "Reasoning".
 *   - When the first line of `content` has finalised (a newline arrived, OR
 *     a closing `**` for a leading bold heading), extract that line, strip
 *     common markdown, and use it as the label — provided it's ≤40 chars.
 *   - Lines longer than 40 chars fall back to "Reasoning" rather than
 *     truncating awkwardly mid-thought.
 *   - While streaming a partial first line, we show "Reasoning" + dots so
 *     the label doesn't thrash character-by-character.
 */

import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import { ThinkingDots } from './motion'
import { DURATIONS_S, EASINGS } from '@/lib/motion'

interface ThinkingProps {
  content: string
  isStreaming?: boolean
}

const MAX_LABEL_LEN = 40
const DEFAULT_LABEL = 'Reasoning'

/**
 * Has the first line of reasoning content finalised?
 *
 * Reasoning tokens arrive in multi-word chunks, not single characters, so
 * the concern isn't letter-level jitter. The concern is that a chunk may
 * contain a *partial* first line: the label would flip between successive
 * phrase prefixes ("Determining response" → "Determining response needs
 * for the user" → fallback to "Reasoning" once it exceeds 40 chars) until
 * the newline finally arrives. Gating on a completed first line — newline
 * or a closed leading `**bold**` heading — keeps the label stable until
 * we know what it should actually be.
 *
 * For non-streaming content (DB replay, finished turns) we always treat
 * whatever is there as finalised.
 */
function firstLineFinalised(content: string, isStreaming: boolean): boolean {
  if (!isStreaming) return true
  if (content.includes('\n')) return true
  const trimmed = content.trimStart()
  // Closed bold heading at the very start: `**...**`
  if (trimmed.startsWith('**')) {
    const rest = trimmed.slice(2)
    return rest.includes('**')
  }
  return false
}

/** Strip the most common leading markdown decorations from a single line. */
function stripLeadingMarkdown(line: string): string {
  let s = line.trim()
  // Bold wrapping: **text**
  const boldMatch = s.match(/^\*\*(.+?)\*\*\s*$/)
  if (boldMatch) return boldMatch[1].trim()
  // Italic wrapping: *text* or _text_
  const italicMatch = s.match(/^[*_](.+?)[*_]\s*$/)
  if (italicMatch) return italicMatch[1].trim()
  // ATX heading: leading `#`s
  s = s.replace(/^#{1,6}\s+/, '')
  // Blockquote/list marker: leading `>`, `-`, `*`, `+`, or digits like `1.`
  s = s.replace(/^(?:[>*+-]|\d+\.)\s+/, '')
  return s.trim()
}

interface Extracted {
  label: string
  /** True when the label was pulled from the content's first line — in
   *  that case the expanded body should omit that line to avoid repeating
   *  it underneath. */
  labelFromContent: boolean
}

function extract(content: string, isStreaming: boolean): Extracted {
  if (!content) return { label: DEFAULT_LABEL, labelFromContent: false }
  if (!firstLineFinalised(content, Boolean(isStreaming))) {
    return { label: DEFAULT_LABEL, labelFromContent: false }
  }

  // First non-empty line
  const firstLine = content
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l.length > 0)
  if (!firstLine) return { label: DEFAULT_LABEL, labelFromContent: false }

  const cleaned = stripLeadingMarkdown(firstLine)
  if (!cleaned) return { label: DEFAULT_LABEL, labelFromContent: false }
  if (cleaned.length > MAX_LABEL_LEN) {
    return { label: DEFAULT_LABEL, labelFromContent: false }
  }
  return { label: cleaned, labelFromContent: true }
}

/**
 * Drop the first non-empty line (and any blank lines immediately following
 * it) from content. Used when that first line was promoted to the header
 * label so the expanded body doesn't repeat it.
 */
function stripFirstLine(content: string): string {
  const lines = content.split('\n')
  let i = 0
  // Skip leading blank lines, then the first non-empty line
  while (i < lines.length && lines[i].trim() === '') i++
  if (i < lines.length) i++
  // Skip blank separator lines
  while (i < lines.length && lines[i].trim() === '') i++
  return lines.slice(i).join('\n')
}

export function Thinking({ content, isStreaming }: ThinkingProps) {
  const [expanded, setExpanded] = useState(false)

  const { label, body } = useMemo(() => {
    const { label, labelFromContent } = extract(content, Boolean(isStreaming))
    const body = labelFromContent ? stripFirstLine(content) : content
    // If stripping the first line leaves nothing, fall back to the full
    // content so there's always something to show when expanded.
    return { label, body: body.trim() ? body : content }
  }, [content, isStreaming])

  return (
    <div className="my-2 border-l border-(--color-border) pl-3">
      {/* Trigger — text-only, no card chrome */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="group -ml-1 flex items-center gap-1.5 rounded px-1 py-0.5 text-xs text-(--color-text-muted) transition-colors duration-(--motion-fast) ease-(--ease-out) hover:text-(--color-text-2) focus-visible:outline-2 focus-visible:outline-(--color-focus-ring)"
        aria-expanded={expanded}
        aria-label={expanded ? 'Collapse reasoning' : 'Expand reasoning'}
      >
        <ChevronRight
          size={12}
          className={`shrink-0 transition-transform duration-(--motion-fast) ease-(--ease-out) ${expanded ? 'rotate-90' : ''}`}
          aria-hidden
        />
        <span className="flex items-center gap-1.5 font-medium">
          <span>{label}</span>
          {isStreaming && (
            <ThinkingDots className="text-(--color-text-muted)" aria-label={`${label}…`} />
          )}
        </span>
      </button>

      {/* Expanded body — indented muted italic, no extra container */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="thinking-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: DURATIONS_S.base, ease: EASINGS.out }}
            className="overflow-hidden"
          >
            <p className="mt-1 whitespace-pre-wrap pb-1 pl-1 font-mono text-xs italic leading-relaxed text-(--color-text-muted)">
              {body}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
