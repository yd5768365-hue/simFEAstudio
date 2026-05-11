import { listen } from '@tauri-apps/api/event'

type Cleanup = () => void

export interface UseSidecarListenersOptions {
  appendLog: (line: string) => void
}

export const useSidecarListeners = (options: UseSidecarListenersOptions) => {
  const { appendLog } = options
  let cleanup: Cleanup | null = null

  const initSidecarListeners = async () => {
    const unlistenStdout = await listen<string>('sidecar-stdout', (event) => {
      if (event.payload?.length > 0 && event.payload !== '\r\n') {
        appendLog(event.payload)
      }
    })

    const unlistenStderr = await listen<string>('sidecar-stderr', (event) => {
      if (event.payload?.length > 0 && event.payload !== '\r\n') {
        appendLog(event.payload)
      }
    })

    cleanup = () => {
      unlistenStdout()
      unlistenStderr()
    }
  }

  const disposeSidecarListeners = () => {
    cleanup?.()
    cleanup = null
  }

  return {
    initSidecarListeners,
    disposeSidecarListeners,
  }
}
