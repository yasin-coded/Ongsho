import { lazyPage } from './lazyPage'

export const LandingPage = lazyPage(() => import('@/features/landing/LandingPage').then((m) => ({ default: m.LandingPage })))
export const LoginPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.LoginPage })))
export const RegisterPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.RegisterPage })))
export const VerifyEmailLinkPage = lazyPage(() =>
  import('@/features/auth/VerificationPages').then((m) => ({ default: m.VerifyEmailLinkPage })),
)
export const RegistrationCheckEmailPage = lazyPage(() =>
  import('@/features/auth/VerificationPages').then((m) => ({ default: m.RegistrationCheckEmailPage })),
)
export const RegistrationVerifiedPage = lazyPage(() =>
  import('@/features/auth/VerificationPages').then((m) => ({ default: m.RegistrationVerifiedPage })),
)
export const EmailChangeVerifiedPage = lazyPage(() =>
  import('@/features/auth/VerificationPages').then((m) => ({ default: m.EmailChangeVerifiedPage })),
)
export const ResetPasswordPage = lazyPage(() => import('@/features/auth/AuthPages').then((m) => ({ default: m.ResetPasswordPage })))
export const InvitePage = lazyPage(() => import('@/features/auth/InvitePage').then((m) => ({ default: m.InvitePage })))
export const PlanJoinPage = lazyPage(() => import('@/features/auth/PlanJoinPage').then((m) => ({ default: m.PlanJoinPage })))
export const MyPlansPage = lazyPage(() => import('@/features/plans/MyPlansPage').then((m) => ({ default: m.MyPlansPage })))
export const PlanFormPage = lazyPage(() => import('@/features/plans/PlanFormPage').then((m) => ({ default: m.PlanFormPage })))
export const OwnerPlanPage = lazyPage(() => import('@/features/plans/OwnerPlanPage').then((m) => ({ default: m.OwnerPlanPage })))
export const ReviewPaymentsPage = lazyPage(() =>
  import('@/features/plans/ReviewPaymentsPage').then((m) => ({ default: m.ReviewPaymentsPage })),
)
export const SharedPlansPage = lazyPage(() => import('@/features/shared/SharedPlansPage').then((m) => ({ default: m.SharedPlansPage })))
export const MemberPlanPage = lazyPage(() => import('@/features/shared/MemberPlanPage').then((m) => ({ default: m.MemberPlanPage })))
export const CalendarPage = lazyPage(() => import('@/features/calendar/CalendarPage').then((m) => ({ default: m.CalendarPage })))
export const NotificationsPage = lazyPage(() =>
  import('@/features/notifications/NotificationsPage').then((m) => ({ default: m.NotificationsPage })),
)
export const ProfilePage = lazyPage(() => import('@/features/profile/ProfilePage').then((m) => ({ default: m.ProfilePage })))
export const KitPage = lazyPage(() => import('@/features/kit/KitPage').then((m) => ({ default: m.KitPage })))
export const NotFoundPage = lazyPage(() => import('@/features/NotFoundPage').then((m) => ({ default: m.NotFoundPage })))
export const NotFoundInApp = lazyPage(() =>
  import('@/features/NotFoundPage').then((m) => ({ default: () => <m.NotFoundPage inApp /> })),
)