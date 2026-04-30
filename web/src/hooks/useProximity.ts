/**
 * useProximity — proximity fade for dense lists.
 *
 * Binary hover produces too much visual noise in long lists (10+ rows).
 * Proximity softens adjacent rows based on cursor distance, coexisting
 * with the standard `:hover` on the directly-hovered row.
 *
 * Usage:
 *
 *   const containerRef = useRef<HTMLDivElement>(null)
 *   const mouseY = useProximityTracker(containerRef)
 *   // ...per row:
 *   const { ref, intensity } = useProximityIntensity(mouseY, 120)
 *   <div ref={ref} style={{
 *     backgroundColor: `color-mix(in srgb, var(--color-accent-subtle) ${intensity * 100}%, transparent)`,
 *   }} />
 *
 * Respects `prefers-reduced-motion` — returns 0 for all rows when set.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { useReducedMotion } from './useReducedMotion'

/**
 * Track pointer Y relative to a container. Returns `null` when the pointer
 * is outside the container (rows fall back to idle styling). Updates are
 * rAF-throttled so a fast pointer doesn't flood re-renders.
 */
export function useProximityTracker(
  containerRef: RefObject<HTMLElement | null>,
): number | null {
  const [mouseY, setMouseY] = useState<number | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const handleMove = (event: PointerEvent) => {
      if (rafRef.current !== null) return
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null
        setMouseY(event.clientY)
      })
    }
    const handleLeave = () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      setMouseY(null)
    }

    el.addEventListener('pointermove', handleMove)
    el.addEventListener('pointerleave', handleLeave)
    return () => {
      el.removeEventListener('pointermove', handleMove)
      el.removeEventListener('pointerleave', handleLeave)
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [containerRef])

  return mouseY
}

export interface ProximityIntensity {
  /** Attach to the row element you want to fade. */
  ref: RefObject<HTMLElement | null>
  /** 0 (idle) … 1 (cursor over row center). */
  intensity: number
}

/**
 * Attach to a row to get a 0..1 intensity value derived from the pointer's
 * distance to the row's vertical center. `radius` (px) controls the
 * falloff distance. Under `prefers-reduced-motion`, intensity is always 0.
 *
 * The row measures itself via ResizeObserver and on scroll; intensity is
 * then pure math on `mouseY` vs cached `rowCenter` (no ref reads during
 * render).
 */
export function useProximityIntensity(
  mouseY: number | null,
  radius = 120,
): ProximityIntensity {
  const ref = useRef<HTMLElement | null>(null)
  const [rowCenter, setRowCenter] = useState<number | null>(null)
  const prefersReduced = useReducedMotion()

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return

    const measure = () => {
      const rect = el.getBoundingClientRect()
      setRowCenter(rect.top + rect.height / 2)
    }
    measure()

    const ro = new ResizeObserver(measure)
    ro.observe(el)
    window.addEventListener('scroll', measure, true)
    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', measure, true)
    }
  }, [])

  let intensity = 0
  if (!prefersReduced && mouseY !== null && rowCenter !== null) {
    const distance = Math.abs(mouseY - rowCenter)
    if (distance < radius) intensity = 1 - distance / radius
  }

  return { ref, intensity }
}
