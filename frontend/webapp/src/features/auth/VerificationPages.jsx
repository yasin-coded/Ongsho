import { useEffect, useRef } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BadgeCheck, MailCheck, RotateCw } from 'lucide-react'
import * as accounts from '@/api/accounts'
import { useAuth } from '@/auth/auth-context'
import { Button } from '@/components/ui/Button'
import { ResendTimer } from '@/components/ui/ResendTimer'
import { useCountdown, useSingleFlight } from '@/hooks/useCountdown'
import { AuthLayout } from './AuthLayout'

/** Must match RESEND_VERIFICATION_COOLDOWN_SECONDS in backend/accounts/services.py. */
export const RESEND_COOLDOWN_SECONDS = 60

const REGISTRATION_VERIFY_ERRORS = {
  invalid_token: 'This verification link is invalid or has expired.',
  throttled: 'Too many attempts. Wait a few minutes, then open the link again.',
}

const EMAIL_CHANGE_VERIFY_ERRORS = {
  invalid_token: 'This link is invalid or has already been used.',
  expired_token: 'This link has expired. Log in and request a new confirmation email from your profile.',
  email_change_stale: 'This link is no longer valid. The request may have been replaced or cancelled.',
  email_taken: 'That email address is already in use on another account.',
  account_inactive: 'This account is not active.',
  throttled: 'Too many attempts. Wait a few minutes, then open the link again.',
}

function messageFor(map, error, fallback) {
  if (!error) return null
  return map[error.code] ?? fallback
}

function useRunOncePerToken(token, run) {
  const started = useRef(null)
  useEffect(() => {
    if (!token || started.current === token) return
    started.current = token
    run()
  }, [token, run])
}

function LoginButton({ children = 'Log in' }) {
  return (
    <Link to="/login" className="neo-btn btn-accept neo-btn--block">
      {children}
    </Link>
  )
}

function Checking({ title }) {
  return (
    <AuthLayout title={title} subtitle="This only takes a moment.">
      <p className="t-meta" role="status">
        Checking your link…
      </p>
    </AuthLayout>
  )
}

/**
 * Shown right after sign-up. The address travels in history state (kept across refresh and back/forward
 * in this tab, never in the URL or storage). Old `?email=` links are moved into state and stripped.
 */
export function RegistrationCheckEmailPage() {
  const location = useLocation()
  const [params] = useSearchParams()
  const fromQuery = (params.get('email') ?? '').trim()
  if (fromQuery) {
    return <Navigate to="/register/check-email" replace state={{ ...(location.state ?? {}), email: fromQuery }} />
  }
  const email = typeof location.state?.email === 'string' ? location.state.email.trim() : ''
  return <CheckEmail email={email} />
}

