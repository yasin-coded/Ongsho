import { lookupServiceKey } from '@/lib/services'
import { fmtMonth } from '@/lib/dates'
import { avatarColorFromId } from './me'
import { idStr, moneyFromApi, paginatedBody } from './common'

function mapCovers(covers) {
  return (covers ?? []).map((c) => ({
    dueId: idStr(c.due_id),
    memberId: c.member_id != null ? idStr(c.member_id) : undefined,
    name: c.member_first_name,
    self: Boolean(c.is_payer),
    amount: moneyFromApi(c.amount),
    monthLong: c.month,
  }))
}

export function mapReview(data) {
  const pending = (data.pending ?? []).map((p) => {
    const covers = mapCovers(p.covers)
    return {
      id: idStr(p.payment_id),
      memberId: idStr(p.payer?.id),
      name: p.payer?.name ?? '',
      firstName: p.payer?.first_name ?? '',
      email: p.payer?.email ?? '',
      avatarColor: avatarColorFromId(p.payer?.avatar_id),
      amount: moneyFromApi(p.amount),
      method: p.method,
      tid: p.transaction_id,
      submittedAt: p.submitted_at,
      leaveRequested: Boolean(p.payer?.leave_requested),
      covers,
      cycleLabel: covers.map((c) => c.monthLong).filter(Boolean).join(', '),
    }
  })
  const planName = data.plan?.plan_name
  const serviceName = data.plan?.service_name?.name
  const decided = (data.decided ?? []).map((d) => ({
    id: idStr(d.due_id),
    name: d.member?.first_name ?? '',
    firstName: d.member?.first_name ?? '',
    email: d.member?.email ?? '',
    avatarColor: avatarColorFromId(d.member?.avatar_id),
    isOwnerSeat: Boolean(d.member?.is_owner_seat),
    amount: moneyFromApi(d.amount),
    status: d.status,
    method: d.method,
    tid: d.transaction_id,
    decidedOn: d.paid_on,
    paymentId: d.payment_id ? idStr(d.payment_id) : null,
    waiverNote: d.waiver_note ?? null,
    recordedByOwner: d.recorded_by_owner,
  }))
  return {
    plan: {
      id: idStr(data.plan?.id),
      planName,
      mode: data.plan?.mode,
      serviceKey: lookupServiceKey(serviceName ?? planName ?? ''),
      serviceName,
      nextRenewal: data.plan?.next_renewal ?? null,
    },
    cycleLabel: data.cycle_month,
    chargeDueDate: data.charge_due_date,
    waiting: {
      count: data.waiting?.count ?? 0,
      total: moneyFromApi(data.waiting?.total) ?? 0,
    },
    confirmed: {
      amount: moneyFromApi(data.confirmed?.amount) ?? 0,
      expected: moneyFromApi(data.confirmed?.expected) ?? 0,
      members: data.confirmed?.members ?? 0,
    },
    stillDue: Array.isArray(data.still_due) ? data.still_due.length : data.still_due ?? 0,
    unpaid: (data.still_due ?? []).map((m) => ({
      dueId: idStr(m.due_id),
      memberId: m.member_id != null ? idStr(m.member_id) : undefined,
      name: m.name ?? '',
      firstName: m.first_name ?? '',
      email: m.email ?? '',
      avatarColor: avatarColorFromId(m.avatar_id),
      amount: moneyFromApi(m.amount),
      leaveRequested: Boolean(m.leave_requested),
    })),
    pending,
    decided,
  }
}

export function mapLedgerRow(row) {
  const dueDate = row.due_date
  return {
    id: idStr(row.due_id),
    chargeId: idStr(row.charge_id),
    month: row.month,
    monthLabel: dueDate ? fmtMonth(dueDate) : row.month,
    dueDate,
    memberId: idStr(row.member?.id),
    name: row.member?.name,
    firstName: row.member?.first_name,
    isOwnerSeat: row.member?.is_owner_seat,
    amount: moneyFromApi(row.amount),
    status: row.status,
    method: row.method,
    tid: row.transaction_id,
    paidOn: row.paid_on,
    recordedByOwner: row.recorded_by_owner,
    coveredBy: row.covered_by,
  }
}

export function mapLedgerResponse(body) {
  const page = paginatedBody(body)
  const totals = {}
  for (const [k, v] of Object.entries(body.totals ?? {})) {
    totals[k] = k === 'all' || ['paid', 'pending', 'due', 'waived'].includes(k) ? moneyFromApi(v) ?? 0 : v
  }
  return {
    ...page,
    items: page.items.map(mapLedgerRow),
    totals,
    months: body.months ?? [],
    people: (body.people ?? []).map((p) => ({ id: idStr(p.id), name: p.name })),
  }
}

export function mapMemberDetail(data) {
  const rows = (data.rows ?? []).map((r) => ({
    id: idStr(r.due_id ?? r.id),
    dueDate: r.due_date ?? (r.month ? `${r.month}-01` : null),
    monthLabel: r.month ? fmtMonth(`${r.month}-01`) : r.month_label ?? '',
    amount: moneyFromApi(r.amount_bdt ?? r.amount),
    status: r.status,
    method: r.method,
    tid: r.transaction_id,
    paymentId: r.payment_id ? idStr(r.payment_id) : null,
  }))
  return {
    id: idStr(data.id),
    userId: idStr(data.user_id),
    name: data.name,
    firstName: data.first_name,
    email: data.email,
    avatarColor: avatarColorFromId(data.avatar_id),
    isOwnerSeat: data.is_owner_seat,
    status: data.status,
    joinedOn: data.joined_on,
    leftOn: data.left_on,
    leaveRequested: Boolean(data.leave_requested_at),
    leaveRequestedAt: data.leave_requested_at,
    dueId: data.due_id ? idStr(data.due_id) : null,
    dueStatus: data.due_status,
    dueAmount: data.due_amount ? moneyFromApi(data.due_amount) : null,
    planId: idStr(data.plan_id),
    planName: data.plan_name,
    rows,
  }
}
