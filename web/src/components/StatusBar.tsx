import { shortId, formatTokens } from '@/utils/format'
import type { AgentUsage } from '@/api/types'

interface StatusBarProps {
  sessionId: string | null
  agent?: string
  model?: string
  isStreaming?: boolean
  error?: string | null
  usage?: AgentUsage | null
}

export function StatusBar({
  sessionId,
  isStreaming,
  error,
  usage,
}: StatusBarProps) {
  return (
    <div className="flex items-center justify-between border-t border-(--color-border) bg-(--color-bg) px-4 py-1 text-xs text-(--color-text-subtle)">
      {/* Left: session ID */}
      <div className="flex items-center gap-2">
         {sessionId && (
           <span className="font-mono text-(--color-text-subtle)">
             {shortId(sessionId)}
           </span>
         )}
         {isStreaming && (
           <span className="flex items-center gap-1 text-(--color-text-2)">
             <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-(--color-accent)" />
             streaming
           </span>
         )}
       </div>

       {/* Center: error */}
       {error && (
         <span className="max-w-xs truncate text-(--color-error)">
           {error}
         </span>
       )}

       {/* Right: token count */}
       <div className="flex items-center gap-2">
         {usage && (
           <span className="text-(--color-text-subtle)">
             {formatTokens(usage.promptTokens)}p ·{' '}
             {formatTokens(usage.completionTokens)}c
             {usage.cachedTokens > 0 && (
               <> · {formatTokens(usage.cachedTokens)} cached</>
             )}
           </span>
         )}
         <span className="text-(--color-text-subtle)">Ctrl+N new</span>
       </div>
     </div>
   )
}
