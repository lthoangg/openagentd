import { useEffect, useId } from 'react'
import { useSettingsStore } from '@/stores/useSettingsStore'

/** Shared guard for structured drafts and raw agent/skill/MCP editors. */
export function useUnsavedSettings(dirty: boolean): void {
  const id = useId()
  useEffect(() => {
    useSettingsStore.getState().setDraftDirty(id, dirty)
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    if (dirty) window.addEventListener('beforeunload', beforeUnload)
    return () => {
      useSettingsStore.getState().setDraftDirty(id, false)
      window.removeEventListener('beforeunload', beforeUnload)
    }
  }, [id, dirty])
}
