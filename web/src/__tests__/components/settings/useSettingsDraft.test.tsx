import { afterEach, describe, expect, it, mock } from 'bun:test'
import { act, cleanup, renderHook } from '@testing-library/react'
import { useSettingsDraft } from '@/components/settings/useSettingsDraft'

mock.module('lucide-react', () => new Proxy({}, { get: () => () => null }))
afterEach(cleanup)

describe('settings draft preservation', () => {
  it('keeps unsaved edits when a remote snapshot changes', () => {
    const { result, rerender } = renderHook(({ data }) => useSettingsDraft({
      data, initial: { name: '' }, onSave: async (value) => value, successTitle: 'Saved',
    }), { initialProps: { data: { name: 'initial' } } })
    act(() => result.current.patch({ name: 'local edit' }))
    rerender({ data: { name: 'remote edit' } })
    expect(result.current.value.name).toBe('local edit')
    expect(result.current.dirty).toBe(true)
    act(() => result.current.reset())
    expect(result.current.value.name).toBe('remote edit')
  })

  it('preserves edits made during an in-flight save', async () => {
    let finish!: (value: { name: string }) => void
    const { result } = renderHook(() => useSettingsDraft({
      data: { name: 'initial' }, initial: { name: '' },
      onSave: () => new Promise<{ name: string }>((resolve) => { finish = resolve }),
      successTitle: 'Saved',
    }))
    act(() => result.current.patch({ name: 'first edit' }))
    let saving!: Promise<void>
    act(() => { saving = result.current.save() })
    act(() => result.current.patch({ name: 'second edit' }))
    await act(async () => { finish({ name: 'first edit' }); await saving })
    expect(result.current.value.name).toBe('second edit')
    expect(result.current.dirty).toBe(true)
  })
})
