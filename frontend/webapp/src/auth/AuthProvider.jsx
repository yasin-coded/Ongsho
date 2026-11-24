import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import * as accounts from '@/api/accounts'
import { keys } from '@/api/keys'
import { forceMockMode } from '@/api/modes'
import { clearAccessToken, setAccessToken } from '@/auth/tokenStore'
import { clearSessionHint, hasSessionHint, markHasSession } from '@/auth/sessionHint'
import { shouldAttemptSessionRefresh } from '@/auth/sessionBootstrap'
import { BootSplash } from '@/components/layout/BootSplash'
import { AuthContext, useAuth } from './auth-context'

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading')
  const [session, setSession] = useState(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    document.documentElement.classList.toggle('is-booting', status === 'loading')
    return () => document.documentElement.classList.remove('is-booting')
  }, [status])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const mock = forceMockMode()
      if (!shouldAttemptSessionRefresh({ forceMock: mock, hasSessionHint: hasSessionHint() })) {
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
          clearSessionHint()
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
    markHasSession()
    queryClient.setQueryData(keys.me, result.user)
    return result
  }, [queryClient])

  const adoptSession = useCallback(
    ({ access, user }) => {
      queryClient.clear()
      setAccessToken(access)
      setSession({ token: access, user })
      setStatus('authed')
      markHasSession()
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
    clearSessionHint()
    setSession(null)
    setStatus('anonymous')
    queryClient.clear()
  }, [queryClient])

  const endSession = useCallback(() => {
    clearAccessToken()
    clearSessionHint()
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
      endSession,
      signInDirect,
      adoptSession,
    }),
    [session, status, login, logout, endSession, signInDirect, adoptSession],
  )

  const booted = status !== 'loading'

  return (
    <AuthContext.Provider value={value}>
      {booted ? children : null}
      {status === 'loading' ? <BootSplash /> : null}
    </AuthContext.Provider>
  )
}

export function RequireAuth({ children }) {
  const { status, isAuthed } = useAuth()
  const location = useLocation()
  if (status === 'loading') return null
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
