const MAX_LEN = 2048

/** Allow only same-app relative return paths (blocks open redirects). */
export function safeReturnPath(raw) {
  if (raw == null || typeof raw !== 'string') return null
  let path = raw.trim()
  if (!path || path.length > MAX_LEN) return null
  if (/%2f|%5c|%2F|%5C/i.test(path)) return null
  try {
    path = decodeURIComponent(path)
  } catch {
    return null
  }
  if (path.includes('\\') || path.includes('\u0000')) return null
  if (/^\s*javascript:/i.test(path) || /^\s*data:/i.test(path)) return null
  if (/^https?:/i.test(path) || path.startsWith('//')) return null
  if (!path.startsWith('/')) return null
  if (path.startsWith('/app') || path === '/') return path
  return null
}