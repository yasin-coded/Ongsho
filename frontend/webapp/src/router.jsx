import { createBrowserRouter } from 'react-router'
import { GuestOnly } from '@/auth/AuthProvider'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { SkeletonCard } from '@/components/ui/Misc'
import { HomePage } from '@/features/dashboard/HomePage'
import {
  DetailPageFallback,
  InvitePageSkeleton,
  LandingFallback,
  ListPageFallback,
  PlanFormSkeleton,
  ReviewPaymentsSkeleton,
} from '@/routes/RouteFallbacks'
import { AppLayout, AppRoot, WrappedRoute } from '@/routing/RouterShell'
import {
  CalendarPage,
  InvitePage,
  KitPage,
  LandingPage,
  LoginPage,
  MemberPlanPage,
  MyPlansPage,
  NotFoundInApp,
  NotFoundPage,
  NotificationsPage,
  OwnerPlanPage,
  PlanFormPage,
  PlanJoinPage,
  ProfilePage,
  RegisterPage,
  ResetPasswordPage,
  ReviewPaymentsPage,
  SharedPlansPage,
  VerifyEmailLinkPage,
  RegistrationCheckEmailPage,
  RegistrationVerifiedPage,
  EmailChangeVerifiedPage,
} from '@/routing/lazyRoutes'

function wrapPage(Page, fallback) {
  return <WrappedRoute page={Page} fallback={fallback} />
}

export const router = createBrowserRouter([
  {
    element: <AppRoot />,
    children: [
      { path: '/', element: wrapPage(LandingPage, <LandingFallback />) },
      { path: '/login', element: <GuestOnly>{wrapPage(LoginPage, <SkeletonCard lines={4} />)}</GuestOnly> },
      { path: '/register', element: <GuestOnly>{wrapPage(RegisterPage, <SkeletonCard lines={4} />)}</GuestOnly> },
      { path: '/register/check-email', element: wrapPage(RegistrationCheckEmailPage, <SkeletonCard lines={3} />) },
      { path: '/verify-email', element: wrapPage(VerifyEmailLinkPage, <SkeletonCard lines={3} />) },
      { path: '/verify-email/confirm', element: wrapPage(RegistrationVerifiedPage, <SkeletonCard lines={3} />) },
      { path: '/email-change/confirm', element: wrapPage(EmailChangeVerifiedPage, <SkeletonCard lines={3} />) },
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
          {
            index: true,
            element: (
              <ErrorBoundary>
                <HomePage />
              </ErrorBoundary>
            ),
          },
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