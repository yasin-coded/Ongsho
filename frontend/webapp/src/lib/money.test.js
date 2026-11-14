import { describe, expect, it } from 'vitest'
import { fromPaisa, toPaisa } from './money'

describe('toPaisa / fromPaisa', () => {
  it('round-trips common amounts', () => {
    expect(fromPaisa(toPaisa('733.78'))).toBe('733.78')
    expect(fromPaisa(toPaisa('0.05'))).toBe('0.05')
    expect(fromPaisa(toPaisa('1200'))).toBe('1200.00')
    expect(toPaisa('125.0000')).toBe(12500)
    expect(toPaisa('122.5')).toBe(12250)
  })

  it('rejects invalid strings', () => {
    expect(() => toPaisa('1e3')).toThrow()
    expect(() => toPaisa('1.2.3')).toThrow()
    expect(() => toPaisa('')).toThrow()
  })

  it('edge amounts', () => {
    expect(fromPaisa(toPaisa('0.05'))).toBe('0.05')
    expect(fromPaisa(toPaisa('1200'))).toBe('1200.00')
    expect(fromPaisa(toPaisa('733.78'))).toBe('733.78')
  })
})
