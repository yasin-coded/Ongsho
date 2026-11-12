import { parseTaka, fromPaisa, toPaisa } from '@/lib/money'
import { apiRequest } from '../http'
import { idStr, moneyToApi, rateToApi, moneyFromApi } from '../adapters/common'
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
import * as mock from '../mock/plans'

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

async function loadInvites(planId) {
  try {
    const rows = await apiRequest('get', `/api/shared-plans/${Number(planId)}/invites/`)
    return (rows ?? []).map((i) => ({
      id: idStr(i.id),
      email: i.email,
      status: i.status,
      createdAt: i.created_at,
      token: i.token,
    }))
  } catch {
    return []
  }
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
  const membersByPlan = new Map()
  for (const sub of data.results ?? []) {
    if ((sub.member_count ?? 0) > 0) {
      membersByPlan.set(sub.id, await loadMembers(sub.id, me.id))
    }
  }
  return mapListResponse(data, membersByPlan, me.id)
}

export async function getSubscription(id) {
  try {
    const sub = await apiRequest('get', `/api/subscriptions/${Number(id)}/`)
    const me = await getMe()
    const [members, invites, shared, priceChanges] = await Promise.all([
      loadMembers(id, me.id),
      loadInvites(id),
      loadSharedMeta(id),
      apiRequest('get', `/api/subscriptions/${Number(id)}/price-changes/`).catch(() => []),
    ])
    return mapSubscriptionDetail(sub, {
      members,
      invites,
      splitType: shared?.split_type,
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

export function getReview(planId) {
  return mock.getReview(planId)
}

export function getMember(memberId) {
  return mock.getMember(memberId)
}

export function getLedger(planId, opts) {
  return mock.getLedger(planId, opts)
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
  await apiRequest('patch', `/api/shared-plans/${Number(planId)}/split/`, {
    data: { split_type: split, shares },
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
  await apiRequest('post', `/api/members/${Number(memberId)}/leave/`, { data: payload })
}

export async function replaceMember(memberId, { email }) {
  await apiRequest('post', `/api/members/${Number(memberId)}/replace/`, { data: { email } })
}

export function startTransfer(planId, payload) {
  return mock.startTransfer(planId, payload)
}

export function cancelTransfer(transferId) {
  return mock.cancelTransfer(transferId)
}

export function downloadOwnerStatement(planId, opts) {
  return mock.downloadOwnerStatement(planId, opts)
}
