import { parseTaka, fromPaisa, toPaisa } from '@/lib/money'
import { apiRequest, downloadFile } from '../http'
import { idStr, moneyToApi, rateToApi, moneyFromApi } from '../adapters/common'
import { mapReview, mapLedgerResponse, mapMemberDetail } from '../adapters/review'
import {
  buildCreatePayload,
  buildPatchPayload,
  mapListResponse,
  mapPlanForm,
  mapSubscriptionDetail,
  mapMemberRow,
} from '../adapters/plan'
import * as catalogLive from './catalog'
import { getMe } from './accounts'
import { enrichTransferError } from '../adapters/transfers'
import { enrichStatementError } from '../adapters/statements'

async function resolveServiceNameId(serviceName, categoryId) {
  const names = await catalogLive.getServiceNames()
  const hit = names.find((n) => n.name.toLowerCase() === serviceName.trim().toLowerCase())
  if (hit) return Number(hit.id)
  const created = await catalogLive.createServiceName({ name: serviceName.trim(), categoryId })
  return Number(created.id)
}

async function loadMembers(planId, meUserId) {
  try {
    const rows = await apiRequest('get', `/api/shared-plans/${Number(planId)}/members/`)
    return (rows ?? []).map((r) => mapMemberRow(r, meUserId))
  } catch {
    return []
  }
}

function mapInviteRow(i) {
  return {
    id: idStr(i.id),
    email: i.email,
    status: i.status,
    createdAt: i.created_at,
    expiresOn: i.expires_on ?? null,
    token: i.token ?? i.link?.split('/').pop() ?? null,
  }
}

async function loadInvites(planId) {
  try {
    const rows = await apiRequest('get', `/api/shared-plans/${Number(planId)}/invites/`)
    const list = Array.isArray(rows) ? rows : rows?.results ?? []
    return list.map(mapInviteRow)
  } catch {
    return []
  }
}

/** Ensure pending emails from subscription detail appear even when the invites list call failed. */
function mergePendingInviteEmails(invites, pendingEmails = []) {
  if (!pendingEmails.length) return invites
  const seen = new Set(invites.map((i) => i.email.toLowerCase()))
  const extra = pendingEmails
    .filter((email) => email && !seen.has(String(email).toLowerCase()))
    .map((email) => ({
      id: `email-${email}`,
      email,
      status: 'pending',
      createdAt: null,
      expiresOn: null,
      token: null,
    }))
  return extra.length ? [...invites, ...extra] : invites
}

async function loadSharedMeta(planId) {
  try {
    return await apiRequest('get', `/api/shared-plans/${Number(planId)}/`)
  } catch {
    return null
  }
}

export async function getSubscriptions({ search = '', filter = 'all', page = 1, size = 5 } = {}) {
  const params = { page, page_size: size, search }
  if (filter === 'review') params.needs_review = 'true'
  if (filter === 'rarely') params.rarely_used = 'true'
  const data = await apiRequest('get', '/api/subscriptions/', { params })
  const me = await getMe()
  return mapListResponse(data, new Map(), me.id)
}

export async function getSubscription(id) {
  try {
    const sub = await apiRequest('get', `/api/subscriptions/${Number(id)}/`)
    const me = await getMe()
    const [members, invitesRaw, shared, priceChanges] = await Promise.all([
      loadMembers(id, me.id),
      loadInvites(id),
      loadSharedMeta(id),
      apiRequest('get', `/api/subscriptions/${Number(id)}/price-changes/`).catch(() => []),
    ])
    const invites = mergePendingInviteEmails(invitesRaw, sub.pending_invites)
    const seatsTaken = shared?.member_count ?? members.length
    return mapSubscriptionDetail(sub, {
      members,
      invites,
      splitType: shared?.split_type,
      seats: shared?.seats,
      seatsTaken,
      priceChanges: priceChanges ?? [],
      meUserId: me.id,
    })
  } catch (err) {
    if (err.status === 404) return { notFound: true }
    throw err
  }
}

export async function getPlanForm(id) {
  const sub = await apiRequest('get', `/api/subscriptions/${Number(id)}/`)
  const shared = await loadSharedMeta(id)
  const form = mapPlanForm({ ...sub, seats: shared?.seats, pending_invites: sub.pending_invites })
  return form
}

export async function getReview(planId) {
  const data = await apiRequest('get', `/api/shared-plans/${Number(planId)}/review/`)
  return mapReview(data)
}

export async function getMember(memberId) {
  const data = await apiRequest('get', `/api/members/${Number(memberId)}/`)
  return mapMemberDetail(data)
}

export async function getLedger(planId, { member = 'all', month = 'all', status = 'all', page = 1, size = 8 } = {}) {
  const params = { page, page_size: size }
  if (member !== 'all') params.member = Number(member)
  if (month !== 'all') params.month = month
  if (status !== 'all') params.status = status
  const data = await apiRequest('get', `/api/shared-plans/${Number(planId)}/ledger/`, { params })
  return mapLedgerResponse(data)
}

