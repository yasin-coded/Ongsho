import { ApiError } from '@/api/http'

export const ACCOUNT_CLOSE_ERROR_MESSAGES = {
  invalid: 'Please enter your current password.',
  invalid_password: 'The password you entered is incorrect.',
  locked: 'Too many unsuccessful attempts. Please try again later.',
  staff_cannot_close: 'Staff accounts cannot be closed through this option.',
  account_already_closed: 'This account has already been closed.',
  pending_ownership_transfer: 'Resolve the pending ownership transfer before closing your account.',
  owned_plans_remain: 'Transfer or resolve ownership of your plans before closing your account.',
  active_membership: 'Leave or resolve your active memberships before closing your account.',
  tombstone_collision: "We couldn't complete account closure right now. Please try again later.",
}

export function messageForAccountCloseError(error) {
  if (error?.code && ACCOUNT_CLOSE_ERROR_MESSAGES[error.code]) {
    return ACCOUNT_CLOSE_ERROR_MESSAGES[error.code]
  }
  if (error?.status === 0) return error.message
  return error?.message ?? 'Something went wrong. Try again.'
}

export function rethrowAccountCloseError(err) {
  if (!(err instanceof ApiError)) throw err
  const message = messageForAccountCloseError(err)
  let fields = err.fields
  if (err.code === 'invalid_password' && fields?.password) {
    fields = { ...fields, password: ACCOUNT_CLOSE_ERROR_MESSAGES.invalid_password }
  }
  throw new ApiError(message, { status: err.status, code: err.code, fields })
}