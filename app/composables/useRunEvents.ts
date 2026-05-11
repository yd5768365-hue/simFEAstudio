export interface RunEventHandlers {
  onEvent: (payload: Record<string, unknown>) => void | Promise<void>
  onError?: () => void
}

export const useRunEvents = (apiBaseUrl: string) => {
  let eventSource: EventSource | null = null

  const closeRunEventStream = () => {
    eventSource?.close()
    eventSource = null
  }

  const openRunEventStream = (runId: string, handlers: RunEventHandlers) => {
    closeRunEventStream()
    eventSource = new EventSource(`${apiBaseUrl}/v1/runs/${runId}/events`)
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
