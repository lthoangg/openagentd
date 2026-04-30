/**
 * useKeyboardShortcuts — registers window-level Ctrl+key handlers.
 *
 * Shortcuts map: key (lowercase) → handler function.
 * All shortcuts require Ctrl (not Meta) to avoid clashing with OS shortcuts.
 *
 * Usage:
 *   useKeyboardShortcuts({
 *     a: () => setShowAgentInfo(v => !v),
 *     b: () => sidebar.toggle(),
 *   })
 */

import { useEffect, useLayoutEffect, useRef } from 'react'

type ShortcutMap = Partial<Record<string, () => void>>

export function useKeyboardShortcuts(shortcuts: ShortcutMap): void {
  // Keep ref in sync with the latest shortcuts map without re-registering
  // the event listener. useLayoutEffect runs synchronously after DOM mutations
  // so the ref is always current before any user interaction.
  const ref = useRef(shortcuts)
  useLayoutEffect(() => {
    ref.current = shortcuts
  })

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.ctrlKey || e.metaKey) return
      const fn = ref.current[e.key.toLowerCase()]
      if (fn) {
        e.preventDefault()
        fn()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, []) // runs once — ref always has latest shortcuts
}
