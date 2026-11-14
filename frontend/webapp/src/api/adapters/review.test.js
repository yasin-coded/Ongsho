import { describe, expect, it } from 'vitest'
import { mapReview, mapLedgerResponse } from './review'

describe('review adapter', () => {
  it('maps pending payments', () => {
    const out = mapReview({
      plan: {
        id: 1,
        plan_name: 'Spotify Family',
        mode: 'owner',
        service_name: { name: 'Spotify' },
        next_renewal: '2026-12-13',
      },
      waiting: { count: 1, total: '500.00' },
      confirmed: { amount: '0.00', expected: '500.00', members: 1 },
      still_due: [{ id: 2 }],
      pending: [
        {
          payment_id: 9,
          payer: {
            id: 3,
            name: 'M',
            first_name: 'M',
            email: 'm@example.com',
            avatar_id: 'sage',
            leave_requested: true,
          },
          method: 'bkash',
          transaction_id: 'ABC123',
          amount: '500.00',
          submitted_at: '2026-01-01T10:00:00+06:00',
          covers: [{ due_id: 5, member_first_name: 'M', month: 'February', amount: '500.00' }],
        },
      ],
      decided: [
        {
          due_id: 7,
          payment_id: 4,
          member: { first_name: 'A', email: 'a@example.com', avatar_id: 'coral' },
          status: 'waived',
          amount: '100.00',
          waiver_note: 'Birthday',
        },
      ],
    })
    expect(out.pending[0].id).toBe('9')
    expect(out.pending[0].amount).toBe(50000)
    expect(out.pending[0].email).toBe('m@example.com')
    expect(out.pending[0].leaveRequested).toBe(true)
    expect(out.plan.serviceKey).toBe('spotify')
    expect(out.plan.nextRenewal).toBe('2026-12-13')
    expect(out.decided[0].waiverNote).toBe('Birthday')
    expect(out.decided[0].paymentId).toBe('4')
    expect(out.stillDue).toBe(1)
  })
})

describe('ledger adapter', () => {
  it('maps totals to paisa', () => {
    const out = mapLedgerResponse({
      results: [],
      count: 0,
      totals: { paid: '100.00', pending: '0.00', due: '50.00', all: '150.00' },
      months: [],
      people: [],
    })
    expect(out.totals.paid).toBe(10000)
  })
})
