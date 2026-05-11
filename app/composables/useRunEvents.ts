export interface RunEventHandlers {
  onEvent: (payload: Record<string, unknown>) => void | Promise<void>
  onError?: () => void
}

export interface UseRunEventsOptions {
  baseUrl: string
}

export const useRunEvents = (options: UseRunEventsOptions) => {
  const { baseUrl } = options
  let eventSource: EventSource | null = null

  const closeRunEventStream = () => {
    eventSource?.close()
    eventSource = null
  }

  const openRunEventStream = (runId: string, handlers: RunEventHandlers) => {
    closeRunEventStream()
    eventSource = new EventSource(`${baseUrl}/v1/runs/${runId}/events`)
    eventSource.onmessage = async (event) => {
      const payload = JSON.parse(event.data)
      await handlers.onEvent(payload)
    }
    eventSource.onerror = () => {
      handlers.onError?.()
      closeRunEventStream()
    }
  }

  return {
    openRunEventStream,
    closeRunEventStream,
  }
}
