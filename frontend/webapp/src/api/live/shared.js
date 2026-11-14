import { setAccessToken } from '@/auth/tokenStore'
import { apiRequest, downloadFile } from '../http'
import { mapUserFromApi } from '../adapters/me'
import { idStr } from '../adapters/common'
import { mapMySharedList, mapMySharedPlanDetail } from '../adapters/shared'
import { mapPlanJoin } from '../adapters/planJoin'
import { getMe } from './accounts'
import { enrichTransferError } from '../adapters/transfers'
import { enrichStatementError } from '../adapters/statements'

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
  try {
    return await downloadFile(`/api/me/shared-plans/${Number(planId)}/statement/`, { params: { month } })
  } catch (err) {
    throw enrichStatementError(err)
  }
}

export async function getPlanJoin(token) {
  try {
    const data = await apiRequest('get', `/api/join/${encodeURIComponent(token)}/`)
    return mapPlanJoin(data, token)
  } catch (err) {
    if (err.status === 404) return { notFound: true }
    throw err
  }
}

export async function acceptPlanJoin(token) {
  const data = await apiRequest('post', `/api/join/${encodeURIComponent(token)}/accept/`)
  return { planId: idStr(data.plan_id), message: data.message ?? 'You joined the plan.' }
}

export async function signupAndJoinPlan(token, { email, name, password }) {
  const data = await apiRequest('post', `/api/join/${encodeURIComponent(token)}/signup/`, {
    data: { email, name, password },
  })
  setAccessToken(data.access)
  return { access: data.access, user: mapUserFromApi(data.user), planId: idStr(data.plan_id) }
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

export async function acceptTransfer(transferId) {
  try {
    const data = await apiRequest('post', `/api/transfers/${Number(transferId)}/accept/`)
    return {
      planId: idStr(data.plan_id),
      message: data.message ?? 'You now own this plan. It moved to My Plans with all its history.',
    }
  } catch (err) {
    throw enrichTransferError(err)
  }
}

export async function declineTransfer(transferId) {
  try {
    const data = await apiRequest('post', `/api/transfers/${Number(transferId)}/decline/`)
    return { message: data.message ?? 'Transfer declined. Nothing changed.', planId: data.plan_id != null ? idStr(data.plan_id) : undefined }
  } catch (err) {
    throw enrichTransferError(err)
  }
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
