import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSimfeaClient } from './simfeaClient'

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('createSimfeaClient experiment files', () => {
  it('normalizes experiment list paths to project-relative learning paths', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        message: 'ok',
        data: {
          files: [
            { path: 'benchmarks/a.py', name: 'a.py', dir: 'learning/benchmarks', size: 1 },
            { path: 'learning/research/b.md', name: 'b.md', dir: 'learning/research', size: 2 },
          ],
        },
      })
    )

    const api = createSimfeaClient('http://api.test', () => {})
    const result = await api.listExperimentFiles()

    expect(result.data.files.map((file) => file.path)).toEqual([
      'learning/benchmarks/a.py',
      'learning/research/b.md',
    ])
  })

  it('reads experiment files without encoding path separators', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        message: 'ok',
        data: {
          content: 'note',
          path: 'learning/research/a note.md',
        },
      })
    )

    const api = createSimfeaClient('http://api.test', () => {})
    await api.readExperimentFile('learning/research/a note.md')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/v1/experiment/files/learning/research/a%20note.md',
      expect.any(Object)
    )
  })
})
