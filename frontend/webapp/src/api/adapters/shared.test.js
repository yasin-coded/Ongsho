import { describe, expect, it } from 'vitest'
import { mapMySharedList, mapMySharedPlanDetail } from './shared'

describe('shared adapter', () => {
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
        history: [],
        total_spent: '500.00',
      },
      'u9',
    )
    expect(out.openDues[0].amount).toBe(25000)
    expect(out.ious[0].youOwe).toBe(true)
  })
})
