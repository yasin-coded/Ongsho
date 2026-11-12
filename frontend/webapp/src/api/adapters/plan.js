import { lookupServiceKey } from '@/lib/services'
import { categoryColor } from '@/lib/colors'
import { idStr, moneyFromApi, moneyToApi, rateFromApi, rateToApi, paginatedBody } from './common'
import { avatarColorFromId } from './me'

function cycleFromApi(unit, count) {
  if (count > 1) return { unit, count }
  return { unit: unit === 'month' && count === 1 ? 'month' : unit, count }
}

function renewalFromApi(renewalType) {
  return renewalType === 'fixed_term' ? 'fixed' : 'ongoing'
}

function renewalToApi(renewal) {
  return renewal === 'fixed' ? 'fixed_term' : 'ongoing'
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

function statusPill(sub, members = []) {
  if (sub.status === 'trial') return { key: 'trial', label: 'Trial' }
  if (sub.status !== 'active') return { key: sub.status, label: sub.status }
  const shared = (sub.member_count ?? 0) > 1 || (sub.pending_invites?.length ?? 0) > 0
  if (!shared) return { key: 'solo', label: 'Just me' }
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
  }
}

export function mapSubscriptionSummary(sub, members = [], meUserId = null) {
  const serviceName = sub.service_name?.name ?? ''
  const category = sub.category
  const price = priceBlock(sub)
  const shared = (sub.member_count ?? members.length) > 1 || (sub.pending_invites?.length ?? 0) > 0
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
    perSeat: shared && members.length ? Math.floor(price.amount / Math.max(members.length, 1)) : price.amount,
    seatsCap: sub.seats ?? members.length ?? 1,
    seatsTaken: members.length,
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
    pendingCount: members.filter((m) => m.dueStatus === 'pending').length,
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
    confirmed: 0, // TODO(live): needs dues API
    pending: 0, // TODO(live): needs dues API
    expected: 0, // TODO(live): needs dues API
    reviewCount: counts.review ?? 0,
    reviewPlans: [], // TODO(live): needs payments review API on list
    rarelyCount: counts.rarely ?? 0,
  }
  const totalsMeta = {
    memberCollections: false,
    reviewDetail: false,
  }
  const items = page.items.map((sub) => {
    const members = membersByPlan.get(sub.id) ?? []
    return mapSubscriptionSummary(sub, members, meUserId)
  })
  return { ...page, items, counts, totals, totalsMeta }
}

export function mapSubscriptionDetail(sub, extras = {}) {
  const members = extras.members ?? []
  const summary = mapSubscriptionSummary({ ...sub, member_count: members.length }, members, extras.meUserId)
  const price = priceBlock(sub)
  const prices = (extras.priceChanges ?? []).map((p) => ({
    id: idStr(p.id),
    effectiveFrom: p.effective_from,
    amount: moneyFromApi(p.amount_bdt ?? p.amount),
    usdCents: p.currency === 'USD' ? moneyFromApi(p.amount) : null,
    rate: p.exchange_rate ? rateFromApi(p.exchange_rate) : null,
  }))
  return {
    ...summary,
    startDate: sub.start_date,
    renewal: renewalFromApi(sub.renewal_type),
    endDate: sub.end_date ?? null,
    split: extras.splitType ?? 'equal',
    categoryId: sub.category ? idStr(sub.category.id) : null,
    categoryName: sub.category?.name ?? '—',
    prices,
    leftMembers: extras.leftMembers ?? [],
    confirmedSoFar: { paid: 0, waived: 0, pending: 0, total: price.amount },
    cycleLabel: null,
    activity: [],
    ious: [],
    invites: extras.invites ?? [],
    charges: extras.charges ?? [],
    transfer: null,
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
  const body = {
    service_name: Number(serviceNameId),
    category: form.categoryId ? Number(form.categoryId) : null,
    plan_name: form.planName?.trim(),
    plan_mode: form.mode,
    note: form.note ?? '',
    currency: form.currency,
    amount: moneyToApi(form.currency === 'USD' ? form.price : form.price),
    cycle_unit: form.cycleUnit === 'custom' ? form.customUnit ?? 'month' : form.cycleUnit,
    cycle_count: form.cycleUnit === 'custom' ? Number(form.cycleCount) || 1 : 1,
    start_date: form.startDate,
    trial_end_date: form.trialEnd || null,
    renewal_type: renewalToApi(form.renewal),
    end_date: form.renewal === 'fixed' ? form.endDate : null,
    recommended_method: form.method,
    rarely_used: Boolean(form.rarelyUsed),
    next_renewal_date: form.nextRenewalDate || null,
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
