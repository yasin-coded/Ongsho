import { describe, expect, it } from 'vitest'
import { mapMySharedList, mapMySharedPlanDetail, memberSharedStatus } from './shared'
import { mapSubscriptionDetail } from './plan'
import { mapOwnerTransfer } from './transfers'

describe('shared adapter', () => {
  it('does not treat pre-billing as paid', () => {
    const plan = mapMySharedList(
      {
        results: [
          {
            plan_id: 10,
            plan_name: 'Apple Music',
            service_name: { name: 'Apple Music' },
            owner: { name: 'O', first_name: 'O', avatar_id: 'sage' },
            cycle: { unit: 'month', count: 1 },
            my_share: '200.00',
            my_status: 'none',
            open_amount: '0.00',
            pending_amount: '0.00',
            open_dues: [],
            members: [],
          },
        ],
        count: 1,
      },
      'u9',
    ).items[0]
    expect(memberSharedStatus(plan)).toBe('none')
    expect(plan.myShare).toBe(20000)
  })

  it('list cards map members and payment method', () => {
    const out = mapMySharedList(
      {
        results: [
          {
            plan_id: 2,
            plan_name: 'Netflix',
            service_name: { name: 'Netflix' },
            owner: { name: 'O', first_name: 'O', avatar_id: 'sage' },
            cycle: { unit: 'month', count: 1 },
            my_share: '250.00',
            my_status: 'due',
            open_amount: '250.00',
            open_dues_count: 1,
            pending_amount: '0.00',
            recommended_method: 'bkash',
            open_dues: [{ due_id: 4, due_date: '2026-02-05', amount: '250.00' }],
            members: [
              { id: 1, name: 'Owner', first_name: 'O', avatar_id: 'sage', is_owner: true, is_you: false },
              { id: 2, name: 'Test', first_name: 'Test', avatar_id: 'coral', is_owner: false, is_you: true },
            ],
          },
        ],
        count: 1,
      },
      'u9',
    )
    expect(out.items[0].method).toBe('bkash')
    expect(out.items[0].openDues[0].amount).toBe(25000)
    expect(out.items[0].members).toHaveLength(2)
    expect(out.items[0].members[1].firstName).toBe('You')
    const withTotals = mapMySharedList(
      {
        results: [],
        count: 0,
        totals: {
          due_names: ['Netflix'],
          waiting_names: [],
          due_count: 1,
          pending_count: 0,
          paid_up_count: 2,
          shares: '500.00',
          due_now: '250.00',
          waiting: '0.00',
        },
      },
      'u9',
    )
    expect(withTotals.totals.dueNames).toEqual(['Netflix'])
    expect(withTotals.totals.dueCount).toBe(1)
    expect(withTotals.totals.paidUpCount).toBe(2)
  })

  it('list cards include payment history and drop stale open dues when paid', () => {
    const item = mapMySharedList(
      {
        results: [
          {
            plan_id: 3,
            plan_name: 'ChatGPT Pro',
            service_name: { name: 'ChatGPT' },
            owner: { name: 'Y', first_name: 'Y', avatar_id: 'sage' },
            cycle: { unit: 'month', count: 1 },
            my_share: '250.00',
            my_status: 'paid',
            open_amount: '250.00',
            open_dues_count: 1,
            pending_amount: '0.00',
            open_dues: [],
            total_spent: '250.00',
            history: [
              {
                due_id: 12,
                month: '2026-11',
                due_date: '2026-11-15',
                amount: '250.00',
                status: 'paid',
                method: 'bkash',
                transaction_id: 'TID123',
              },
            ],
            members: [],
          },
        ],
        count: 1,
      },
      'u9',
    ).items[0]
    expect(item.openDues).toEqual([])
    expect(memberSharedStatus(item)).toBe('paid')
    expect(item.history).toHaveLength(1)
    expect(item.history[0].tid).toBe('TID123')
    expect(item.totalSpent).toBe(25000)
  })

  it('list cards keep only the three most recent payments', () => {
    const rows = Array.from({ length: 5 }, (_, i) => ({
      due_id: i + 1,
      month: `2026-0${i + 1}`,
      due_date: `2026-0${i + 1}-15`,
      amount: '250.00',
      status: 'paid',
    }))
    const item = mapMySharedList(
      {
        results: [
          {
            plan_id: 4,
            plan_name: 'Spotify',
            service_name: { name: 'Spotify' },
            owner: { name: 'Y', first_name: 'Y', avatar_id: 'sage' },
            cycle: { unit: 'month', count: 1 },
            my_share: '250.00',
            my_status: 'paid',
            open_amount: '0.00',
            pending_amount: '0.00',
            open_dues: [],
            total_spent: '1250.00',
            history: rows,
            members: [],
          },
        ],
        count: 1,
      },
      'u9',
    ).items[0]
    expect(item.history).toHaveLength(3)
    expect(item.history[0].id).toBe('5')
    expect(item.history[2].id).toBe('3')
  })

  it('labels weekly dues with the full date', () => {
    const out = mapMySharedPlanDetail(
      {
        plan_id: 9,
        plan_name: 'ChatGPT Pro',
        service_name: { name: 'ChatGPT' },
        owner: { name: 'Y', first_name: 'Y', avatar_id: 'sage' },
        cycle: { unit: 'week', count: 1 },
        my_share: '833.33',
        my_status: 'due',
        open_amount: '833.33',
        pending_amount: '0.00',
        open_dues: [{ due_id: 4, due_date: '2026-11-21', amount: '833.33' }],
        members: [],
        coverable: [],
        history: [],
      },
      'u9',
    )
    expect(out.openDues[0].monthLabel).toBe('21 Nov 2026')
  })

  it('maps member detail dues', () => {
    const out = mapMySharedPlanDetail(
      {
        plan_id: 2,
        plan_name: 'Netflix',
        service_name: { name: 'Netflix' },
        owner: { name: 'O', first_name: 'O', avatar_id: 'sage' },
        cycle: { unit: 'month', count: 1 },
        my_share: '250.00',
        my_status: 'due',
        open_amount: '250.00',
        pending_amount: '0.00',
        open_dues: [{ due_id: 4, due_date: '2026-02-05', amount: '250.00', month: '2026-02' }],
        members: [],
        coverable: [],
        ious: [{ you_owe: true, other: { first_name: 'Sam' }, amount: '100.00' }],
        history: [
          {
            due_id: 8,
            month: '2026-01',
            amount: '250.00',
            status: 'paid',
            method: 'bkash',
            transaction_id: 'TX1',
            waiver_note: null,
            rejection_reason: null,
            payment_id: 2,
          },
        ],
        incoming_transfer: {
          id: 5,
          created_at: '2026-11-01T12:00:00+06:00',
          from: { name: 'Sam', first_name: 'Sam', avatar_id: 'sage' },
        },
        total_spent: '500.00',
        next_renewal: '2026-12-13',
        leave_requested: false,
        leave_requested_at: null,
        can_request_leave: true,
        me: { member_id: 9, status: 'active', joined_on: '2026-01-01', leave_requested_at: null },
      },
      'u9',
    )
    expect(out.openDues[0].amount).toBe(25000)
    expect(out.openDues[0].monthLabel).toBe('Feb 2026')
    expect(out.ious[0].youOwe).toBe(true)
    expect(out.nextRenewal).toBe('2026-12-13')
    expect(out.canRequestLeave).toBe(true)
    expect(out.me.memberId).toBe('9')
    expect(out.me.joinedOn).toBe('2026-01-01')
    expect(out.history[0].method).toBe('bkash')
    expect(out.history[0].tid).toBe('TX1')
    expect(out.history[0].paymentId).toBe('2')
    expect(out.incomingTransfer.id).toBe('5')
    expect(out.incomingTransfer.from.firstName).toBe('Sam')
  })
})

describe('owner transfer on plan detail', () => {
  it('is wired through mapSubscriptionDetail', () => {
    const sub = {
      id: 1,
      plan_name: 'Family',
      service_name: { name: 'Spotify' },
      renewal_type: 'auto',
      transfer: { id: 9, status: 'pending', to: { id: 44, first_name: 'Lee' } },
    }
    expect(mapSubscriptionDetail(sub).transfer).toEqual(mapOwnerTransfer(sub.transfer))
  })
})
