import { describe, expect, it } from 'vitest'
import { mapNotificationCounts, mapNotificationItem } from './notifications'

describe('notifications adapter', () => {
  it('maps action to needs_action', () => {
    const item = mapNotificationItem({ id: 1, kind: 'invite', title: 't', body: 'b', created_at: 'x', read: false, group: 'action' })
    expect(item.group).toBe('needs_action')
    expect(item.needsAction).toBe(true)
    expect(item.resolved).toBe(false)
  })

  it('maps counts', () => {
    expect(mapNotificationCounts({ action: 2, all: 5 }).needs_action).toBe(2)
  })
})
