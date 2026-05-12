export interface RunEventHandlers {
  onEvent: (payload: Record<string, unknown>) => void | Promise<void>
  onError?: () => void
  onReconnecting?: (attempt: number) => void
}

export interface UseRunEventsOptions {
  baseUrl: string
}

const MAX_RETRIES = 5
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

export const eventStreamUrl = (baseUrl: string, runId: string, lastSeq: number) => {
  const url = new URL(`/v1/runs/${runId}/events`, baseUrl)
  if (lastSeq > 0) {
    url.searchParams.set('from_seq', String(lastSeq))
  }
  return url.toString()
}

export const useRunEvents = (options: UseRunEventsOptions) => {
  const { baseUrl } = options
  let eventSource: EventSource | null = null
  let retryCount = 0
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let manualReconnect = false
  let lastSeq = 0

  const clearRetry = () => {
    retryCount = 0
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  const closeRunEventStream = () => {
    manualReconnect = false
    clearRetry()
    eventSource?.close()
    eventSource = null
    lastSeq = 0
  }

  const scheduleReconnect = (runId: string, handlers: RunEventHandlers) => {
    if (retryCount >= MAX_RETRIES) {
      handlers.onError?.()
      closeRunEventStream()
      return
    }
    retryCount++
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** (retryCount - 1), RECONNECT_MAX_MS)
    handlers.onReconnecting?.(retryCount)
    retryTimer = setTimeout(() => {
      connectStream(runId, handlers)
    }, delay)
  }

  const connectStream = (runId: string, handlers: RunEventHandlers) => {
    eventSource?.close()
    manualReconnect = true
    eventSource = new EventSource(eventStreamUrl(baseUrl, runId, lastSeq))

    eventSource.onopen = () => {
      clearRetry()
    }

    eventSource.onmessage = async (event) => {
      clearRetry()
      const payload = JSON.parse(event.data)
      if (typeof payload.seq === 'number') {
        lastSeq = Math.max(lastSeq, payload.seq)
      }
      await handlers.onEvent(payload)
    }

    eventSource.onerror = () => {
      if (eventSource?.readyState === EventSource.CLOSED && manualReconnect) {
        scheduleReconnect(runId, handlers)
      }
    }
  }

  const openRunEventStream = (runId: string, handlers: RunEventHandlers) => {
    closeRunEventStream()
    connectStream(runId, handlers)
  }

  return {
    openRunEventStream,
    closeRunEventStream,
  }
}
