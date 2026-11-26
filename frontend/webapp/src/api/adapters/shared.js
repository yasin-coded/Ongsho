import { lookupServiceKey } from '@/lib/services'
import { fmtCycleDueLabel, todayDhaka } from '@/lib/dates'
import { avatarColorFromId } from './me'
import { idStr, moneyFromApi, paginatedBody } from './common'
import { mapIncomingTransfer } from './transfers'

/** Recent payments preview on Shared Plans list cards (full list on member plan page). */
export const SHARED_LIST_HISTORY_PREVIEW = 3

function cycleFromApi(cycle) {
  if (!cycle) return { unit: 'month', count: 1 }
  if (cycle.count > 1) return { unit: cycle.unit, count: cycle.count }
  return { unit: cycle.unit, count: 1 }
}

function mapMemberHistoryRow(h, cycle) {
  const dueDate = h.due_date ?? (h.month ? `${h.month}-01` : null)
  return {
    id: idStr(h.due_id ?? h.id),
    dueDate,
    monthLabel: dueDate ? fmtCycleDueLabel(dueDate, cycle) : h.month ? fmtCycleDueLabel(`${h.month}-01`, cycle) : '',
    amount: moneyFromApi(h.amount),
    status: h.status,
    method: h.method ?? null,
    tid: h.transaction_id ?? null,
    waiverNote: h.waiver_note ?? null,
    rejectionReason: h.rejection_reason ?? null,
    wasRejected: Boolean(h.rejection_reason),
    paymentId: h.payment_id != null ? idStr(h.payment_id) : null,
  }
}

function mapOpenDueRow(d, cycle) {
  const dueDate = d.due_date ?? (d.month ? `${d.month}-01` : null)
  return {
    id: idStr(d.due_id ?? d.id),
    amount: moneyFromApi(d.amount),
    dueDate,
    monthLabel: dueDate ? fmtCycleDueLabel(dueDate, cycle) : '',
    rejectionReason: d.rejection_reason ?? null,
  }
}

