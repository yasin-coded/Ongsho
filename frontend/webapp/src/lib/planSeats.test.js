import { describe, expect, it } from 'vitest'
import { freeSeats, inviteReservesSeat } from './planSeats'

describe('planSeats', () => {
  it('counts expired invites as reserving a seat', () => {
    expect(inviteReservesSeat({ status: 'expired' })).toBe(true)
    expect(inviteReservesSeat({ status: 'declined' })).toBe(false)
  })

  it('subtracts reserved invites from free seats', () => {
    const plan = {
      seatsCap: 2,
      seatsTaken: 1,
      status: 'active',
      invites: [{ status: 'pending' }, { status: 'accepted' }],
    }
    expect(freeSeats(plan)).toBe(0)
  })
})
