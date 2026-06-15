import { afterEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'
import { contract, createClient } from './client'

afterEach(() => {
  vi.restoreAllMocks()
})

const okResponseSchema = z.object({
  message: z.string(),
  data: z.object({
    path: z.string(),
  }),
})

describe('createClient path params', () => {
  it('keeps slashes for path-style params', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ message: 'ok', data: { path: 'learning/research/a note.md' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const c = contract({
      method: 'GET',
      path: '/v1/experiment/files/:filePath',
      params: ['filePath'] as const,
      pathParams: ['filePath'] as const,
      response: okResponseSchema,
    })

    const { request } = createClient('http://api.test/', () => {})
    await request(c, { params: { filePath: 'learning/research/a note.md' } })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/v1/experiment/files/learning/research/a%20note.md',
      expect.any(Object)
    )
  })

  it('encodes slashes for segment params by default', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ message: 'ok', data: { path: 'a/b' } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    )
    const c = contract({
      method: 'GET',
      path: '/v1/items/:itemId',
      params: ['itemId'] as const,
      response: okResponseSchema,
    })

    const { request } = createClient('http://api.test/', () => {})
    await request(c, { params: { itemId: 'a/b' } })

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/v1/items/a%2Fb', expect.any(Object))
  })
})
