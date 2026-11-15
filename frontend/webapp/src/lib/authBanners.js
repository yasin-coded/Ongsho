export const AUTH_BANNER_REASONS = {
  'session-ended': 'Your session ended. Please sign in again.',
  'password-updated': 'Password updated. Sign in with your new password.',
}

export function authBannerForReason(reason) {
  if (!reason || typeof reason !== 'string') return null
  return AUTH_BANNER_REASONS[reason] ?? null
}