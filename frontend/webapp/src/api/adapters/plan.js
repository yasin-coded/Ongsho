import { cycleFromForm, nextRenewalDateForApi } from '@/mocks/schedule'
import { lookupServiceKey } from '@/lib/services'
import { categoryColor } from '@/lib/colors'
import { fmtMonth } from '@/lib/dates'
import { idStr, moneyFromApi, moneyToApi, rateFromApi, rateToApi, paginatedBody } from './common'
import { avatarColorFromId } from './me'
import { mapOwnerTransfer } from './transfers'

function cycleFromApi(unit, count) {
  if (count > 1) return { unit, count }
  return { unit: unit === 'month' && count === 1 ? 'month' : unit, count }
}

function renewalFromApi(renewalType) {
  return renewalType === 'fixed_term' ? 'fixed' : 'auto'
}

function renewalToApi(renewal) {
  return renewal === 'fixed' ? 'fixed_term' : 'auto'
}

function priceBlock(sub) {
  const pn = sub.price_now
  if (!pn) return { amount: 0, usdCents: null, rate: null }
  const amount = moneyFromApi(pn.amount_bdt ?? pn.amount) ?? 0
  if (pn.currency === 'USD') {
    const usdCents = moneyFromApi(pn.amount)
    const rate = rateFromApi(pn.rate)
    return { amount, usdCents, rate, currency: 'USD' }
  }
  return { amount, usdCents: null, rate: null, currency: 'BDT' }
}

function planHeadcount(sub, members = []) {
  return Math.max(Number(sub.member_count) || 0, Number(sub.seats_taken) || 0, members.length)
}

function isMultiMemberPlan(sub, members = []) {
  return planHeadcount(sub, members) > 1 || (sub.pending_invites?.length ?? 0) > 0
}

function statusPill(sub, members = []) {
  if (sub.status === 'trial') return { key: 'trial', label: 'Trial' }
  if (sub.status !== 'active') return { key: sub.status, label: sub.status }
  if (!isMultiMemberPlan(sub, members)) return { key: 'solo', label: 'Just me' }
  const pending = members.filter((m) => m.dueStatus === 'pending').length
  const due = members.filter((m) => m.dueStatus === 'due').length
  if (pending) return { key: 'review', label: `${pending} to review`, count: pending }
  if (due) return { key: 'due', label: `${due} due`, count: due }
  if (!members.length) return { key: 'empty', label: 'No members yet' }
  return { key: 'allpaid', label: 'All paid' }
}

export function mapMemberRow(row, meUserId) {
  return {
    id: idStr(row.id),
    userId: idStr(row.user_id),
    name: row.name,
    firstName: row.first_name ?? row.name?.split(' ')[0],
    email: row.email,
    avatarColor: avatarColorFromId(row.avatar_id),
    isOwnerSeat: row.is_owner_seat,
    dueStatus: row.due_status,
    dueAmount: row.due_amount ? moneyFromApi(row.due_amount) : null,
    leaveRequested: Boolean(row.leave_requested_at),
    leaveRequestedAt: row.leave_requested_at,
    pendingPaymentId: row.pending_payment_id ? idStr(row.pending_payment_id) : null,
    isYou: meUserId && String(row.user_id) === String(meUserId),
    status: row.status,
    joinedOn: row.joined_on,
  }
}

export function mapSubscriptionSummary(sub, members = [], meUserId = null) {
  const serviceName = sub.service_name?.name ?? ''
  const category = sub.category
  const price = priceBlock(sub)
  const shared = isMultiMemberPlan(sub, members)
  const monthly = moneyFromApi(sub.monthly_cost) ?? price.amount
  return {
    id: idStr(sub.id),
    planName: sub.plan_name,
    serviceName,
    serviceKey: lookupServiceKey(serviceName),
    mode: sub.plan_mode,
    status: sub.status,
    cycle: cycleFromApi(sub.cycle_unit, sub.cycle_count),
    currency: sub.currency,
    price,
    perSeat: sub.per_seat ? moneyFromApi(sub.per_seat) : shared && members.length ? Math.floor(price.amount / Math.max(members.length, 1)) : price.amount,
    seatsCap: sub.seats ?? members.length ?? 1,
    seatsTaken: sub.seats_taken ?? members.length,
    shared,
    nextRenewal: sub.next_renewal ?? null,
    trialEnd: sub.trial_end_date ?? null,
    pausedOn: sub.paused_on ?? null,
    members,
    statusPill: statusPill(sub, members),
    rarelyUsed: sub.rarely_used,
    method: sub.recommended_method,
    note: sub.note ?? '',
    category: category ? { id: idStr(category.id), name: category.name, color: categoryColor(category.name) } : null,
    pendingCount: sub.pending_count ?? members.filter((m) => m.dueStatus === 'pending').length,
    chargeId: null,
    monthly,
  }
}

