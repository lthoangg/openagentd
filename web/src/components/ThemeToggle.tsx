/**
 * ThemeToggle — three-way preference control (System / Light / Dark).
 *
 * Expanded: segmented control with all three options visible.
 * Collapsed: single icon button showing the current preference; click cycles
 * `system -> light -> dark -> system`.
 */
import { Monitor, Moon, Sun } from 'lucide-react'
import { useThemePreference } from '@/hooks/useThemePreference'
import type { ThemePreference } from '@/lib/theme'

const OPTIONS: ReadonlyArray<{
  value: ThemePreference
  label: string
  Icon: typeof Monitor
}> = [
  { value: 'system', label: 'System', Icon: Monitor },
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
]

const NEXT: Record<ThemePreference, ThemePreference> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
}

export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { preference, setPreference } = useThemePreference()

  if (collapsed) {
    const current = OPTIONS.find((o) => o.value === preference) ?? OPTIONS[0]
    const Icon = current.Icon
    return (
      <button
        type="button"
        onClick={() => setPreference(NEXT[preference])}
        title={`Theme: ${current.label} (click to cycle)`}
        aria-label={`Theme: ${current.label}. Click to cycle.`}
        className="interactive-weight flex h-8 w-8 items-center justify-center rounded-md text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
      >
        <Icon size={14} />
      </button>
    )
  }

  return (
    <div
      role="radiogroup"
      aria-label="Theme preference"
      className="flex items-center gap-0.5 rounded-lg border border-(--color-border) bg-(--color-bg) p-0.5"
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = preference === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setPreference(value)}
            title={label}
            className={`interactive-weight flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors ${
              active
                ? 'bg-(--color-accent-subtle) text-(--color-text)'
                : 'text-(--color-text-muted) hover:text-(--color-text)'
            }`}
          >
            <Icon size={12} />
            <span>{label}</span>
          </button>
        )
      })}
    </div>
  )
}
