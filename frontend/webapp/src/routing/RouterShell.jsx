import { Suspense } from 'react'
import { Outlet } from 'react-router'
import { AuthProvider, RequireAuth } from '@/auth/AuthProvider'
import { HttpProvider } from '@/providers/HttpProvider'
import { AppShell } from '@/components/layout/AppShell'
import { ErrorBoundary } from '@/components/ErrorBoundary'

export function AppRoot() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <HttpProvider>
          <Outlet />
        </HttpProvider>
      </AuthProvider>
    </ErrorBoundary>
  )
}

export function AppLayout() {
  return (
    <RequireAuth>
      <AppShell />
    </RequireAuth>
  )
}

export function WrappedRoute({ page: Page, fallback }) {
  return (
    <Suspense fallback={fallback}>
      <ErrorBoundary>
        <Page />
      </ErrorBoundary>
    </Suspense>
  )
}