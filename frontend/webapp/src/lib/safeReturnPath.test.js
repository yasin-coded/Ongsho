import { describe, expect, it } from 'vitest'
import { safeReturnPath } from './safeReturnPath'

describe('safeReturnPath', () => {
  it('allows /app and subpaths and /', () => {
    expect(safeReturnPath('/app')).toBe('/app')
    expect(safeReturnPath('/app/plans/1')).toBe('/app/plans/1')
    expect(safeReturnPath('/')).toBe('/')
  })

  it('rejects open redirects', () => {
    expect(safeReturnPath('https://evil.test/app')).toBeNull()
    expect(safeReturnPath('//evil.test/app')).toBeNull()
    expect(safeReturnPath('/\\evil.test')).toBeNull()
    expect(safeReturnPath('javascript:alert(1)')).toBeNull()
    expect(safeReturnPath('/login')).toBeNull()
    expect(safeReturnPath('/invite/abc')).toBeNull()
  })

  it('rejects encoded slashes and backslashes', () => {
    expect(safeReturnPath('/app%2f..%2fetc')).toBeNull()
    expect(safeReturnPath('%2Fapp')).toBeNull()
  })

  it('rejects null and empty', () => {
    expect(safeReturnPath(null)).toBeNull()
    expect(safeReturnPath('')).toBeNull()
    expect(safeReturnPath('   ')).toBeNull()
  })
})