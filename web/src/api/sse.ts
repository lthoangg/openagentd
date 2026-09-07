/**
 * SSE stream reader for fetch() responses.
 *
 * Wire format from backend (sse_starlette):
 *   event: <type>\n
 *   data: <json>\n
 *   \n
 *
 * Usage:
 *   const res = await fetch(url, { signal })
 *   readSSE(res, {
 *     onEvent: (type, data) => ...,
 *     onError: (err)        => ...,
 *     onDone:  ()           => ...,
 *   })
 */

export interface SSECallbacks {
  onEvent: (type: string, data: unknown) => void
  onError?: (err: Error) => void
  onParseError?: (err: Error) => void
  onDone?: () => void
}

export function readSSE(response: Response, callbacks: SSECallbacks): void {
  if (!response.body) {
    callbacks.onError?.(new Error('No response body'))
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  // Current event fields being accumulated
  let currentEvent = ''
  let currentData = ''

  const dispatchEvent = () => {
    if (!currentData) return
    let parsed: unknown
    try {
      parsed = JSON.parse(currentData)
    } catch {
      callbacks.onParseError?.(new Error(`SSE parse error: ${currentData}`))
      currentEvent = ''
      currentData = ''
      return
    }
    const embeddedType = parsed && typeof parsed === 'object' && 'type' in parsed && typeof parsed.type === 'string'
      ? parsed.type : 'unknown'
    const type = currentEvent || embeddedType
    currentEvent = ''
    currentData = ''
    callbacks.onEvent(type, parsed)
  }

  const processLine = (line: string) => {
    if (line === '') {
      // Empty line = event boundary — dispatch accumulated event
      dispatchEvent()
      return
    }
    if (line.startsWith('event:')) {
      currentEvent = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      const chunk = line.slice(5).trim()
      // Concatenate multi-line data (rare, but spec-compliant)
      currentData = currentData ? currentData + '\n' + chunk : chunk
    }
    // id: and retry: lines are intentionally ignored
  }

  const pump = async () => {
    try {
      while (true) {
        const { done, value } = await reader.read()

        if (done) {
          // Flush any remaining buffer
          const remaining = buf.trim()
          if (remaining) processLine(remaining)
          dispatchEvent()
          callbacks.onDone?.()
          return
        }

        buf += decoder.decode(value, { stream: true })

        // Process all complete lines (split on \n, keep last incomplete chunk)
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''          // last element may be incomplete

        for (const raw of lines) {
          processLine(raw.trimEnd())     // strip \r
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return
      callbacks.onError?.(err instanceof Error ? err : new Error(String(err)))
    } finally {
      reader.releaseLock()
    }
  }

  pump()
}
