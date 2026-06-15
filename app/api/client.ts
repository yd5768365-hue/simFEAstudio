import type { z } from 'zod'

// ── Contract definition ──────────────────────────────────────

export interface Contract<
  P extends readonly string[] = readonly string[],
  B extends z.ZodTypeAny | undefined = undefined,
  R extends z.ZodTypeAny = z.ZodTypeAny,
> {
  method: 'GET' | 'POST' | 'DELETE'
  path: string
  params?: P
  body?: B
  response: R
  cache?: boolean
}

export function contract<
  P extends readonly string[],
  B extends z.ZodTypeAny,
  R extends z.ZodTypeAny,
>(config: {
  method: 'GET' | 'POST' | 'DELETE'
  path: string
  params?: P
  body?: B
  response: R
  cache?: boolean
}): Contract<P, B, R> {
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

const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

interface CacheEntry {
  data: unknown
  expires: number
}

export function createClient(baseUrl: string, appendLog: (line: string) => void) {
  const cache = new Map<string, CacheEntry>()

  async function request<C extends Contract>(
    c: C,
    options?: { params?: Record<string, string>; body?: unknown; skipCache?: boolean }
  ): Promise<z.output<C['response']>> {
    let url = `${baseUrl.replace(/\/+$/, '')}${c.path}`

    if (c.params && options?.params) {
      for (const param of c.params) {
        url = url.replace(`:${param}`, encodeURIComponent(options.params[param]))
      }
    }

    const cacheKey = `${c.method}:${url}`
    if (c.method === 'GET' && c.cache && !options?.skipCache) {
      const cached = cache.get(cacheKey)
      if (cached && Date.now() < cached.expires) {
        return cached.data as z.output<C['response']>
      }
      if (cached) cache.delete(cacheKey)
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

    const parsed = c.response.parse(json)

    if (c.method === 'GET' && c.cache) {
      cache.set(cacheKey, { data: parsed, expires: Date.now() + CACHE_TTL_MS })
    }

    return parsed
  }

  async function requestRaw(urlPath: string, options?: RequestInit): Promise<Response> {
    const url = `${baseUrl.replace(/\/+$/, '')}${urlPath}`
    return fetch(url, options)
  }

  return { request, requestRaw }
}