/** One row per due id (guards against bad API/mock duplicates). */
export function uniqueDueRows(rows) {
  const seen = new Set()
  return rows.filter((r, i) => {
    const key = r.id ?? `i-${i}-${r.dueDate}-${r.amount}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function mapRosterMember(m, myStatus) {
  const cycle = m.cycle_status && m.cycle_status !== 'none' ? m.cycle_status : null
  return {
    id: idStr(m.id),
    name: m.name,
    firstName: m.is_you ? 'You' : m.first_name,
    avatarColor: avatarColorFromId(m.avatar_id),
    isOwner: m.is_owner,
    isYou: m.is_you,
    status: cycle ?? (m.is_you ? myStatus : null),
  }
}

function effectiveMyStatus(row) {
  const st = row.my_status
  if (st && st !== 'none') return st
  if (row.status !== 'active') return st ?? 'none'
  const today = todayDhaka()
  const renewal = row.next_renewal
  if (!renewal || today > renewal) return st ?? 'none'
  const joined = row.me?.joined_on ?? row.joined_on
  if (joined && today < joined) return 'none'
  if ((row.open_dues_count ?? 0) > 0) return 'due'
  const openAmount = moneyFromApi(row.open_amount) ?? 0
  const pendingAmount = moneyFromApi(row.pending_amount) ?? 0
  if (openAmount > 0) return 'due'
  if (pendingAmount > 0) return 'pending'
  return 'due'
}

export function memberSharedStatus(plan) {
  if (plan.myStatus === 'paid' || plan.myStatus === 'waived') return plan.myStatus === 'waived' ? 'waived' : 'paid'
  if (plan.openDues?.length) return 'due'
  if (plan.pendingAmount) return 'pending'
  if (plan.myStatus === 'due') return 'due'
  if (plan.myStatus === 'pending') return 'pending'
  if (plan.myStatus === 'none') return 'none'
  return 'none'
}

export function mapMySharedSummary(row, meUserId) {
  const subId = row.plan_id
  const priceBdt = row.price_now?.amount_bdt ? moneyFromApi(row.price_now.amount_bdt) : null
  const openAmount = moneyFromApi(row.open_amount) ?? 0
  const pendingAmount = moneyFromApi(row.pending_amount) ?? 0
  const myShare = moneyFromApi(row.my_share) ?? openAmount ?? 0
  const cycle = cycleFromApi(row.cycle)
  let openDues = uniqueDueRows((row.open_dues ?? []).map((d) => mapOpenDueRow(d, cycle)))
  const settled = row.my_status === 'paid' || row.my_status === 'waived'
  if (settled) {
    openDues = []
  } else if (!openDues.length && (row.open_dues_count ?? 0) > 0 && openAmount > 0) {
    openDues.push({ id: `${subId}-open`, amount: openAmount, dueDate: null, monthLabel: '' })
  }
  const history = (row.history ?? [])
    .map((h) => mapMemberHistoryRow(h, cycle))
    .sort((a, b) => (b.dueDate ?? '').localeCompare(a.dueDate ?? ''))
    .slice(0, SHARED_LIST_HISTORY_PREVIEW)
  return {
    id: idStr(subId),
    planName: row.plan_name,
    serviceKey: lookupServiceKey(row.service_name?.name ?? ''),
    serviceName: row.service_name?.name,
    cycle: cycleFromApi(row.cycle),
    owner: {
      name: row.owner?.name,
      firstName: row.owner?.first_name,
      avatarColor: avatarColorFromId(row.owner?.avatar_id),
    },
    myShare,
    myStatus: effectiveMyStatus(row),
    nextRenewal: row.next_renewal,
    method: row.recommended_method,
    note: row.note ?? '',
    openDues,
    pendingAmount,
    earliestOpenDue: null,
    members: (row.members ?? []).map((m) => mapRosterMember(m, row.my_status)),
    history,
    totalSpent: moneyFromApi(row.total_spent) ?? 0,
    me: {
      memberId: row.me?.member_id != null ? idStr(row.me.member_id) : null,
      status: row.me?.status ?? null,
      joinedOn: row.me?.joined_on ?? null,
      name: row.me?.name ?? row.members?.find((m) => m.is_you)?.name ?? '',
      firstName: 'You',
      avatarColor: avatarColorFromId(meUserId),
      leaveRequested: Boolean(row.leave_requested ?? row.me?.status === 'leave_requested'),
      leaveRequestedAt: row.leave_requested_at ?? row.me?.leave_requested_at ?? null,
    },
    price: priceBdt ? { amount: priceBdt } : { amount: myShare },
    seats: row.seats_taken ?? row.seats,
  }
}

export function mapMySharedTotals(t) {
  return {
    shares: moneyFromApi(t.shares) ?? 0,
    planCount: t.plan_count ?? 0,
    dueNow: moneyFromApi(t.due_now) ?? 0,
    waiting: moneyFromApi(t.waiting) ?? 0,
    dueNames: t.due_names ?? [],
    waitingNames: t.waiting_names ?? [],
    dueCount: t.due_count,
    pendingCount: t.pending_count,
    paidUpCount: t.paid_up_count,
  }
}

export function mapMySharedList(body, meUserId) {
  const page = paginatedBody(body)
  return {
    ...page,
    items: page.items.map((r) => mapMySharedSummary(r, meUserId)),
    counts: page.counts ?? body.counts,
    totals: mapMySharedTotals(body.totals ?? {}),
  }
}

export function mapMySharedPlanDetail(row, meUserId) {
  const base = mapMySharedSummary(row, meUserId)
  const openAmount = moneyFromApi(row.open_amount) ?? 0
  const cycle = cycleFromApi(row.cycle)
  let openDues = uniqueDueRows((row.open_dues ?? []).map((d) => mapOpenDueRow(d, cycle)))
  if (base.myStatus === 'paid' || base.myStatus === 'waived') {
    openDues = []
  } else if (!openDues.length && (row.open_dues_count ?? 0) > 0 && openAmount > 0) {
    openDues.push({ id: `${idStr(row.plan_id)}-open`, amount: openAmount, dueDate: null, monthLabel: '' })
  }
  const history = (row.history ?? []).map((h) => mapMemberHistoryRow(h, base.cycle))
  const members = (row.members ?? []).map((m) => mapRosterMember(m, base.myStatus))
  const coverable = uniqueDueRows(
    (row.coverable ?? []).map((c) => {
      const dueDate = c.due_date ?? (c.month ? `${c.month}-01` : null)
      return {
        id: idStr(c.due_id),
        name: c.first_name,
        amount: moneyFromApi(c.amount),
        dueDate,
        monthLabel: dueDate ? fmtCycleDueLabel(dueDate, base.cycle) : '',
        isOwnerSeat: Boolean(c.is_owner_seat),
        ownerFirstName: c.owner_first_name ?? base.owner?.firstName ?? null,
      }
    }),
  )
  const ious = (row.ious ?? []).map((i) => ({
    text: i.you_owe ? `You owe ${i.other?.first_name} ` : `${i.other?.first_name} owes you `,
    amount: moneyFromApi(i.amount),
    youOwe: i.you_owe,
  }))
  return {
    ...base,
    mode: row.mode,
    openDues,
    history,
    members,
    coverable,
    ious,
    totalSpent: moneyFromApi(row.total_spent) ?? 0,
    pendingSince: row.pending_since,
    lastRejection: row.last_rejection,
    canRequestLeave: row.can_request_leave ?? true,
    incomingTransfer: mapIncomingTransfer(row.incoming_transfer),
    me: {
      ...base.me,
      memberId: row.me?.member_id != null ? idStr(row.me.member_id) : base.me.memberId,
      status: row.me?.status ?? base.me.status,
      joinedOn: row.me?.joined_on ?? base.me.joinedOn,
      leaveRequested: Boolean(row.leave_requested ?? row.me?.status === 'leave_requested'),
      leaveRequestedAt: row.leave_requested_at ?? row.me?.leave_requested_at ?? base.me.leaveRequestedAt,
    },
  }
}
