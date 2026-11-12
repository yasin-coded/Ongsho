import { isLive } from './modes'

export function delegate(liveMod, mockMod, name) {
  const liveFn = liveMod[name]
  const mockFn = mockMod[name]
  if (!liveFn || !mockFn) {
    throw new Error(`Missing live or mock export: ${name}`)
  }
  return (...args) => (isLive(name) ? liveFn(...args) : mockFn(...args))
}