export async function createSubscription(form) {
  const serviceId = await resolveServiceNameId(form.serviceName, form.categoryId)
  const body = buildCreatePayload(form, serviceId)
  if (form.currency === 'USD') {
    body.amount = fromPaisa(Math.round(Number(form.price) * 100))
    body.exchange_rate = rateToApi(Math.round(Number(form.rate) * 100))
  } else {
    const paisa = parseTaka(String(form.price))
    if (paisa === null) throw new RangeError('Invalid price')
    body.amount = fromPaisa(paisa)
  }
  const data = await apiRequest('post', '/api/subscriptions/', { data: body })
  return mapPlanForm(data)
}

export async function updateSubscription(id, form) {
  const data = await apiRequest('patch', `/api/subscriptions/${Number(id)}/`, { data: buildPatchPayload(form) })
  return mapPlanForm(data)
}

export async function deletePlan(id, { password }) {
  await apiRequest('delete', `/api/subscriptions/${Number(id)}/`, { data: { password } })
  return {}
}

export async function pausePlan(id) {
  const data = await apiRequest('post', `/api/subscriptions/${Number(id)}/pause/`)
  return mapPlanForm(data)
}

export async function resumePlan(id) {
  const data = await apiRequest('post', `/api/subscriptions/${Number(id)}/resume/`)
  return mapPlanForm(data)
}

export async function cancelPlan(id) {
  const data = await apiRequest('post', `/api/subscriptions/${Number(id)}/cancel/`)
  return mapPlanForm(data)
}

export async function renewPlan(id, { endDate }) {
  const data = await apiRequest('post', `/api/subscriptions/${Number(id)}/renew/`, { data: { end_date: endDate } })
  return mapPlanForm(data)
}

export async function setRarelyUsed(id, value) {
  await apiRequest('patch', `/api/subscriptions/${Number(id)}/`, { data: { rarely_used: value } })
}

export async function updatePlanSplit(planId, { split, shares = {} }) {
  const payload = {}
  for (const [memberId, value] of Object.entries(shares)) {
    payload[memberId] = typeof value === 'number' ? fromPaisa(value) : String(value)
  }
  await apiRequest('put', `/api/shared-plans/${Number(planId)}/split/`, {
    data: { split_type: split, shares: payload },
  })
}

export async function addPriceChange(id, { amount, usd, rate, effectiveFrom }) {
  const body = { effective_from: effectiveFrom }
  if (usd != null) {
    body.amount = fromPaisa(Math.round(usd))
    body.exchange_rate = rateToApi(rate)
  } else {
    body.amount = typeof amount === 'number' && amount > 1000 ? fromPaisa(amount) : moneyToApi(amount)
  }
  await apiRequest('post', `/api/subscriptions/${Number(id)}/price-changes/`, { data: body })
}

export async function correctRate(chargeId, { rate }) {
  await apiRequest('post', `/api/charges/${Number(chargeId)}/rate/`, {
    data: { exchange_rate: rateToApi(rate) },
  })
}

export async function createInvite(planId, { email }) {
  const data = await apiRequest('post', `/api/shared-plans/${Number(planId)}/invites/`, { data: { email } })
  return { id: idStr(data.id), email: data.email, link: data.link }
}

export async function cancelInvite(inviteId) {
  await apiRequest('post', `/api/invites/${Number(inviteId)}/cancel/`)
}

export async function decideLeave(memberId, payload) {
  await apiRequest('post', `/api/members/${Number(memberId)}/leave/`, {
    data: {
      approve: payload.approve,
      leave_date: payload.leaveDate,
      unpaid: payload.unpaid,
    },
  })
}

export async function replaceMember(memberId, { email }) {
  await apiRequest('post', `/api/members/${Number(memberId)}/replace/`, { data: { email } })
}

export async function startTransfer(planId, { memberId, password }) {
  try {
    await apiRequest('post', `/api/shared-plans/${Number(planId)}/transfer/`, {
      data: { member_id: Number(memberId), password },
    })
    return { message: 'Request sent. Nothing changes until they accept.' }
  } catch (err) {
    throw enrichTransferError(err)
  }
}

export async function cancelTransfer(transferId) {
  try {
    await apiRequest('post', `/api/transfers/${Number(transferId)}/cancel/`)
    return { message: 'Transfer cancelled. Nothing changed.' }
  } catch (err) {
    throw enrichTransferError(err)
  }
}

export async function downloadOwnerStatement(planId, { month }) {
  try {
    return await downloadFile(`/api/shared-plans/${Number(planId)}/statement/`, { params: { month } })
  } catch (err) {
    throw enrichStatementError(err)
  }
}
