/**
 * ToastStack — renders all toasts from ``useToastStore`` in the top-right
 * corner.  Handles its own mount/unmount animations and auto-dismiss is
 * driven by the store.
 *
 * Swipe right or up to dismiss.
 */
import { AnimatePresence, motion, useMotionValue, useTransform } from 'framer-motion'
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react'
import { useToastStore, type Toast } from '@/stores/useToastStore'

const TONE_STYLES: Record<
  Toast['tone'],
  { icon: React.ComponentType<{ size?: number; className?: string }>; iconClass: string }
> = {
  success: {
    icon: CheckCircle2,
    iconClass: 'text-(--color-success) opacity-60',
  },
  error: {
    icon: AlertCircle,
    iconClass: 'text-(--color-error)',
  },
  info: {
    icon: Info,
    iconClass: 'text-(--color-text-muted)',
  },
}

// Threshold (px) past which a drag is treated as a dismiss gesture
const SWIPE_THRESHOLD = 60

interface ToastItemProps {
  t: Toast
  dismiss: (id: string) => void
}

function ToastItem({ t, dismiss }: ToastItemProps) {
  const { icon: Icon, iconClass } = TONE_STYLES[t.tone]

  const x = useMotionValue(0)
  const y = useMotionValue(0)
  // Fade out as the user drags away
  const opacity = useTransform([x, y], ([latestX, latestY]: number[]) => {
    const dist = Math.max(Math.abs(latestX), Math.abs(latestY))
    return Math.max(0, 1 - dist / (SWIPE_THRESHOLD * 1.5))
  })

  function handleDragEnd() {
    const dx = x.get()
    const dy = y.get()
    // Dismiss on swipe right or swipe up
    if (dx > SWIPE_THRESHOLD || dy < -SWIPE_THRESHOLD) {
      dismiss(t.id)
    }
  }

  return (
    <motion.div
      key={t.id}
      layout
      style={{ x, y, opacity }}
      variants={{
        enter: { opacity: 0, y: -12, scale: 0.96, transition: { type: 'spring', damping: 26, stiffness: 320 } },
        visible: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring', damping: 26, stiffness: 320 } },
        exit: { opacity: 0, x: 40, scale: 0.96, transition: { type: 'tween', duration: 0.15, ease: 'easeIn' } },
      }}
      initial="enter"
      animate="visible"
      exit="exit"
      drag
      dragConstraints={{ left: 0, right: 200, top: -200, bottom: 0 }}
      dragElastic={{ left: 0.05, right: 0.4, top: 0.4, bottom: 0.05 }}
      dragMomentum={false}
      onDragEnd={handleDragEnd}
      whileDrag={{ cursor: 'grabbing' }}
      className="pointer-events-auto flex cursor-grab items-start gap-3 rounded-xl bg-(--color-surface-2) p-3 shadow-xl ring-1 ring-(--color-border) select-none"
      role="status"
      aria-live="polite"
    >
      <Icon size={16} className={`mt-0.5 shrink-0 ${iconClass}`} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-(--color-text)">{t.title}</p>
        {t.description && (
          <p className="mt-0.5 text-xs text-(--color-text-muted)">{t.description}</p>
        )}
      </div>
      <button
        onClick={() => dismiss(t.id)}
        aria-label="Dismiss"
        className="shrink-0 rounded-md p-1 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
      >
        <X size={12} />
      </button>
    </motion.div>
  )
}

export function ToastStack() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  return (
    <div className="pointer-events-none fixed top-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <ToastItem key={t.id} t={t} dismiss={dismiss} />
        ))}
      </AnimatePresence>
    </div>
  )
}
