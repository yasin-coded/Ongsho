import { useCallback, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import * as accounts from '@/api/accounts'
import { AuthContext, useAuth } from './auth-context'

/** The access token lives in memory only. A reload signs you out, by design. */
export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const queryClient = useQueryClient()

  const login = useCallback(async (credentials) => {
    const result = await accounts.login(credentials)
    setSession({ token: result.access, user: result.user })
    return result
  }, [])

  const signInDirect = useCallback((user) => setSession({ token: `mock-access-${Date.now().toString(36)}`, user }), [])

  const logout = useCallback(async () => {
    await accounts.logout()
    setSession(null)
    queryClient.clear()
  }, [queryClient])

  const value = useMemo(() => ({ session, isAuthed: Boolean(session), login, logout, signInDirect }), [session, login, logout, signInDirect])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function RequireAuth({ children }) {
  const { isAuthed } = useAuth()
  const location = useLocation()
  if (!isAuthed) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return children
}
