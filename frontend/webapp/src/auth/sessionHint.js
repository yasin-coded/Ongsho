const KEY = 'ongsho:hasSession'

/** Non-sensitive hint that this browser has logged in before (never stores tokens or PII). */
export function markHasSession() {
  try {
    localStorage.setItem(KEY, '1')
  } catch {
    /* quota / private mode */
  }
}

export function clearSessionHint() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}

export function hasSessionHint() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}