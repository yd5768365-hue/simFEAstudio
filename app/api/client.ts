import type { z } from 'zod'

// ── Contract definition ──────────────────────────────────────

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

// ── Structured errors ────────────────────────────────────────

export class ApiClientError extends Error {
  status: number
  body: unknown
  code: string

  constructor(status: number, message: string, body: unknown, code = 'API_ERROR') {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.body = body
    this.code = code
  }
}

export function extractValidationIssues(err: unknown): string[] {
  if (err instanceof ApiClientError) {
    const body = err.body as Record<string, unknown> | undefined
    if (body?.details && Array.isArray(body.details)) {
      return body.details.map((d: unknown) => String((d as Record<string, unknown>)?.msg ?? d))
    }
    return [err.message]
  }
  if (err instanceof Error) {
    return [err.message]
  }
  return [String(err)]
}

// ── Client ───────────────────────────────────────────────────

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

    const res = await fetch(url, {
      method: c.method,
      headers: { 'Content-Type': 'application/json' },
      body,
    })

    if (!res.ok) {
      let errorBody: unknown
      try {
        errorBody = await res.json()
      } catch {
        errorBody = await res.text().catch(() => '(no body)')
      }
      const msg =
        typeof errorBody === 'object' && errorBody !== null && 'message' in errorBody
          ? String((errorBody as Record<string, unknown>).message)
          : `request failed: ${res.status}`
      throw new ApiClientError(res.status, msg, errorBody)
    }

    const json: unknown = await res.json()
    if (json && typeof json === 'object' && 'message' in json) {
      appendLog(`[服务响应] ${(json as { message: string }).message}`)
    }

    return c.response.parse(json)
  }

  async function requestRaw(urlPath: string, options?: RequestInit): Promise<Response> {
    const url = `${baseUrl.replace(/\/+$/, '')}${urlPath}`
    return fetch(url, options)
  }

  return { request, requestRaw }
}
