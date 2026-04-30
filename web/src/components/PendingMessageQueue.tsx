import { X, Clock } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useTeamStore } from '@/stores/useTeamStore'
import type { InputBarHandle } from './InputBar'

interface PendingMessageQueueProps {
  /** Ref to the InputBar — used to restore text when user cancels a queued message. */
  inputRef: React.RefObject<InputBarHandle | null>
}

export function PendingMessageQueue({ inputRef }: PendingMessageQueueProps) {
  const messages = useTeamStore((s) => s._pendingMessages)
  const removePendingMessage = useTeamStore((s) => s.removePendingMessage)

  if (messages.length === 0) return null

  const handleRemove = (id: string, content: string) => {
    removePendingMessage(id)
    inputRef.current?.setValue(content)
    inputRef.current?.focus()
  }

  return (
    <div className="mb-2 flex flex-col gap-1 px-1">
      <AnimatePresence initial={false}>
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="flex items-center gap-2 rounded-xl border border-(--color-border) bg-(--color-surface-2)/60 px-3 py-2 shadow-sm backdrop-blur-sm"
          >
            <Clock size={12} className="shrink-0 text-(--color-text-muted)" aria-hidden="true" />

            <span className="min-w-0 flex-1 truncate text-xs text-(--color-text-muted)">
              {msg.content}
            </span>

            {msg.files && msg.files.length > 0 && (
              <span className="shrink-0 rounded-full bg-(--color-accent-subtle) px-1.5 py-0.5 text-[10px] text-(--color-accent)">
                +{msg.files.length}
              </span>
            )}

            <button
              onClick={() => handleRemove(msg.id, msg.content)}
              aria-label="Cancel queued message and restore to input"
              title="Cancel — restore to input"
              className="shrink-0 rounded-full p-0.5 text-(--color-text-muted) transition-colors hover:bg-(--color-accent-subtle) hover:text-(--color-text)"
            >
              <X size={12} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
