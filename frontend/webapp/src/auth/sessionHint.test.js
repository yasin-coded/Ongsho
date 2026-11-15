/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest'
import { clearSessionHint, hasSessionHint, markHasSession } from './sessionHint'
import { shouldAttemptSessionRefresh } from './sessionBootstrap'

describe('session hint', () => {
  afterEach(() => {
    clearSessionHint()
    localStorage.clear()
  })

  it('starts anonymous without a hint', () => {
    expect(hasSessionHint()).toBe(false)
    expect(shouldAttemptSessionRefresh({ forceMock: false, hasSessionHint: false })).toBe(false)
  })

  it('attempts refresh when hint is set', () => {
    markHasSession()
    expect(hasSessionHint()).toBe(true)
    expect(shouldAttemptSessionRefresh({ forceMock: false, hasSessionHint: true })).toBe(true)
  })

  it('skips refresh in mock mode even with hint', () => {
    markHasSession()
    expect(shouldAttemptSessionRefresh({ forceMock: true, hasSessionHint: true })).toBe(false)
  })

  it('clears hint on logout path', () => {
    markHasSession()
    clearSessionHint()
    expect(hasSessionHint()).toBe(false)
  })
})