import type { z } from 'zod'

export interface Contract<
  P extends readonly string[] = readonly string[],
  B extends z.ZodTypeAny | undefined = undefined,
  R extends z.ZodTypeAny = z.ZodTypeAny,
> {
  method: 'GET' | 'POST'
  path: string
  params?: P
  body?: B
  response: R
}

export function contract<
  P extends readonly string[],
  B extends z.ZodTypeAny,
  R extends z.ZodTypeAny,
>(config: { method: 'GET' | 'POST'; path: string; params?: P; body?: B; response: R }): Contract<P, B, R> {
  return config as Contract<P, B, R>
}

export function createClient(baseUrl: string, appendLog: (line: string) => void) {
  async function request<C extends Contract>(
    c: C,
    options?: { params?: Record<string, string>; body?: unknown }
  ): Promise<z.output<C['response']>> {
    let url = `${baseUrl.replace(/\/+$/, '')}${c.path}`

    if (c.params && options?.params) {
      for (const param of c.params) {
        url = url.replace(`:${param}`, encodeURIComponent(options.params[param]))
      }
    }

    let body: string | undefined
    if (c.body && options?.body !== undefined) {
      body = JSON.stringify(c.body.parse(options.body))
    }

    try {
      const res = await fetch(url, {
        method: c.method,
        headers: { 'Content-Type': 'application/json' },
        body,
      })

      if (!res.ok) {
        throw new Error(`request failed: ${res.status} ${await res.text()}`)
      }

      const json: unknown = await res.json()
      if (json && typeof json === 'object' && 'message' in json) {
        appendLog(`[服务响应] ${(json as { message: string }).message}`)
      }

      return c.response.parse(json)
    } catch (err) {
      appendLog(`[服务响应] ${err}`)
      throw err
    }
  }

  return { request }
}
