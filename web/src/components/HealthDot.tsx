import { useHealthQuery } from '@/queries/useHealthQuery'

/**
 * Small connected/disconnected indicator dot.
 * - Green when connected
 * - Red when error
 * - Pulsing gray during initial load
 */
export function HealthDot() {
  const health = useHealthQuery()

  let bgColor = 'bg-(--color-text-muted)'
  let pulseClass = 'animate-pulse'

  if (health.isSuccess) {
    bgColor = 'bg-(--color-success)'
    pulseClass = ''
  } else if (health.isError) {
    bgColor = 'bg-(--color-error)'
    pulseClass = ''
  }

  return (
    <div
      className={`h-1.5 w-1.5 rounded-full ${bgColor} ${pulseClass}`}
      title={
        health.isSuccess
          ? 'Connected'
          : health.isError
            ? 'Backend error'
            : 'Connecting…'
      }
      aria-label={
        health.isSuccess
          ? 'Connected'
          : health.isError
            ? 'Backend error'
            : 'Connecting…'
      }
    />
  )
}
