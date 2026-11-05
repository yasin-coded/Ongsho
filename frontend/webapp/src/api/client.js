// Mock transport. Every API module resolves through here so swapping in axios later
// changes this file only, never a component.

const initialMode = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('mock') : null

/** Dev-only switch: ?mock=empty | error | slow. Sticks for the session once set on first load. */
export function mockMode() {
  if (!import.meta.env.DEV || typeof window === 'undefined') return null
  return new URLSearchParams(window.location.search).get('mock') ?? initialMode
}

export class ApiError extends Error {
  constructor(message, { status = 400, fields = {} } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
  }
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const latency = () => (mockMode() === 'slow' ? 2600 : 300 + Math.floor(Math.random() * 300))

/** A read. `empty` gives the value to return under ?mock=empty. */
export async function read(compute, { empty } = {}) {
  await wait(latency())
  const mode = mockMode()
  if (mode === 'error') throw new ApiError('Could not reach Ongsho. Check your connection and try again.', { status: 503 })
  if (mode === 'empty' && empty !== undefined) return structuredClone(typeof empty === 'function' ? empty(compute()) : empty)
  return structuredClone(compute())
}

/** A write. Throw ApiError inside `apply` for validation failures. */
export async function write(apply) {
  await wait(Math.min(latency(), 700))
  const result = apply()
  return result === undefined ? { ok: true } : structuredClone(result)
}

export function paginate(list, page = 1, size = 5) {
  const pages = Math.max(1, Math.ceil(list.length / size))
  const current = Math.min(Math.max(1, page), pages)
  return { items: list.slice((current - 1) * size, current * size), page: current, pages, total: list.length, size }
}
