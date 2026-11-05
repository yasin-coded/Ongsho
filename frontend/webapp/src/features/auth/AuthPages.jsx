import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import { ArrowRight, Check, Circle, MailCheck } from 'lucide-react'
import * as accounts from '@/api/accounts'
import { useAuth } from '@/auth/auth-context'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Field'
import { AuthLayout } from './AuthLayout'

function maskEmail(email) {
  const [name, domain] = (email ?? '').split('@')
  if (!domain) return email
  return `${name.charAt(0)}***@${domain}`
}

function FormError({ error }) {
  if (!error || Object.keys(error.fields ?? {}).length) return null
  return (
    <p role="alert" className="field__error">
      {error.message}
    </p>
  )
}

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: 'yasin@example.com', password: '' })
  const m = useMutation({ mutationFn: login, onSuccess: () => navigate(location.state?.from ?? '/app', { replace: true }) })
  const f = m.error?.fields ?? {}

  return (
    <AuthLayout
      title="Log in"
      subtitle="Welcome back. Your plans are where you left them."
      footer={
        <p>
          New to Ongsho?{' '}
          <Link to="/register" className="text-link">
            Create an account
          </Link>
        </p>
      }
    >
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          m.mutate(form)
        }}
      >
        <Input label="Email" type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} error={f.email} />
        <PasswordInput autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} error={f.password} help="Mock mode: any password works." />
        <Link to="/reset-password" className="text-link w-fit text-[0.95rem]">
          Forgot password?
        </Link>
        <FormError error={m.error} />
        <Button type="submit" variant="accept" block busy={m.isPending} icon={ArrowRight}>
          Log in
        </Button>
      </form>
    </AuthLayout>
  )
}

function PasswordRules({ password }) {
  return (
    <ul className="grid gap-1.5" aria-label="Password rules">
      {accounts.passwordRules(password).map((r) => (
        <li key={r.id} className="row t-meta gap-2">
          {r.ok ? <Check aria-hidden="true" className="size-4 text-[#1d7a00]" /> : <Circle aria-hidden="true" className="size-4" />}
          <span className={r.ok ? 'font-bold' : ''}>
            {r.label}
            <span className="sr-only">{r.ok ? ', done' : ', not yet'}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

export function RegisterPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', repeat: '' })
  const [repeatError, setRepeatError] = useState(null)
  const m = useMutation({ mutationFn: accounts.register, onSuccess: (data) => navigate(`/verify-email?email=${encodeURIComponent(data.email)}`) })
  const f = m.error?.fields ?? {}

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Everyone on a shared plan has their own account, so every payment belongs to a real person."
      footer={
        <p>
          Already have an account?{' '}
          <Link to="/login" className="text-link">
            Log in
          </Link>
        </p>
      }
    >
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (form.password !== form.repeat) {
            setRepeatError('The two passwords do not match.')
            return
          }
          setRepeatError(null)
          m.mutate(form)
        }}
      >
        <Input label="Name" autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} error={f.name} />
        <Input label="Email" type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} error={f.email} />
        <div className="grid gap-3">
          <PasswordInput autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} error={f.password} />
          <PasswordRules password={form.password} />
        </div>
        <PasswordInput label="Confirm password" autoComplete="new-password" value={form.repeat} onChange={(e) => setForm({ ...form, repeat: e.target.value })} error={repeatError} />
        <FormError error={m.error} />
        <Button type="submit" variant="accept" block busy={m.isPending} icon={ArrowRight}>
          Create account
        </Button>
      </form>
    </AuthLayout>
  )
}

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const email = params.get('email') ?? 'yasin@example.com'
  const [left, setLeft] = useState(60)
  const resend = useMutation({ mutationFn: accounts.resendVerification, onSuccess: () => setLeft(60) })

  useEffect(() => {
    if (left <= 0) return undefined
    const t = setTimeout(() => setLeft((v) => v - 1), 1000)
    return () => clearTimeout(t)
  }, [left])

  return (
    <AuthLayout title="Check your inbox" subtitle={`We sent a link to ${maskEmail(email)}. Open it to verify your email.`}>
      <div className="grid gap-5">
        <div className="neo-box neo-box--flat neo-box--highlight row gap-3">
          <MailCheck aria-hidden="true" className="size-6 flex-none" />
          <p className="t-meta">The link works once and expires in 24 hours. Check the spam folder if it is not there.</p>
        </div>
        <Button variant="ghost" block onClick={() => resend.mutate()} disabled={left > 0} busy={resend.isPending}>
          {left > 0 ? `Resend in ${left}s` : 'Resend the link'}
        </Button>
        <Link to="/login" className="neo-btn btn-accept neo-btn--block">
          I verified, log in
        </Link>
      </div>
    </AuthLayout>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const ask = useMutation({ mutationFn: accounts.requestPasswordReset })
  const set = useMutation({ mutationFn: accounts.confirmPasswordReset })

  if (token) {
    return (
      <AuthLayout title="Set a new password" subtitle="Pick something you have not used on Ongsho before.">
        {set.isSuccess ? (
          <div className="grid gap-4">
            <p className="font-bold">Your password is changed. Every other session was signed out.</p>
            <Link to="/login" className="neo-btn btn-accept neo-btn--block">
              Log in
            </Link>
          </div>
        ) : (
          <form
            className="grid gap-5"
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              set.mutate({ password })
            }}
          >
            <div className="grid gap-3">
              <PasswordInput label="New password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} error={set.error?.fields?.password} />
              <PasswordRules password={password} />
            </div>
            <Button type="submit" variant="accept" block busy={set.isPending}>
              Save new password
            </Button>
          </form>
        )}
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your email. If it has an account, a reset link is on its way."
      footer={
        <Link to="/login" className="text-link">
          Back to log in
        </Link>
      }
    >
      {ask.isSuccess ? (
        <div className="grid gap-4">
          <p className="font-bold">If {email} has an Ongsho account, the link is in its inbox now.</p>
          <Link to="/reset-password?token=mock-token" className="text-link w-fit">
            Open the link (mock)
          </Link>
        </div>
      ) : (
        <form
          className="grid gap-5"
          noValidate
          onSubmit={(e) => {
            e.preventDefault()
            ask.mutate({ email })
          }}
        >
          <Input label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} error={ask.error?.fields?.email} />
          <Button type="submit" variant="accept" block busy={ask.isPending}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