export function mapListResponse(body, membersByPlan = new Map(), meUserId = null) {
  const page = paginatedBody(body)
  const counts = body.counts ?? { all: page.total, review: 0, rarely: 0 }
  const apiTotals = body.totals ?? {}
  const totals = {
    count: apiTotals.count ?? page.total,
    toProviders: moneyFromApi(apiTotals.to_providers) ?? 0,
    confirmed: moneyFromApi(apiTotals.confirmed) ?? 0,
    pending: moneyFromApi(apiTotals.pending) ?? 0,
    expected: moneyFromApi(apiTotals.expected) ?? 0,
    reviewCount: apiTotals.review_count ?? counts.review ?? 0,
    reviewPlans: (apiTotals.review_plans ?? []).map((p) => ({
      id: idStr(p.id),
      planName: p.plan_name,
      count: p.count,
    })),
    rarelyCount: counts.rarely ?? 0,
  }
  const totalsMeta = {
    memberCollections: true,
    reviewDetail: true,
  }
  const items = page.items.map((sub) => {
    const members = (sub.members ?? membersByPlan.get(sub.id) ?? []).map((m) =>
      m.user_id !== undefined ? mapMemberRow(m, meUserId) : m,
    )
    return mapSubscriptionSummary(sub, members, meUserId)
  })
  return { ...page, items, counts, totals, totalsMeta }
}

function mapActivityRow(row) {
  const ts = row.created_at
  return {
    id: row.id != null ? idStr(row.id) : undefined,
    text: row.text,
    tone: row.tone,
    amount: row.amount ? moneyFromApi(row.amount) : null,
    createdAt: ts,
    ts,
  }
}

function mapIouRow(row) {
  return {
    debtorId: idStr(row.debtor?.id),
    creditorId: idStr(row.creditor?.id),
    debtor: row.debtor?.first_name ?? row.debtor?.name,
    creditor: row.creditor?.first_name ?? row.creditor?.name,
    amount: moneyFromApi(row.amount),
  }
}

function mapChargeRow(ch) {
  return {
    id: idStr(ch.id),
    dueDate: ch.due_date,
    monthLabel: ch.due_date ? fmtMonth(ch.due_date) : ch.month,
    amount: moneyFromApi(ch.amount_bdt ?? ch.amount),
    locked: ch.locked,
    status: ch.status,
    hasPayments: ch.has_payments,
  }
}

export function mapSubscriptionDetail(sub, extras = {}) {
  const members = extras.members ?? []
  const summary = mapSubscriptionSummary(
    { ...sub, member_count: members.length, seats: sub.seats ?? extras.seats, seats_taken: extras.seatsTaken ?? members.length, per_seat: sub.per_seat },
    members,
    extras.meUserId,
  )
  const price = priceBlock(sub)
  const prices = (extras.priceChanges ?? []).map((p) => ({
    id: idStr(p.id),
    effectiveFrom: p.effective_from,
    amount: moneyFromApi(p.amount_bdt ?? p.amount),
    usdCents: p.currency === 'USD' ? moneyFromApi(p.amount) : null,
    rate: p.exchange_rate ? rateFromApi(p.exchange_rate) : null,
  }))
  const collected = sub.collected != null ? moneyFromApi(sub.collected) : extras.collected != null ? moneyFromApi(extras.collected) : null
  const expected = sub.expected != null ? moneyFromApi(sub.expected) : extras.expected != null ? moneyFromApi(extras.expected) : null
  const csf = sub.confirmed_so_far
  const confirmedSoFar = csf
    ? {
        paid: moneyFromApi(csf.paid) ?? 0,
        waived: moneyFromApi(csf.waived) ?? 0,
        pending: moneyFromApi(csf.pending) ?? 0,
        total: moneyFromApi(csf.expected) ?? 0,
      }
    : {
        paid: collected ?? 0,
        waived: 0,
        pending: 0,
        total: expected ?? price.amount,
      }
  return {
    ...summary,
    startDate: sub.start_date,
    renewal: renewalFromApi(sub.renewal_type),
    endDate: sub.end_date ?? null,
    split: sub.split_type ?? extras.splitType ?? 'equal',
    categoryId: sub.category ? idStr(sub.category.id) : null,
    categoryName: sub.category?.name ?? '—',
    prices,
    leftMembers: extras.leftMembers ?? [],
    confirmedSoFar,
    cycleLabel: extras.charges?.[0]?.month ?? null,
    activity: (sub.activity ?? []).map(mapActivityRow),
    ious: (sub.ious ?? []).map(mapIouRow),
    invites: extras.invites ?? [],
    charges: (sub.charges ?? extras.charges ?? []).map(mapChargeRow),
    leaveRequests: (sub.leave_requests ?? []).map((lr) => ({
      memberId: idStr(lr.member_id),
      name: lr.name,
      firstName: lr.first_name,
      leaveRequestedAt: lr.leave_requested_at,
    })),
    transfer: mapOwnerTransfer(sub.transfer),
    collected: collected ?? undefined,
    expected: expected ?? undefined,
  }
}

