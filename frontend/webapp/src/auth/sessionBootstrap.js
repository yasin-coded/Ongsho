/** Whether the app should POST /api/auth/refresh/ on first load. */
export function shouldAttemptSessionRefresh({ forceMock, hasSessionHint }) {
  if (forceMock) return false
  return hasSessionHint
}