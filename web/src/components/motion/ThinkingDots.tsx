import { cn } from '@/lib/utils'

interface ThinkingDotsProps {
  className?: string
  'aria-label'?: string
}

/**
 * Thinking indicator — three dots pulsing with a 200ms stagger. Signals
 * "the agent is reasoning but has not yet produced output". Distinct from
 * StreamingCursor: thinking dots appear when there is no text to show yet.
 *
 * Pair with a progressive text label (`Thinking`, `Reading`, `Searching`)
 * to tell the user what the agent is actually doing.
 */
export function ThinkingDots({
  className,
  'aria-label': ariaLabel = 'Thinking',
}: ThinkingDotsProps) {
  return (
    <span
      className={cn('inline-flex items-center gap-1', className)}
      role="status"
      aria-label={ariaLabel}
    >
      {[0, 200, 400].map((delay) => (
        <span
          key={delay}
          className="thinking-dot block h-1 w-1 rounded-full bg-current"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  )
}
