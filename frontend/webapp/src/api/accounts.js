import { db, ME, nextId } from '@/mocks/db'
import { userById, profileCounts, inviteView } from '@/mocks/selectors'
import { mockNow } from '@/lib/dates'
import { ApiError, read, write } from './client'

// The mock server's own memory of the signed-in password, so password-confirmed actions can be checked.
const server = { password: null }

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function passwordRules(password) {
  return [
    { id: 'length', label: 'At least 8 characters', ok: password.length >= 8 },
    { id: 'digits', label: 'Not only numbers', ok: password.length > 0 && !/^\d+$/.test(password) },
    { id: 'letters', label: 'Has a letter', ok: /[a-z]/i.test(password) },
  ]
}

export function checkPassword(password) {
  if (!password) throw new ApiError('Enter your password.', { fields: { password: 'Enter your password.' } })
  if (server.password && password !== server.password) {
    throw new ApiError('That password is not right.', { status: 403, fields: { password: 'That password is not right. Try again.' } })
  }
}

function meShape() {
  const me = userById(ME)
  return { ...me, ...profileCounts(ME) }
}

export function login({ email, password }) {
  return write(() => {
    const fields = {}
    if (!EMAIL_RE.test(email ?? '')) fields.email = 'Enter an email address like name@example.com.'
    if (!password) fields.password = 'Enter your password.'
    if (Object.keys(fields).length) throw new ApiError('Check the highlighted fields.', { fields })
    server.password = password
    return { access: `mock-access-${Date.now().toString(36)}`, user: meShape() }
  })
}

export function register({ name, email, password }) {
  return write(() => {
    const fields = {}
    if (!name?.trim()) fields.name = 'Enter your name.'
    if (!EMAIL_RE.test(email ?? '')) fields.email = 'Enter an email address like name@example.com.'
    if (passwordRules(password ?? '').some((r) => !r.ok)) fields.password = 'The password does not meet the rules below.'
    if (Object.keys(fields).length) throw new ApiError('Check the highlighted fields.', { fields })
    server.password = password
    return { email }
  })
}

export function verifyEmail() {
  return write(() => ({ verified: true }))
}

export function resendVerification() {
  return write(() => ({ sent: true }))
}

export function requestPasswordReset({ email }) {
  return write(() => {
    if (!EMAIL_RE.test(email ?? '')) throw new ApiError('Enter an email address like name@example.com.', { fields: { email: 'Enter an email address like name@example.com.' } })
    return { sent: true }
  })
}

export function confirmPasswordReset({ password }) {
  return write(() => {
    if (passwordRules(password ?? '').some((r) => !r.ok)) throw new ApiError('The password does not meet the rules.', { fields: { password: 'The password does not meet the rules below.' } })
    server.password = password
  })
}

export function logout() {
  return write(() => {
    server.password = null
  })
}

export function getMe() {
  return read(meShape)
}

export function updateMe({ name, avatarColor }) {
  return write(() => {
    const me = userById(ME)
    if (name !== undefined) {
      if (!name.trim()) throw new ApiError('Enter your name.', { fields: { name: 'Enter your name.' } })
      me.name = name.trim()
    }
    if (avatarColor) me.avatarColor = avatarColor
    return meShape()
  })
}

export function changeEmail({ email, password }) {
  return write(() => {
    const me = userById(ME)
    if (!EMAIL_RE.test(email ?? '')) throw new ApiError('Enter an email address like name@example.com.', { fields: { email: 'Enter an email address like name@example.com.' } })
    if (email === me.email) throw new ApiError('That is already your email.', { fields: { email: 'That is already your email.' } })
    checkPassword(password)
    me.pendingEmail = email
    db.audit.push({ id: nextId('a'), ts: mockNow(), actor: ME, action: 'email_change_requested', value: email })
    return meShape()
  })
}

export function resendEmailChange() {
  return write(() => ({ sent: true }))
}

export function cancelEmailChange() {
  return write(() => {
    userById(ME).pendingEmail = null
    return meShape()
  })
}

export function changePassword({ oldPassword, newPassword, repeat }) {
  return write(() => {
    const fields = {}
    if (!oldPassword) fields.oldPassword = 'Enter your current password.'
    else if (server.password && oldPassword !== server.password) fields.oldPassword = 'That password is not right.'
    if (passwordRules(newPassword ?? '').some((r) => !r.ok)) fields.newPassword = 'Use at least 8 characters, with a letter.'
    if (newPassword !== repeat) fields.repeat = 'The two new passwords do not match.'
    if (Object.keys(fields).length) throw new ApiError('Check the highlighted fields.', { fields })
    server.password = newPassword
  })
}

export function getReminderSettings() {
  return read(() => db.reminderSettings)
}

export function updateReminderSettings(settings) {
  return write(() => {
    Object.assign(db.reminderSettings, settings)
    return db.reminderSettings
  })
}

/** Public: invite by token, for the sign-up or accept page. */
export function getInvite(token) {
  return read(() => {
    const invite = db.invites.find((i) => i.token === token)
    if (!invite) return { notFound: true }
    return inviteView(invite)
  })
}
