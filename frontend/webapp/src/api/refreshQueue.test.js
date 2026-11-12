import { describe, expect, it, vi } from 'vitest'
import { onceRefresh, peekRefreshPromise, resetRefreshQueue } from './refreshQueue'

describe('refreshQueue', () => {
  it('coalesces concurrent refresh calls', async () => {
    resetRefreshQueue()
  const run = vi.fn(() => new Promise((resolve) => setTimeout(() => resolve('ok'), 20)))
    const a = onceRefresh(run)
    const b = onceRefresh(run)
    expect(peekRefreshPromise).toBeTruthy()
    expect(run).toHaveBeenCalledTimes(1)
    await expect(Promise.all([a, b])).resolves.toEqual(['ok', 'ok'])
    expect(peekRefreshPromise()).toBe(null)
  })

  it('runs again after the first finishes', async () => {
    resetRefreshQueue()
    const run = vi.fn().mockResolvedValue('x')
    await onceRefresh(run)
    await onceRefresh(run)
    expect(run).toHaveBeenCalledTimes(2)
  })

  it('failed refresh allows retry', async () => {
    resetRefreshQueue()
    const run = vi.fn().mockRejectedValueOnce(new Error('nope')).mockResolvedValueOnce('ok')
    await expect(onceRefresh(run)).rejects.toThrow('nope')
    await expect(onceRefresh(run)).resolves.toBe('ok')
  })
})
