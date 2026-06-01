import { describe, expect, it } from 'vitest'
import { resolveApiBaseUrl } from './apiBaseUrl'

describe('resolveApiBaseUrl', () => {
  it('uses localhost when the page is served from localhost', () => {
    expect(resolveApiBaseUrl(undefined, 'localhost')).toBe('http://localhost:8008')
  })

  it('uses localhost for Tauri custom protocol hostnames', () => {
    expect(resolveApiBaseUrl(undefined, 'tauri.localhost')).toBe('http://localhost:8008')
  })

  it('keeps an explicit configured URL', () => {
    expect(resolveApiBaseUrl('http://127.0.0.1:9000/', 'tauri.localhost')).toBe('http://127.0.0.1:9000')
  })
})
