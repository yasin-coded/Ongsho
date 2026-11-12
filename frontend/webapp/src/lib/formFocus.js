const FIELD_SELECTOR = '[aria-invalid="true"], input[aria-invalid="true"], select[aria-invalid="true"], textarea[aria-invalid="true"]'

export function focusFirstInvalid(root = document) {
  const el = (root instanceof Document ? root : document).querySelector(FIELD_SELECTOR)
  el?.focus()
}

export function formLevelMessage(serverFields, knownKeys) {
  const known = new Set(knownKeys)
  const extra = Object.entries(serverFields ?? {}).filter(([k]) => !known.has(k))
  if (!extra.length) return null
  return extra.map(([, msg]) => msg).join(' ')
}
