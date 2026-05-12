import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { eventStreamUrl, useRunEvents } from './useRunEvents'

class MockEventSource {
  static CLOSED = 2
  static instances: MockEventSource[] = []

  onerror: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onopen: (() => void) | null = null
  readyState = 0
  url: string

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  close() {
    this.readyState = MockEventSource.CLOSED
  }
}

describe('eventStreamUrl', () => {
  it('omits from_seq for a fresh stream', () => {
    expect(eventStreamUrl('http://127.0.0.1:8008', 'run-001', 0)).toBe(
      'http://127.0.0.1:8008/v1/runs/run-001/events'
    )
  })

  it('adds from_seq for a reconnecting stream', () => {
    expect(eventStreamUrl('http://127.0.0.1:8008', 'run-001', 12)).toBe(
      'http://127.0.0.1:8008/v1/runs/run-001/events?from_seq=12'
    )
  })
})

describe('useRunEvents', () => {
  const originalEventSource = globalThis.EventSource

  beforeEach(() => {
    vi.useFakeTimers()
    MockEventSource.instances = []
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource
  })

  afterEach(() => {
    vi.useRealTimers()
    globalThis.EventSource = originalEventSource
  })

  it('reconnects from the latest received sequence', async () => {
    const { openRunEventStream } = useRunEvents({ baseUrl: 'http://127.0.0.1:8008' })
    const onEvent = vi.fn()

    openRunEventStream('run-001', { onEvent })
    expect(MockEventSource.instances[0].url).toBe('http://127.0.0.1:8008/v1/runs/run-001/events')

    await MockEventSource.instances[0].onmessage?.({
      data: JSON.stringify({ seq: 7, type: 'stdout', line: 'step 7' }),
    } as MessageEvent)
    MockEventSource.instances[0].readyState = MockEventSource.CLOSED
    MockEventSource.instances[0].onerror?.()
    await vi.advanceTimersByTimeAsync(1000)

    expect(MockEventSource.instances[1].url).toBe('http://127.0.0.1:8008/v1/runs/run-001/events?from_seq=7')
  })
})
