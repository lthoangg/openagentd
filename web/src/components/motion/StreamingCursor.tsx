import { cn } from '@/lib/utils'

interface StreamingCursorProps {
  className?: string
  'aria-label'?: string
}

/**
 * Streaming cursor — blinking block that signals "the agent is generating
 * this token right now". Remove as soon as the stream emits `[DONE]` or a
 * tool call starts; a blinking cursor with no generation is a bug.
 *
 * Under `prefers-reduced-motion`, the CSS animation collapses to a static
 * block (see the global reduced-motion rule in index.css).
 */
export function StreamingCursor({
  className,
  'aria-label': ariaLabel = 'Generating…',
}: StreamingCursorProps) {
  return (
    <span
      className={cn('streaming-cursor', className)}
      role="status"
      aria-label={ariaLabel}
    />
  )
}
