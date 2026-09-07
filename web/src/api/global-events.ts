import { apiBaseUrl } from './base-url'
import { apiAuthHeaders } from './auth'
import { readSSE } from './sse'
import type { SSECallbacks } from './sse'

export interface GlobalEventCallbacks extends SSECallbacks {
  onOpen?: () => void
}

/** Open the app-lifetime event feed used by first-party clients. */
export function globalEventStream(callbacks: GlobalEventCallbacks, signal?: AbortSignal): void {
  const url = `${apiBaseUrl()}/events/stream`
  fetch(url, { signal, headers: apiAuthHeaders(url) })
    .then((res) => {
      if (!res.ok) throw new Error(`GET /events/stream failed: ${res.status}`)
      callbacks.onOpen?.()
      readSSE(res, callbacks)
    })
    .catch((err) => { if (err.name !== 'AbortError') callbacks.onError?.(err) })
}
