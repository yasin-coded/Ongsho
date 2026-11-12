import { describe, expect, it } from 'vitest'
import { mapPublicInvite } from './invite'

describe('invite adapter', () => {
  it('maps public invite', () => {
    const out = mapPublicInvite(
      {
        id: 3,
        email: 'a@b.com',
        status: 'pending',
        expires_on: '2026-04-01',
        expired: false,
        plan_id: 7,
        plan_name: 'Spotify',
        seats: 4,
        from: 'Sam',
        share: '120.50',
        cycle: { unit: 'month', count: 1 },
        account_exists: false,
      },
      'tok',
    )
    expect(out.token).toBe('tok')
    expect(out.share).toBe(12050)
    expect(out.notFound).toBe(false)
  })
})
