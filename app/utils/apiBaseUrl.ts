export function resolveApiBaseUrl(configuredUrl: string | undefined, pageHostname: string) {
  const trimmed = configuredUrl?.trim().replace(/\/$/, '')
  if (trimmed) return trimmed

  const hostname = pageHostname || 'localhost'
  const apiHostname = hostname === 'localhost' || hostname === '127.0.0.1' ? hostname : 'localhost'
  return `http://${apiHostname}:8008`
}
