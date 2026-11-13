import { lookupServiceKey } from '@/lib/services'
import { fmtMonth } from '@/lib/dates'
import { avatarColorFromId } from './me'
import { idStr, moneyFromApi, paginatedBody } from './common'

function cycleFromApi(cycle) {
  if (!cycle) return { unit: 'month', count: 1 }
  if (cycle.count > 1) return { unit: cycle.unit, count: cycle.count }
  return { unit: cycle.unit, count: 1 }
}

function mapRosterMember(m, myStatus) {
  return {
    id: idStr(m.id),
    name: m.name,
    firstName: m.is_you ? 'You' : m.first_name,
    avatarColor: avatarColorFromId(m.avatar_id),
    isOwner: m.is_owner,
    isYou: m.is_you,
    status: m.is_you ? myStatus : null,
  }
}

export function memberSharedStatus(plan) {
  if (plan.openDues?.length) return 'due'
  if (plan.pendingAmount) return 'pending'
  if (plan.myStatus === 'paid' || plan.myStatus === 'none') return 'paid'
  return plan.myStatus ?? 'paid'
}

export function mapMySharedSummary(row, meUserId) {
  const subId = row.plan_id
  const priceBdt = row.price_now?.amount_bdt ? moneyFromApi(row.price_now.amount_bdt) : null
  const openAmount = moneyFromApi(row.open_amount) ?? 0
  const pendingAmount = moneyFromApi(row.pending_amount) ?? 0
  const myShare = moneyFromApi(row.my_share) ?? openAmount ?? 0
  const openDues = (row.open_dues ?? []).map((d) => ({
    id: idStr(d.due_id ?? d.id),
    amount: moneyFromApi(d.amount),
    dueDate: d.due_date,
    monthLabel: d.due_date ? fmtMonth(d.due_date) : d.month,
  }))
  if (!openDues.length && (row.open_dues_count ?? 0) > 0 && openAmount > 0) {
    openDues.push({ id: `${subId}-open`, amount: openAmount, dueDate: null, monthLabel: '' })
  }
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
    myStatus: row.my_status,
    nextRenewal: row.next_renewal,
    method: row.recommended_method,
    note: row.note ?? '',
    openDues,
    pendingAmount,
    earliestOpenDue: null,
    members: (row.members ?? []).map((m) => mapRosterMember(m, row.my_status)),
    history: [],
    totalSpent: moneyFromApi(row.total_spent) ?? 0,
    me: {
      memberId: row.me?.member_id != null ? idStr(row.me.member_id) : null,
      name: row.me?.name ?? row.members?.find((m) => m.is_you)?.name ?? '',
      firstName: 'You',
      avatarColor: avatarColorFromId(meUserId),
      leaveRequested: Boolean(row.leave_requested),
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
  const openDues = (row.open_dues ?? []).map((d) => ({
    id: idStr(d.due_id),
    amount: moneyFromApi(d.amount),
    dueDate: d.due_date,
    monthLabel: d.due_date ? fmtMonth(d.due_date) : d.month,
  }))
  const history = (row.history ?? []).map((h) => ({
    id: idStr(h.due_id),
    dueDate: h.month ? `${h.month}-01` : null,
    monthLabel: h.month ? fmtMonth(`${h.month}-01`) : '',
    amount: moneyFromApi(h.amount),
    status: h.status,
    method: null,
    tid: null,
    waiverNote: null,
    rejectionReason: null,
    wasRejected: false,
  }))
  const members = (row.members ?? []).map((m) => mapRosterMember(m, base.myStatus))
  const coverable = (row.coverable ?? []).map((c) => ({
    id: idStr(c.due_id),
    name: c.first_name,
    amount: moneyFromApi(c.amount),
    monthLabel: c.month ? fmtMonth(`${c.month}-01`) : '',
  }))
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
    me: {
      ...base.me,
      leaveRequested: row.leave_requested,
      leaveRequestedAt: row.leave_requested_at,
    },
  }
}
