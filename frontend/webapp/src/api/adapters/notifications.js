import { idStr } from './common'

const FILTER_FROM_API = { action: 'needs_action' }

export function mapNotificationItem(n) {
  return {
    id: idStr(n.id),
    kind: n.kind,
    title: n.title,
    body: n.body,
    createdAt: n.created_at,
    read: n.read,
    href: n.href,
    planId: n.plan_id ? idStr(n.plan_id) : null,
    group: FILTER_FROM_API[n.group] ?? n.group,
    needsAction: n.group === 'action' && !n.read,
    resolved: Boolean(n.read),
  }
}

export function mapNotificationCounts(counts) {
  const out = {}
  for (const [k, v] of Object.entries(counts ?? {})) {
    out[FILTER_FROM_API[k] ?? k] = v
  }
  return out
}
