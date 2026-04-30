/**
 * ToolCall — quiet, aside-style record of a tool invocation.
 *
 * Visual language mirrors `Thinking`: no card, no gray fill, no tool-type
 * icon. A single left rule (`border-l` in `--color-border`) with left
 * padding marks the block as a margin note. Identity is carried by a
 * colored status dot (matching the `AgentCapabilities` vocabulary) +
 * either a tool-specific one-line summary or the bare tool name.
 *
 * Collapsed: dot + summary + optional done check.
 * Expanded: arguments (optionally as a bash code block) and/or result,
 * each with its own copy button; both sections share the left rule
 * indentation rather than living inside their own surfaces.
 *
 * The per-tool header/args customisation lives in ``./display.tsx``;
 * this module owns only the chrome (collapse, copy, status dot, motion).
 */

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronRight, Copy, Check } from 'lucide-react'
import { ToolResult } from '../ToolResult'
import { DURATIONS_S, EASINGS } from '@/lib/motion'
import { StatusDot } from './StatusDot'
import { getToolDisplay } from './display'
import type { ToolCallState } from './types'

interface ToolCallProps {
  name: string
  args?: string
  done?: boolean
  result?: string // tool response content
}

export function ToolCall({ name, args, done, result }: ToolCallProps) {
  // Hooks must be called unconditionally — before any early returns
  const [expanded, setExpanded] = useState(false)
  const [copiedArgs, setCopiedArgs] = useState(false)
  const [copiedResult, setCopiedResult] = useState(false)

  // Determine status: pending (no args yet) → running (args, not done) → done
  const isPending = args === undefined || args === null
  const isRunning = !isPending && !done
  const state: ToolCallState = done ? 'done' : isRunning ? 'running' : 'pending'

  const { header, headerTitle, formattedArgs, language, suppressResult } =
    getToolDisplay(name, args)
  const shownResult = suppressResult ? undefined : result

  const handleCopyArgs = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const text = formattedArgs || args || ''
    try {
      await navigator.clipboard.writeText(text)
      setCopiedArgs(true)
      setTimeout(() => setCopiedArgs(false), 1500)
    } catch {
      // ignore
    }
  }

  const handleCopyResult = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const text = result || ''
    try {
      await navigator.clipboard.writeText(text)
      setCopiedResult(true)
      setTimeout(() => setCopiedResult(false), 1500)
    } catch {
      // ignore
    }
  }

  const hasDetails = Boolean(formattedArgs || shownResult)
  const displayName = name || 'tool'

  return (
    <div className="tool-row-enter my-2 border-l border-(--color-border) pl-3">
      {/* Header row — text-first, no card chrome */}
      <button
        type="button"
        onClick={() => hasDetails && setExpanded((v) => !v)}
        className={`group -ml-1 flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-xs transition-colors duration-(--motion-fast) ease-(--ease-out) focus-visible:outline-2 focus-visible:outline-(--color-focus-ring) ${
          hasDetails
            ? 'cursor-pointer hover:text-(--color-text-2)'
            : 'cursor-default'
        }`}
        aria-expanded={expanded}
        aria-label={
          hasDetails
            ? expanded
              ? `Collapse ${displayName} details`
              : `Expand ${displayName} details`
            : `${displayName} (no details)`
        }
      >
        {hasDetails && (
          <ChevronRight
            size={12}
            className={`shrink-0 text-(--color-text-muted) transition-transform duration-(--motion-fast) ease-(--ease-out) ${expanded ? 'rotate-90' : ''}`}
            aria-hidden
          />
        )}
        <StatusDot state={state} />

        {/* Header content: tool-specific summary or fallback to tool name.
            Only argument values inside the header are italicised (via <Arg>);
            the verb/framing text stays upright. */}
        {header ? (
          <span className="flex-1 truncate text-(--color-text-2)" title={headerTitle ?? undefined}>
            {header}
          </span>
        ) : (
          <code className="flex-1 truncate font-mono font-medium text-(--color-text-2)">
            {displayName}
          </code>
        )}

        {isPending && (
          <span className="shrink-0 text-(--color-text-muted)">pending</span>
        )}
      </button>

      {/* Expandable details — no card, flows under the same left rule */}
      <AnimatePresence initial={false}>
        {expanded && hasDetails && (
          <motion.div
            key="tool-details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: DURATIONS_S.base, ease: EASINGS.out }}
            className="overflow-hidden"
          >
            <div className="mt-1.5 space-y-2 pl-1 pb-1">
              {/* Args section — caption + copy sit above a subtle panel so
                  the actual content (JSON / bash / text) gets a calm reading
                  surface without the heavy overlay we used before. */}
              {formattedArgs && (
                <section className="relative">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[10px] uppercase tracking-wider text-(--color-text-subtle)">
                      {language === 'bash' ? 'bash' : 'arguments'}
                    </span>
                    <button
                      onClick={handleCopyArgs}
                      className="rounded p-0.5 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text-2) focus-visible:outline-2 focus-visible:outline-(--color-focus-ring)"
                      aria-label="Copy arguments"
                      title="Copy"
                    >
                      {copiedArgs ? (
                        <Check size={12} className="text-(--color-success)" />
                      ) : (
                        <Copy size={12} />
                      )}
                    </button>
                  </div>
                  <div className="rounded-md border border-(--color-border) bg-(--color-surface-2) px-2.5 py-2">
                    {language === 'bash' ? (
                      <pre className="overflow-auto whitespace-pre-wrap break-all font-mono text-xs leading-relaxed text-(--color-accent)">
                        <span className="select-none text-(--color-text-muted)">$ </span>
                        {formattedArgs}
                      </pre>
                    ) : (
                      <pre className="overflow-auto whitespace-pre-wrap break-all font-mono text-xs leading-relaxed text-(--color-text-2)">
                        {formattedArgs}
                      </pre>
                    )}
                  </div>
                </section>
              )}

              {/* Result section — same caption + panel treatment as args. */}
              {shownResult && (
                <section className="relative">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[10px] uppercase tracking-wider text-(--color-text-subtle)">
                      result
                    </span>
                    <button
                      onClick={handleCopyResult}
                      className="rounded p-0.5 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text-2) focus-visible:outline-2 focus-visible:outline-(--color-focus-ring)"
                      aria-label="Copy result"
                      title="Copy result"
                    >
                      {copiedResult ? (
                        <Check size={12} className="text-(--color-success)" />
                      ) : (
                        <Copy size={12} />
                      )}
                    </button>
                  </div>
                  <div className="rounded-md border border-(--color-border) bg-(--color-surface-2) px-2.5 py-2 text-xs leading-relaxed text-(--color-text-2)">
                    <ToolResult toolName={name} result={shownResult} />
                  </div>
                </section>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
