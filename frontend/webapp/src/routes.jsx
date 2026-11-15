import { lazy, Suspense } from 'react'
import { createBrowserRouter, Outlet } from 'react-router'
import { AuthProvider, GuestOnly, RequireAuth } from '@/auth/AuthProvider'
import { HttpProvider } from '@/providers/HttpProvider'
import { AppShell } from '@/components/layout/AppShell'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { SkeletonCard } from '@/components/ui/Misc'
import {
  AppHomeFallback,
  DetailPageFallback,
  InvitePageSkeleton,
  LandingFallback,
  ListPageFallback,
  PlanFormSkeleton,
  ReviewPaymentsSkeleton,
} from '@/routes/RouteFallbacks'

function lazyPage(importFn) {
  const Lazy = lazy(importFn)
  return function LazyRoute(props) {
    return <Lazy {...props} />
  }
}

const LandingPage = lazyPage(() => import('@/features/landing/LandingPage').then((m) => ({ default: m.LandingPage })))
const LoginPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.LoginPage })))
const RegisterPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.RegisterPage })))
const VerifyEmailPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.VerifyEmailPage })))
const ResetPasswordPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.ResetPasswordPage })))
const InvitePage = lazyPage(() => import('@/features/auth/InvitePage').then((m) => ({ default: m.InvitePage })))
const PlanJoinPage = lazyPage(() => import('@/features/auth/PlanJoinPage').then((m) => ({ default: m.PlanJoinPage })))
const HomePage = lazyPage(() => import('@/features/dashboard/HomePage').then((m) => ({ default: m.HomePage })))
const MyPlansPage = lazyPage(() => import('@/features/plans/MyPlansPage').then((m) => ({ default: m.MyPlansPage })))
const PlanFormPage = lazyPage(() => import('@/features/plans/PlanFormPage').then((m) => ({ default: m.PlanFormPage })))
const OwnerPlanPage = lazyPage(() => import('@/features/plans/OwnerPlanPage').then((m) => ({ default: m.OwnerPlanPage })))
const ReviewPaymentsPage = lazyPage(() =>
  import('@/features/plans/ReviewPaymentsPage').then((m) => ({ default: m.ReviewPaymentsPage })),
)
const SharedPlansPage = lazyPage(() => import('@/features/shared/SharedPlansPage').then((m) => ({ default: m.SharedPlansPage })))
const MemberPlanPage = lazyPage(() => import('@/features/shared/MemberPlanPage').then((m) => ({ default: m.MemberPlanPage })))
const CalendarPage = lazyPage(() => import('@/features/calendar/CalendarPage').then((m) => ({ default: m.CalendarPage })))
const NotificationsPage = lazyPage(() =>
  import('@/features/notifications/NotificationsPage').then((m) => ({ default: m.NotificationsPage })),
)
const ProfilePage = lazyPage(() => import('@/features/profile/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const KitPage = lazyPage(() => import('@/features/kit/KitPage').then((m) => ({ default: m.KitPage })))
const NotFoundPage = lazyPage(() => import('@/features/NotFoundPage').then((m) => ({ default: m.NotFoundPage })))
const NotFoundInApp = lazyPage(() =>
  import('@/features/NotFoundPage').then((m) => ({ default: () => <m.NotFoundPage inApp /> })),
)

function wrapPage(Page, fallback) {
  return (
    <Suspense fallback={fallback}>
      <ErrorBoundary>
        <Page />
      </ErrorBoundary>
    </Suspense>
  )
}

function AppRoot() {
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

function AppLayout() {
  return (
    <RequireAuth>
      <AppShell />
    </RequireAuth>
  )
}

export const router = createBrowserRouter([
  {
    element: <AppRoot />,
    children: [
      { path: '/', element: wrapPage(LandingPage, <LandingFallback />) },
      { path: '/login', element: <GuestOnly>{wrapPage(LoginPage, <SkeletonCard lines={4} />)}</GuestOnly> },
      { path: '/register', element: <GuestOnly>{wrapPage(RegisterPage, <SkeletonCard lines={4} />)}</GuestOnly> },
      { path: '/verify-email', element: wrapPage(VerifyEmailPage, <SkeletonCard lines={3} />) },
      { path: '/reset-password', element: wrapPage(ResetPasswordPage, <SkeletonCard lines={3} />) },
      {
        path: '/invite/:token',
        element: wrapPage(InvitePage, <InvitePageSkeleton />),
      },
      {
        path: '/join/:token',
        element: wrapPage(PlanJoinPage, <InvitePageSkeleton />),
      },
      { path: '/kit', element: wrapPage(KitPage, <SkeletonCard tall lines={4} />) },
      {
        path: '/app',
        element: (
          <ErrorBoundary>
            <AppLayout />
          </ErrorBoundary>
        ),
        children: [
          { index: true, element: wrapPage(HomePage, <AppHomeFallback />) },
          { path: 'plans', element: wrapPage(MyPlansPage, <ListPageFallback />) },
          { path: 'plans/new', element: wrapPage(PlanFormPage, <PlanFormSkeleton />) },
          { path: 'plans/:id', element: wrapPage(OwnerPlanPage, <DetailPageFallback />) },
          { path: 'plans/:id/edit', element: wrapPage(PlanFormPage, <PlanFormSkeleton />) },
          { path: 'plans/:id/review', element: wrapPage(ReviewPaymentsPage, <ReviewPaymentsSkeleton />) },
          { path: 'shared', element: wrapPage(SharedPlansPage, <ListPageFallback />) },
          { path: 'shared/:id', element: wrapPage(MemberPlanPage, <DetailPageFallback />) },
          { path: 'calendar', element: wrapPage(CalendarPage, <SkeletonCard tall />) },
          { path: 'notifications', element: wrapPage(NotificationsPage, <ListPageFallback />) },
          { path: 'profile', element: wrapPage(ProfilePage, <SkeletonCard lines={5} />) },
          { path: '*', element: wrapPage(NotFoundInApp, <SkeletonCard />) },
        ],
      },
      { path: '*', element: wrapPage(NotFoundPage, <SkeletonCard />) },
    ],
  },
])