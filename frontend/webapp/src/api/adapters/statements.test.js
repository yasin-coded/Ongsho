import { describe, expect, it } from 'vitest'
import { ApiError } from '../errors'
import { enrichStatementError } from './statements'

describe('statement errors', () => {
  it('maps nothing_to_report', () => {
    const err = enrichStatementError(new ApiError('raw', { code: 'nothing_to_report', status: 409 }))
    expect(err.message).toBe('Nothing to report for that month.')
  })

  it('keeps month field errors', () => {
    const err = enrichStatementError(
      new ApiError('Invalid month.', { status: 400, fields: { month: 'Use YYYY-MM.' } }),
    )
    expect(err.fields.month).toBe('Use YYYY-MM.')
  })
})