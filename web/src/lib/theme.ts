/**
 * Theme — three-way light/dark/system preference with localStorage persistence.
 *
 * The `html` element carries `.dark` or `.light` (never both). When the stored
 * preference is `"system"`, the class tracks `prefers-color-scheme` and updates
 * when the user's OS setting changes.
 *
 * Pre-paint: `web/index.html` contains an inline script that applies the
 * correct class before the first paint to prevent a flash of wrong theme.
 * Keep the storage key and logic here in sync with that inline script.
 */

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'oa-theme'
const MEDIA_QUERY = '(prefers-color-scheme: dark)'

function isTheme(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

export function readStoredPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    if (isTheme(raw)) return raw
  } catch {
    // localStorage unavailable (SSR, privacy mode) — fall through
  }
  return 'system'
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === 'system') {
    return typeof window !== 'undefined' && window.matchMedia(MEDIA_QUERY).matches
      ? 'dark'
      : 'light'
  }
  return preference
}

export function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.classList.toggle('light', resolved === 'light')
}

export function setThemePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    // best-effort — still apply class below
  }
  applyTheme(resolveTheme(preference))
}

/**
 * Initialise theme tracking. Applies the current resolved theme and, if the
 * stored preference is `"system"`, subscribes to OS theme changes.
 *
 * Safe to call after the inline pre-paint script — it will re-apply the same
 * class, which is a no-op.
 *
 * Returns a cleanup function that removes the media-query listener.
 */
export function initTheme(): () => void {
  const preference = readStoredPreference()
  applyTheme(resolveTheme(preference))

  if (typeof window === 'undefined' || !window.matchMedia) {
    return () => {}
  }

  const mql = window.matchMedia(MEDIA_QUERY)
  const handler = () => {
    // Only react when the user prefers "system"; explicit picks are sticky.
    if (readStoredPreference() === 'system') {
      applyTheme(mql.matches ? 'dark' : 'light')
    }
  }

  mql.addEventListener('change', handler)
  return () => mql.removeEventListener('change', handler)
}
