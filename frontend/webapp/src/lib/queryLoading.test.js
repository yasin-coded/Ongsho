import { describe, expect, it } from 'vitest'
import { shouldShowInitialSkeleton } from './queryLoading'

describe('shouldShowInitialSkeleton', () => {
  it('is true only when pending without cached data', () => {
    expect(shouldShowInitialSkeleton({ isPending: true, data: undefined })).toBe(true)
    expect(shouldShowInitialSkeleton({ isPending: true, data: { ok: 1 } })).toBe(false)
    expect(shouldShowInitialSkeleton({ isPending: false, data: { ok: 1 }, isFetching: true })).toBe(false)
    expect(shouldShowInitialSkeleton({ isPending: false, data: undefined })).toBe(false)
  })
})
