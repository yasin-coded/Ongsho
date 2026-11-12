import { setAccessToken } from '@/auth/tokenStore'
import { apiRequest } from '../http'
import { mapUserFromApi } from '../adapters/me'
import { idStr } from '../adapters/common'
import * as mock from '../mock/shared'

export function getMyShared(opts) {
  return mock.getMyShared(opts)
}

export function getMySharedPlan(id) {
  return mock.getMySharedPlan(id)
}

export function downloadMyStatement(planId, opts) {
  return mock.downloadMyStatement(planId, opts)
}

export async function acceptInvite(ref) {
  if (typeof ref === 'object' && ref.token) {
    const data = await apiRequest('post', `/api/invites/${encodeURIComponent(ref.token)}/accept/`)
    return { planId: idStr(data.plan_id), message: data.message ?? 'You joined the plan.' }
  }
  const id = typeof ref === 'object' ? ref.id : ref
  const data = await apiRequest('post', `/api/me/invites/${Number(id)}/accept/`)
  return { planId: idStr(data.plan_id), message: data.message ?? 'You joined the plan.' }
}

export async function declineInvite(ref) {
  const id = typeof ref === 'object' ? ref.id : ref
  await apiRequest('post', `/api/me/invites/${Number(id)}/decline/`)
}

export async function acceptInviteAsNewUser(token, { name, password }) {
  const data = await apiRequest('post', `/api/invites/${encodeURIComponent(token)}/signup/`, {
    data: { name, password },
  })
  setAccessToken(data.access)
  return { access: data.access, user: mapUserFromApi(data.user) }
}

export async function requestLeave(planId) {
  await apiRequest('post', `/api/shared-plans/${Number(planId)}/leave-request/`)
}

export async function cancelLeaveRequest(planId) {
  await apiRequest('delete', `/api/shared-plans/${Number(planId)}/leave-request/`)
}

export function acceptTransfer(transferId) {
  return mock.acceptTransfer(transferId)
}

export function declineTransfer(transferId) {
  return mock.declineTransfer(transferId)
}

export async function getPendingInvites() {
  const rows = await apiRequest('get', '/api/me/invites/')
  return (rows ?? []).map((i) => ({
    id: idStr(i.id),
    planName: i.plan_name,
    ownerName: i.owner_name,
    email: i.email,
  }))
}
