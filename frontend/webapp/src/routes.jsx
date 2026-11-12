import { createBrowserRouter, Outlet } from 'react-router'
import { AuthProvider, GuestOnly, RequireAuth } from '@/auth/AuthProvider'
import { HttpProvider } from '@/providers/HttpProvider'
import { AppShell } from '@/components/layout/AppShell'
import { LandingPage } from '@/features/landing/LandingPage'
import { LoginPage, RegisterPage, VerifyEmailPage, ResetPasswordPage } from '@/features/auth/AuthPages'
import { InvitePage } from '@/features/auth/InvitePage'
import { HomePage } from '@/features/dashboard/HomePage'
import { MyPlansPage } from '@/features/plans/MyPlansPage'
import { PlanFormPage } from '@/features/plans/PlanFormPage'
import { OwnerPlanPage } from '@/features/plans/OwnerPlanPage'
import { ReviewPaymentsPage } from '@/features/plans/ReviewPaymentsPage'
import { SharedPlansPage } from '@/features/shared/SharedPlansPage'
import { MemberPlanPage } from '@/features/shared/MemberPlanPage'
import { CalendarPage } from '@/features/calendar/CalendarPage'
import { NotificationsPage } from '@/features/notifications/NotificationsPage'
import { ProfilePage } from '@/features/profile/ProfilePage'
import { KitPage } from '@/features/kit/KitPage'
import { NotFoundPage } from '@/features/NotFoundPage'

function AppRoot() {
  return (
    <AuthProvider>
      <HttpProvider>
        <Outlet />
      </HttpProvider>
    </AuthProvider>
  )
}

export const router = createBrowserRouter([
  {
    element: <AppRoot />,
    children: [
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <GuestOnly><LoginPage /></GuestOnly> },
  { path: '/register', element: <GuestOnly><RegisterPage /></GuestOnly> },
  { path: '/verify-email', element: <VerifyEmailPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
  { path: '/invite/:token', element: <InvitePage /> },
  { path: '/kit', element: <KitPage /> },
  {
    path: '/app',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <HomePage /> },
      { path: 'plans', element: <MyPlansPage /> },
      { path: 'plans/new', element: <PlanFormPage /> },
      { path: 'plans/:id', element: <OwnerPlanPage /> },
      { path: 'plans/:id/edit', element: <PlanFormPage /> },
      { path: 'plans/:id/review', element: <ReviewPaymentsPage /> },
      { path: 'shared', element: <SharedPlansPage /> },
      { path: 'shared/:id', element: <MemberPlanPage /> },
      { path: 'calendar', element: <CalendarPage /> },
      { path: 'notifications', element: <NotificationsPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: '*', element: <NotFoundPage inApp /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
    ],
  },
])
