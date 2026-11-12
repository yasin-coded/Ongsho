import { delegate } from './delegate'
import * as mock from './mock/accounts'
import * as live from './live/accounts'

export { passwordRules } from './mock/accounts'
export { checkPassword } from './mock/accounts'

export const register = delegate(live, mock, 'register')
export const verifyEmail = delegate(live, mock, 'verifyEmail')
export const resendVerification = delegate(live, mock, 'resendVerification')
export const login = delegate(live, mock, 'login')
export const logout = delegate(live, mock, 'logout')
export const requestPasswordReset = delegate(live, mock, 'requestPasswordReset')
export const confirmPasswordReset = delegate(live, mock, 'confirmPasswordReset')
export const getMe = delegate(live, mock, 'getMe')
export const updateMe = delegate(live, mock, 'updateMe')
export const changePassword = delegate(live, mock, 'changePassword')
export const changeEmail = delegate(live, mock, 'changeEmail')
export const resendEmailChange = delegate(live, mock, 'resendEmailChange')
export const cancelEmailChange = delegate(live, mock, 'cancelEmailChange')
export const getReminderSettings = delegate(live, mock, 'getReminderSettings')
export const updateReminderSettings = delegate(live, mock, 'updateReminderSettings')
export const getInvite = delegate(live, mock, 'getInvite')

export { refreshSession } from './live/accounts'
