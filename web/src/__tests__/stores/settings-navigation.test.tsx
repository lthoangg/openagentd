import { afterEach, expect, it, mock } from 'bun:test'
import { act, cleanup, renderHook } from '@testing-library/react'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useUnsavedSettings } from '@/hooks/useUnsavedSettings'

mock.module('lucide-react', () => new Proxy({}, { get: () => () => null }))
afterEach(() => {
  cleanup()
  useSettingsStore.setState({ open: false, section: 'about', dirtyDrafts: {}, pendingNavigation: null })
})

it('does not close or navigate away from unsaved work until discarded', () => {
  useSettingsStore.setState({ open: true, section: 'automation' })
  renderHook(() => useUnsavedSettings(true))
  act(() => useSettingsStore.getState().setSection('providers'))
  expect(useSettingsStore.getState().section).toBe('automation')
  expect(useSettingsStore.getState().pendingNavigation).not.toBeNull()
  act(() => useSettingsStore.getState().resolvePendingNavigation(false))
  expect(useSettingsStore.getState().section).toBe('automation')
  act(() => useSettingsStore.getState().closeSettings())
  expect(useSettingsStore.getState().open).toBe(true)
  act(() => useSettingsStore.getState().resolvePendingNavigation(true))
  expect(useSettingsStore.getState().open).toBe(false)
})