function CheckEmail({ email }) {
  const [left, setLeft] = useCountdown(RESEND_COOLDOWN_SECONDS)
  const resend = useMutation({
    mutationFn: () => accounts.resendVerification({ email }),
    onSuccess: () => setLeft(RESEND_COOLDOWN_SECONDS),
    onError: (err) => {
      if (err?.retryAfter) setLeft(err.retryAfter)
    },
  })
  const runResend = useSingleFlight(resend)
  const coolingDown = left > 0

  return (
    <AuthLayout
      title="Check your inbox"
      subtitle="We sent you a verification email. Open it and follow the link to finish setting up your account."
      footer={
        <p>
          Used the wrong email?{' '}
          <Link to="/register" className="text-link">
            Start again
          </Link>
        </p>
      }
    >
      <div className="grid gap-5">
        <div className="neo-box neo-box--flat neo-box--highlight row flex-nowrap items-start gap-3">
          <MailCheck aria-hidden="true" className="size-6 flex-none" />
          <div className="grid min-w-0 gap-1">
            <p className="t-label">Sent to</p>
            <p className="font-bold break-all">{email || 'the address you signed up with'}</p>
          </div>
        </div>
        <p className="t-meta">The link works once and expires in 3 days. If you cannot find the email, check your spam folder.</p>

        {email ? (
          <div className="grid gap-3">
            <ResendTimer seconds={left} />
            <Button
              variant="ghost"
              block
              icon={RotateCw}
              onClick={() => runResend()}
              disabled={coolingDown}
              busy={resend.isPending}
            >
              Resend verification email
            </Button>
            {resend.isSuccess && !resend.isPending ? (
              <p className="t-meta" role="status">
                If this account still needs verifying, a new link is on its way to {email}.
              </p>
            ) : null}
            {resend.isError && !resend.isPending ? (
              <p role="alert" className="field__error">
                {resend.error?.message ?? 'We could not send a new link. Try again in a moment.'}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="t-meta">
            To get a new link, <Link to="/login" className="text-link">log in</Link> with the email and password you signed up with.
          </p>
        )}
      </div>
    </AuthLayout>
  )
}

/** Target of the link in the sign-up verification email. */
export function RegistrationVerifiedPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const verify = useMutation({ mutationFn: () => accounts.verifyEmail({ token }) })
  useRunOncePerToken(token, verify.mutate)

  if (token && (verify.isIdle || verify.isPending)) return <Checking title="Verifying your email" />

  if (verify.isSuccess) {
    return (
      <AuthLayout title="Email verified!" subtitle="Your account is ready.">
        <div className="grid gap-5">
          <div className="neo-box neo-box--flat neo-box--highlight row flex-nowrap items-start gap-3" role="status">
            <BadgeCheck aria-hidden="true" className="size-6 flex-none" />
            <p className="min-w-0">Your account&apos;s email address has been verified. Log in to start using Ongsho.</p>
          </div>
          <LoginButton />
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="This link did not work" subtitle="Your email has not been verified by this link.">
      <div className="grid gap-5">
        <p role="alert" className="field__error">
          {token
            ? messageFor(REGISTRATION_VERIFY_ERRORS, verify.error, 'We could not verify this link.')
            : 'This link is incomplete. Open the link from the email again.'}
        </p>
        <p className="t-meta">
          Links work once and expire after 3 days. Log in with your email and password; if your email still needs verifying, you can send a new link from there.
        </p>
        <LoginButton>Go to log in</LoginButton>
      </div>
    </AuthLayout>
  )
}

/** Target of the link sent to a new address from Profile → Change email. */
export function EmailChangeVerifiedPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const queryClient = useQueryClient()
  const { endSession } = useAuth()
  const verify = useMutation({
    mutationFn: () => accounts.verifyEmailChange({ token }),
    onSuccess: () => {
      endSession()
      queryClient.clear()
    },
  })
  useRunOncePerToken(token, verify.mutate)

  if (token && (verify.isIdle || verify.isPending)) return <Checking title="Confirming your new email" />

  if (verify.isSuccess) {
    const newEmail = verify.data?.email ?? ''
    return (
      <AuthLayout title="Your new email has been verified!" subtitle="You have been signed out everywhere for safety.">
        <div className="grid gap-5">
          <div className="neo-box neo-box--flat neo-box--highlight row flex-nowrap items-start gap-3" role="status">
            <BadgeCheck aria-hidden="true" className="size-6 flex-none" />
            <div className="grid min-w-0 gap-2">
              <p>Your account&apos;s email address has been successfully updated. You can now log in using your new email address.</p>
              {newEmail ? <p className="font-bold break-all">{newEmail}</p> : null}
            </div>
          </div>
          <p className="t-meta">Your password is unchanged.</p>
          <LoginButton />
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="We could not verify your new email" subtitle="Your account email has not changed.">
      <div className="grid gap-5">
        <p role="alert" className="field__error">
          {token
            ? messageFor(EMAIL_CHANGE_VERIFY_ERRORS, verify.error, 'We could not confirm this email change.')
            : 'This link is incomplete. Open the link from the email again.'}
        </p>
        <p className="t-meta">Keep logging in with your current email. You can request a new link from your profile.</p>
        <LoginButton />
      </div>
    </AuthLayout>
  )
}

/**
 * `/verify-email` is the path in every email the backend has sent, so it stays a stable entry point:
 * `?type=email-change&token=` (email change), `?token=` (sign-up), `?email=` (old sign-up redirect).
 */
export function VerifyEmailLinkPage() {
  const [params] = useSearchParams()
  const type = params.get('type')
  const token = params.get('token')
  const email = params.get('email')
  const tokenQuery = token ? `?${new URLSearchParams({ token })}` : ''

  if (type === 'email-change') return <Navigate to={`/email-change/confirm${tokenQuery}`} replace />
  if (type) {
    return (
      <AuthLayout title="This link did not work" subtitle="We do not recognise this verification link.">
        <div className="grid gap-5">
          <p role="alert" className="field__error">
            Open the link from the email again, or log in to request a new one.
          </p>
          <LoginButton />
        </div>
      </AuthLayout>
    )
  }
  if (token) return <Navigate to={`/verify-email/confirm${tokenQuery}`} replace />
  return <Navigate to="/register/check-email" replace state={email ? { email } : undefined} />
}
