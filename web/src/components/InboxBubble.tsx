/**
 * InboxBubble — renders inter-agent inbox messages.
 *
 * - Left-aligned, muted border (distinct from user bubbles)
 * - Markdown rendered via ReactMarkdown + remark-gfm
 * - Auto-collapses when content exceeds COLLAPSE_LINES
 *   Collapsed: first N lines + blur/fade peek + overlaid expand button
 *   Expanded:  full content + overlaid collapse button
 */

import { useState, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ChevronDown, ChevronUp } from 'lucide-react'

/** Me change N here to tune collapse threshold */
const COLLAPSE_LINES = 5

/** Me how many lines the fade overlay covers (visual peek depth) */
const FADE_LINES = 2

interface InboxBubbleProps {
  content: string
  fromAgent: string
  /** Compact sizing for split-view panels */
  compact?: boolean
}

export function InboxBubble({ content, fromAgent, compact = false }: InboxBubbleProps) {
  const [expanded, setExpanded] = useState(false)

  const label = fromAgent

  // Me strip "[agent_name]: " prefixes — label already shows sender
  const stripped = useMemo(
    () => content.replace(/^\[[\w-]+\]:\s*/gm, '').trim(),
    [content],
  )

  const lines = stripped.split('\n')
  const needsCollapse = lines.length > COLLAPSE_LINES

  // Me slice visible content when collapsed
  const visibleContent = needsCollapse && !expanded
    ? lines.slice(0, COLLAPSE_LINES).join('\n')
    : stripped

  // Me size tokens — compact vs normal
  const textSize  = compact ? 'text-xs'    : 'text-sm'
  const maxWidth  = compact ? 'max-w-[88%]' : 'max-w-[78%]'
  const padding   = compact ? 'px-3 py-2'  : 'px-4 py-3'
  const labelSize = compact ? 'text-[10px]' : 'text-xs'
  // Me fade height scales with compact mode
  const fadeHeight = compact
    ? `${FADE_LINES * 1.4}rem`
    : `${FADE_LINES * 1.6}rem`

  return (
    <div className="mb-4 flex justify-start">
      <div
         className={[
           maxWidth,
           padding,
           textSize,
           'relative rounded-2xl rounded-bl-sm',
           'border border-(--color-border) bg-(--color-surface-2)',
           'leading-relaxed text-(--color-text)',
           'overflow-hidden',
         ].join(' ')}
       >
         {/* Me header row: agent label + collapse toggle (top-right) */}
         <div className="mb-1.5 flex items-center justify-between gap-2">
           <p className={`${labelSize} font-semibold tracking-wide uppercase text-(--color-info) opacity-90`}>
             {label}
           </p>

           {needsCollapse && (
             <button
               onClick={() => setExpanded((v) => !v)}
               aria-expanded={expanded}
               title={expanded ? 'Collapse' : 'Expand'}
               className={[
                 'flex items-center justify-center shrink-0',
                 'rounded-md border border-(--color-border)',
                 'bg-(--color-bg) text-(--color-text-muted)',
                 compact ? 'h-4 w-4' : 'h-5 w-5',
                 'transition-all duration-150',
                 'hover:border-(--color-syn-operator) hover:text-(--color-syn-operator)',
                 'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-syn-operator)',
                 'active:scale-90',
               ].join(' ')}
             >
               {expanded
                 ? <ChevronUp size={compact ? 10 : 12} />
                 : <ChevronDown size={compact ? 10 : 12} />}
             </button>
           )}
         </div>

          {/* Me markdown content */}
          <div className="oa-prose">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" />
                ),
              }}
            >
              {visibleContent}
            </ReactMarkdown>
          </div>

         {/* Me gradient fade at bottom — only in collapsed state */}
         {needsCollapse && !expanded && (
           <div
             className="pointer-events-none absolute inset-x-0 bottom-0"
             style={{
               height: fadeHeight,
               background: `linear-gradient(to bottom, transparent 0%, var(--color-surface-2) 90%)`,
             }}
           />
         )}
      </div>
    </div>
  )
}