export function mapPlanForm(sub) {
  const price = priceBlock(sub)
  return {
    ...mapSubscriptionSummary(sub, []),
    id: idStr(sub.id),
    serviceName: sub.service_name?.name,
    categoryId: sub.category ? idStr(sub.category.id) : null,
    planName: sub.plan_name,
    mode: sub.plan_mode,
    currency: sub.currency,
    price: price.currency === 'USD' ? (price.usdCents ?? 0) / 100 : price.amount / 100,
    rate: price.rate ? price.rate / 100 : null,
    startDate: sub.start_date,
    trialEnd: sub.trial_end_date,
    renewal: renewalFromApi(sub.renewal_type),
    endDate: sub.end_date,
    method: sub.recommended_method,
    cycleUnit: sub.cycle_count > 1 ? 'custom' : sub.cycle_unit,
    customUnit: sub.cycle_unit,
    cycleCount: sub.cycle_count,
    nextRenewalDate: sub.next_renewal,
    rarelyUsed: sub.rarely_used,
    note: sub.note,
    seats: sub.seats ?? 1,
    split: 'equal',
    invites: sub.pending_invites ?? [],
    memberCount: sub.member_count ?? 0,
    priceNow: price,
    pendingInvites: sub.pending_invites ?? [],
  }
}

export function buildCreatePayload(form, serviceNameId) {
  const cycle = cycleFromForm(form)
  const body = {
    service_name: Number(serviceNameId),
    category: form.categoryId ? Number(form.categoryId) : null,
    plan_name: form.planName?.trim(),
    plan_mode: form.mode,
    note: form.note ?? '',
    currency: form.currency,
    amount: moneyToApi(form.currency === 'USD' ? form.price : form.price),
    cycle_unit: cycle.unit,
    cycle_count: cycle.count,
    start_date: form.startDate,
    trial_end_date: form.trialEnd || null,
    renewal_type: renewalToApi(form.renewal),
    end_date: form.renewal === 'fixed' ? form.endDate : null,
    recommended_method: form.method,
    rarely_used: Boolean(form.rarelyUsed),
    next_renewal_date: nextRenewalDateForApi(form),
  }
  if (form.currency === 'USD') {
    body.exchange_rate = rateToApi(Math.round(form.rate * 100))
    body.amount = moneyToApi(Math.round(form.price * 100))
  } else {
    body.amount = moneyToApi(form.price)
  }
  if (form.seats) body.seats = Number(form.seats)
  if (form.split) body.split_type = form.split
  if (form.invites?.length) body.invite_emails = form.invites
  return body
}

export function buildPatchPayload(form) {
  const allowed = {}
  if (form.planName !== undefined) allowed.plan_name = form.planName?.trim()
  if (form.note !== undefined) allowed.note = form.note ?? ''
  if (form.method !== undefined) allowed.recommended_method = form.method
  if (form.rarelyUsed !== undefined) allowed.rarely_used = form.rarelyUsed
  if (form.trialEnd !== undefined) allowed.trial_end_date = form.trialEnd || null
  if (form.endDate !== undefined) allowed.end_date = form.endDate || null
  if (form.nextRenewalDate !== undefined) allowed.next_renewal_date = form.nextRenewalDate || null
  return allowed
}
