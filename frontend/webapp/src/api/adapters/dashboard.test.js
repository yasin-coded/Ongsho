import { describe, expect, it } from 'vitest'
import { composeDashboard, mapAttentionItem } from './dashboard'

describe('dashboard adapter', () => {
  it('composes summary and cards', () => {
    const out = composeDashboard(
      {
        first_name: 'A',
        spend: { total: '100.00', owned: '100.00', joined: '0.00', rows: [] },
        due_soon: { count: 0, total: '0.00', first: null, items: [] },
        rarely: { plans: [], yearly: '0.00' },
        attention: [{ kind: 'review', plan_id: 1, plan_name: 'N', count: 2, title: '2 payments', payload: {} }],
        next7: [],
        by_category: [{ name: 'Streaming', amount: '100.00' }],
      },
      [{ key: '2026-02', label: 'Feb', year: '2026', total: '100.00', kind: 'this', yearly_plans: [] }],
      [{ id: 1, plan_name: 'N', plan_mode: 'owner', currency: 'BDT', cycle_unit: 'month', cycle_count: 1, category: { id: 1, name: 'Streaming' }, price_now: { amount_bdt: '100.00', currency: 'BDT' }, member_count: 0, members: [] }],
      [],
      'u1',
    )
    expect(out.firstName).toBe('A')
    expect(out.spend.total).toBe(10000)
    expect(out.forecast[0].total).toBe(10000)
    expect(out.owned).toHaveLength(1)
  })

  it('maps invite attention', () => {
    const item = mapAttentionItem({
      kind: 'invite',
      plan_id: 1,
      plan_name: 'N',
      title: 'Invite from Sam',
      payload: { invite_id: 5 },
    })
    expect(item.inviteId).toBe('5')
  })
})
