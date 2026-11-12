import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useMutation } from '@tanstack/react-query'
import { ArrowRight, Check, Circle, MailCheck } from 'lucide-react'
import * as accounts from '@/api/accounts'
import { useAuth } from '@/auth/auth-context'
import { focusFirstInvalid } from '@/lib/formFocus'
import { validateEmail, validatePassword, validateName, validatePasswordRepeat } from '@/lib/validation'
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
  const [form, setForm] = useState({ email: '', password: '' })
  const [clientFields, setClientFields] = useState({})
  const [banner, setBanner] = useState(() => {
    try {
      const msg = sessionStorage.getItem('ongsho:authMessage')
      if (msg) sessionStorage.removeItem('ongsho:authMessage')
      return msg
    } catch {
      return null
    }
  })
  const m = useMutation({
    mutationFn: login,
    onSuccess: () => {
      const fromQuery = new URLSearchParams(location.search).get('next')
      const fromState = location.state?.from
      navigate(fromQuery ?? fromState ?? '/app', { replace: true })
    },
  })
  const f = { ...clientFields, ...m.error?.fields }

  const blurValidate = (field, value) => {
    const err =
      field === 'email' ? validateEmail(value) : field === 'password' && value ? validatePassword(value) : null
    setClientFields((prev) => {
      const next = { ...prev }
      if (err) next[field] = err
      else delete next[field]
      return next
    })
  }

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
          const fields = {}
          const em = validateEmail(form.email)
          if (em) fields.email = em
          if (!form.password) fields.password = 'Enter your password.'
          if (Object.keys(fields).length) {
            setClientFields(fields)
            focusFirstInvalid()
            return
          }
          setClientFields({})
          m.mutate(form)
        }}
      >
        {banner && (
          <p role="status" className="field__error">
            {banner}
          </p>
        )}
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          maxLength={254}
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          onBlur={() => blurValidate('email', form.email)}
          error={f.email}
        />
        <PasswordInput
          autoComplete="current-password"
          maxLength={128}
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          onBlur={() => blurValidate('password', form.password)}
          error={f.password}
        />
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
  const [clientFields, setClientFields] = useState({})
  const m = useMutation({ mutationFn: accounts.register, onSuccess: (data) => navigate(`/verify-email?email=${encodeURIComponent(data.email)}`) })
  const f = { ...clientFields, ...(m.error?.fields ?? {}) }

  const blurValidate = (field, value) => {
    let err = null
    if (field === 'name') err = validateName(value)
    else if (field === 'email') err = validateEmail(value)
    else if (field === 'password' && value) err = validatePassword(value)
    else if (field === 'repeat' && value) err = validatePasswordRepeat(form.password, value)
    setClientFields((prev) => {
      const next = { ...prev }
      if (err) next[field] = err
      else delete next[field]
      return next
    })
  }

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
          const fields = {}
          const nm = validateName(form.name)
          if (nm) fields.name = nm
          const em = validateEmail(form.email)
          if (em) fields.email = em
          const pw = validatePassword(form.password)
          if (pw) fields.password = pw
          const rp = validatePasswordRepeat(form.password, form.repeat)
          if (rp) fields.repeat = rp
          if (Object.keys(fields).length) {
            setClientFields(fields)
            focusFirstInvalid()
            return
          }
          setClientFields({})
          m.mutate(form)
        }}
      >
        <Input label="Name" autoComplete="name" maxLength={255} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} onBlur={() => blurValidate('name', form.name)} error={f.name} />
        <Input label="Email" type="email" autoComplete="email" maxLength={254} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} onBlur={() => blurValidate('email', form.email)} error={f.email} />
        <div className="grid gap-3">
          <PasswordInput autoComplete="new-password" maxLength={128} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} onBlur={() => blurValidate('password', form.password)} error={f.password} />
          <PasswordRules password={form.password} />
        </div>
        <PasswordInput label="Confirm password" autoComplete="new-password" maxLength={128} value={form.repeat} onChange={(e) => setForm({ ...form, repeat: e.target.value })} onBlur={() => blurValidate('repeat', form.repeat)} error={f.repeat} />
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
  const email = params.get('email') ?? ''
  const verifyToken = params.get('token')
  const [left, setLeft] = useState(60)
  const resend = useMutation({ mutationFn: () => accounts.resendVerification({ email }), onSuccess: () => setLeft(60) })
  const verified = useMutation({ mutationFn: () => accounts.verifyEmail({ token: verifyToken }) })

  useEffect(() => {
    if (!verifyToken) return undefined
    verified.mutate()
    return undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per token in the URL
  }, [verifyToken])

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
  const uid = params.get('uid')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [clientFields, setClientFields] = useState({})
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
              const fields = {}
              const pw = validatePassword(password)
              if (pw) fields.password = pw
              if (Object.keys(fields).length) {
                setClientFields(fields)
                focusFirstInvalid()
                return
              }
              setClientFields({})
              set.mutate({ password, uid, token })
            }}
          >
            <div className="grid gap-3">
              <PasswordInput
                label="New password"
                autoComplete="new-password"
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onBlur={() => {
                  const pw = password ? validatePassword(password) : null
                  setClientFields((p) => {
                    const next = { ...p }
                    if (pw) next.password = pw
                    else delete next.password
                    return next
                  })
                }}
                error={clientFields.password ?? set.error?.fields?.newPassword ?? set.error?.fields?.password}
              />
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
            const em = validateEmail(email)
            if (em) {
              setClientFields({ email: em })
              focusFirstInvalid()
              return
            }
            setClientFields({})
            ask.mutate({ email })
          }}
        >
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => {
              const em = validateEmail(email)
              setClientFields((p) => {
                const next = { ...p }
                if (em) next.email = em
                else delete next.email
                return next
              })
            }}
            error={clientFields.email ?? ask.error?.fields?.email}
          />
          <Button type="submit" variant="accept" block busy={ask.isPending}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
