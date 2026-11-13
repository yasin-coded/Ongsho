import { idStr } from './common'

const FILTER_FROM_API = { action: 'needs_action' }

export const RESOLVED_LABELS = {
  approved: 'Approved',
  rejected: 'Rejected',
  reversed: 'Reversed',
  joined: 'Joined',
  declined: 'Declined',
  cancelled: 'Cancelled',
  expired: 'Expired',
  accepted: 'Accepted',
  gone: 'Done',
  waived: 'Waived',
}

function mapAction(payload) {
  const action = payload?.action
  if (!action?.type) return null
  return {
    type: action.type,
    paymentId: action.payment_id != null ? idStr(action.payment_id) : undefined,
    inviteId: action.invite_id != null ? idStr(action.invite_id) : undefined,
    transferId: action.transfer_id != null ? idStr(action.transfer_id) : undefined,
    memberId: action.member_id != null ? idStr(action.member_id) : undefined,
    planId: action.plan_id != null ? idStr(action.plan_id) : undefined,
  }
}

export function mapResolved(value) {
  if (value == null) return null
  return RESOLVED_LABELS[value] ?? 'Done'
}

export function mapNotificationItem(n) {
  const group = FILTER_FROM_API[n.group] ?? n.group
  const action = mapAction(n.payload)
  const resolvedRaw = n.resolved
  return {
    id: idStr(n.id),
    kind: n.kind,
    title: n.title,
    detail: n.message ?? n.body,
    createdAt: n.created_at,
    readAt: n.read_at ?? (n.read ? n.created_at : null),
    read: Boolean(n.read_at ?? n.read),
    link: n.link ?? n.href,
    planId: n.plan_id ? idStr(n.plan_id) : action?.planId,
    group,
    needsAction: Boolean(n.needs_action ?? (group === 'needs_action' && !resolvedRaw)),
    resolved: mapResolved(resolvedRaw),
    resolvedKey: resolvedRaw,
    action,
  }
}

export function mapNotificationCounts(counts) {
  const out = {}
  for (const [k, v] of Object.entries(counts ?? {})) {
    const key = FILTER_FROM_API[k] ?? k
    out[key] = v
    if (k === 'action') out.action = v
  }
  return out
}
