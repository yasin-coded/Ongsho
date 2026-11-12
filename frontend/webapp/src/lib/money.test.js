import { describe, expect, it } from 'vitest'
import { fromPaisa, toPaisa } from './money'

describe('toPaisa / fromPaisa', () => {
  it('round-trips common amounts', () => {
    expect(fromPaisa(toPaisa('733.78'))).toBe('733.78')
    expect(fromPaisa(toPaisa('0.05'))).toBe('0.05')
    expect(fromPaisa(toPaisa('1200'))).toBe('1200.00')
  })

  it('rejects invalid strings', () => {
    expect(() => toPaisa('1e3')).toThrow()
    expect(() => toPaisa('1.234')).toThrow()
  })

  it('edge amounts', () => {
    expect(fromPaisa(toPaisa('0.05'))).toBe('0.05')
    expect(fromPaisa(toPaisa('1200'))).toBe('1200.00')
    expect(fromPaisa(toPaisa('733.78'))).toBe('733.78')
  })
})
