import { setAccessToken, clearAccessToken } from '@/auth/tokenStore'
import { apiRequest } from '../http'
import { mapMePatch, mapUserFromApi } from '../adapters/me'
import { mapPublicInvite } from '../adapters/invite'
import * as mock from '../mock/accounts'

export function passwordRules(password) {
  return mock.passwordRules(password)
}

export function checkPassword() {
  return mock.checkPassword(...arguments)
}

export async function register({ name, email, password }) {
  await apiRequest('post', '/api/auth/register/', { data: { name, email, password } })
  return { email }
}

export async function verifyEmail({ token } = {}) {
  if (!token) return mock.verifyEmail()
  await apiRequest('post', '/api/auth/verify-email/', { data: { token } })
  return { verified: true }
}

export async function resendVerification({ email } = {}) {
  await apiRequest('post', '/api/auth/resend-verification/', { data: { email } })
  return { sent: true }
}

export async function login({ email, password }) {
  const data = await apiRequest('post', '/api/auth/login/', { data: { email, password } })
  setAccessToken(data.access)
  return { access: data.access, user: mapUserFromApi(data.user) }
}

export async function logout() {
  try {
    await apiRequest('post', '/api/auth/logout/')
  } finally {
    clearAccessToken()
  }
}

export async function requestPasswordReset({ email }) {
  await apiRequest('post', '/api/auth/password-reset/', { data: { email } })
  return { sent: true }
}

export async function confirmPasswordReset({ password, uid, token }) {
  await apiRequest('post', '/api/auth/password-reset/confirm/', {
    data: { uid, token, new_password: password },
  })
}

export async function refreshSession() {
  const data = await apiRequest('post', '/api/auth/refresh/')
  setAccessToken(data.access)
  return data.access
}

export async function getMe() {
  const data = await apiRequest('get', '/api/me/')
  return mapUserFromApi(data)
}

export async function updateMe(payload) {
  const data = await apiRequest('patch', '/api/me/', { data: mapMePatch(payload) })
  return mapUserFromApi(data)
}

export async function changePassword({ oldPassword, newPassword }) {
  await apiRequest('post', '/api/me/password/', {
    data: { current_password: oldPassword, new_password: newPassword },
  })
  clearAccessToken()
  return { message: 'Password updated. Please sign in again.', revoked: true }
}

export async function changeEmail({ email, password }) {
  await apiRequest('post', '/api/me/email/', { data: { new_email: email, password } })
  return getMe()
}

export async function resendEmailChange() {
  await apiRequest('post', '/api/me/email/resend/')
  return { sent: true }
}

export async function cancelEmailChange() {
  await apiRequest('delete', '/api/me/email/')
  return getMe()
}

export async function getReminderSettings() {
  const data = await apiRequest('get', '/api/reminders/settings/')
  return {
    daysBefore: data.days_before ?? [],
    email: data.email ?? true,
  }
}

export async function updateReminderSettings({ daysBefore, email }) {
  const body = {}
  if (daysBefore !== undefined) body.days_before = daysBefore
  if (email !== undefined) body.email = email
  const data = await apiRequest('patch', '/api/reminders/settings/', { data: body })
  return {
    daysBefore: data.days_before ?? [],
    email: data.email ?? true,
  }
}

export async function getInvite(token) {
  try {
    const data = await apiRequest('get', `/api/invites/${encodeURIComponent(token)}/`)
    return mapPublicInvite(data, token)
  } catch (err) {
    if (err.status === 404) return { notFound: true }
    throw err
  }
}
