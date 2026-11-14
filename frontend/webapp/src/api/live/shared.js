import { setAccessToken } from '@/auth/tokenStore'
import { apiRequest, downloadFile } from '../http'
import { mapUserFromApi } from '../adapters/me'
import { idStr } from '../adapters/common'
import { mapMySharedList, mapMySharedPlanDetail } from '../adapters/shared'
import { getMe } from './accounts'
import * as mock from '../mock/shared'

export async function getMyShared({ filter = 'all', page = 1, size = 5 } = {}) {
  const data = await apiRequest('get', '/api/me/shared-plans/', {
    params: { filter, page, page_size: size },
  })
  const me = await getMe()
  return mapMySharedList(data, me.id)
}

export async function getMySharedPlan(id) {
  try {
    const data = await apiRequest('get', `/api/me/shared-plans/${Number(id)}/`)
    const me = await getMe()
    return mapMySharedPlanDetail(data, me.id)
  } catch (err) {
    if (err.status === 404) return { notFound: true }
    throw err
  }
}

export async function downloadMyStatement(planId, { month }) {
  return downloadFile(`/api/me/shared-plans/${Number(planId)}/statement/`, { params: { month } })
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
