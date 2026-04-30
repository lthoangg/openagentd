/**
 * useReducedMotion — single import path for the `prefers-reduced-motion`
 * query. Re-exports framer-motion's implementation so app code depends on
 * our path, not framer-motion's surface.
 *
 * The CSS layer in `index.css` already short-circuits transitions and
 * animations when the media query matches; use this hook only for
 * JS-driven motion (framer-motion variants, animation-derived layout,
 * custom rAF loops).
 */
export { useReducedMotion } from 'framer-motion'
