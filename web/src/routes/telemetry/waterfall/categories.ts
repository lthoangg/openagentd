/**
 * Tailwind class lookups for the span category swatches in the waterfall.
 * Kept separate from the React component so the colour palette is easy to
 * audit at a glance.
 */

import type { SpanCategory } from '@/utils/traceTree'

export function categoryDotClass(cat: SpanCategory): string {
  switch (cat) {
    case 'agent_run':
      return 'bg-(--color-accent)'
    case 'chat':
      return 'bg-sky-500'
    case 'tool':
      return 'bg-emerald-500'
    case 'summarization':
      return 'bg-purple-500'
    case 'title':
      return 'bg-amber-500'
    default:
      return 'bg-slate-400'
  }
}

export function categoryBarClass(cat: SpanCategory, isError: boolean): string {
  if (isError) return 'bg-(--color-danger)'
  switch (cat) {
    case 'agent_run':
      return 'bg-(--color-accent)'
    case 'chat':
      return 'bg-sky-500'
    case 'tool':
      return 'bg-emerald-500'
    case 'summarization':
      return 'bg-purple-500'
    case 'title':
      return 'bg-amber-500'
    default:
      return 'bg-slate-400'
  }
}
