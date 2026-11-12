import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import * as accounts from '@/api/accounts'
import { keys } from '@/api/keys'
import { forceMockMode } from '@/api/modes'
import { clearAccessToken, setAccessToken } from '@/auth/tokenStore'
import { AuthContext, useAuth } from './auth-context'

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading')
  const [session, setSession] = useState(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (forceMockMode()) {
        if (!cancelled) setStatus('anonymous')
        return
      }
      try {
        const access = await accounts.refreshSession()
        if (cancelled) return
        setAccessToken(access)
        const user = await accounts.getMe()
        if (cancelled) return
        setSession({ token: access, user })
        setStatus('authed')
        queryClient.setQueryData(keys.me, user)
      } catch {
        if (!cancelled) {
          clearAccessToken()
          setSession(null)
          setStatus('anonymous')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [queryClient])

  const login = useCallback(async (credentials) => {
    queryClient.clear()
    const result = await accounts.login(credentials)
    setSession({ token: result.access, user: result.user })
    setStatus('authed')
    queryClient.setQueryData(keys.me, result.user)
    return result
  }, [queryClient])

  const adoptSession = useCallback(
    ({ access, user }) => {
      queryClient.clear()
      setAccessToken(access)
      setSession({ token: access, user })
      setStatus('authed')
      queryClient.setQueryData(keys.me, user)
    },
    [queryClient],
  )

  const signInDirect = useCallback(
    (user) => adoptSession({ access: `mock-access-${Date.now().toString(36)}`, user }),
    [adoptSession],
  )

  const logout = useCallback(async () => {
    await accounts.logout()
    setSession(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  const value = useMemo(
    () => ({
      session,
      user: session?.user ?? null,
      status,
      isAuthed: status === 'authed',
      login,
      logout,
      signInDirect,
      adoptSession,
    }),
    [session, status, login, logout, signInDirect, adoptSession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function RequireAuth({ children }) {
  const { status, isAuthed } = useAuth()
  const location = useLocation()
  if (status === 'loading') {
    return (
      <div className="shell" aria-busy="true">
        <p className="p-8 font-bold">Loading…</p>
      </div>
    )
  }
  if (!isAuthed) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return children
}

export function GuestOnly({ children }) {
  const { status, isAuthed } = useAuth()
  const location = useLocation()
  if (status === 'loading') return null
  if (isAuthed) return <Navigate to="/app" replace state={{ from: location.pathname }} />
  return children
}
