import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, X } from 'lucide-react'
import { getInvite, getMe } from '@/api/accounts'
import { snapshotNavCounts } from '@/api/dashboard'
import { acceptInvite, acceptInviteAsNewUser, declineInvite } from '@/api/shared'
import { useAuth } from '@/auth/auth-context'
import { useAction } from '@/hooks/useAction'
import { focusFirstInvalid } from '@/lib/formFocus'
import { validateName, validatePassword } from '@/lib/validation'
import { fmtShort } from '@/lib/dates'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Field'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { ErrorBox, InvitePageSkeleton } from '@/components/ui/Misc'
import { shouldShowInitialSkeleton } from '@/lib/queryLoading'
import { AuthLayout } from './AuthLayout'

export function InvitePage() {
  const { token } = useParams()
  const { isAuthed, session, signInDirect, adoptSession } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['invite', token], queryFn: () => getInvite(token) })
  const { data: invite, error, refetch } = query
  const [form, setForm] = useState({ name: '', password: '' })
  const [clientFields, setClientFields] = useState({})

  const signUp = useMutation({
    mutationFn: () => acceptInviteAsNewUser(token, form),
    onSuccess: async (result) => {
      if (result?.access) adoptSession({ access: result.access, user: result.user })
      else signInDirect({ name: form.name, email: invite.email })
      const snap = snapshotNavCounts()
      if (snap) queryClient.setQueryData(['nav-counts'], snap)
      await queryClient.invalidateQueries({ refetchType: 'all' })
      navigate('/app')
    },
  })
  const accept = useAction(() => acceptInvite({ token, id: invite.id }), { onSuccess: (r) => navigate(`/app/shared/${r.planId}`) })
  const decline = useAction(() => declineInvite(invite.id), { onSuccess: () => navigate('/app/notifications') })
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe, enabled: isAuthed })

  if (shouldShowInitialSkeleton(query)) {
    return (
      <AuthLayout title="Opening your invite">
        <InvitePageSkeleton />
      </AuthLayout>
    )
  }
  if (error) {
    return (
      <AuthLayout title="Opening your invite">
        <ErrorBox error={error} onRetry={refetch} />
      </AuthLayout>
    )
  }

  const unusable = invite.notFound || invite.status !== 'pending' || invite.expired
  if (unusable) {
    const why = invite.notFound
      ? 'This invite link does not exist. Check you copied all of it.'
      : invite.expired
        ? `This invite expired on ${fmtShort(invite.expiresOn)}. Ask ${invite.from} for a new one.`
        : `This invite was already ${invite.status}. Each invite works once.`
    return (
      <AuthLayout title="This invite cannot be used" subtitle={why}>
        <Link to="/" className="neo-btn btn-ghost neo-btn--block">
          Go to the home page
        </Link>
      </AuthLayout>
    )
  }

  const existingUser = isAuthed && (me?.email ?? session?.user?.email) === invite.email
  const wrongAccount = isAuthed && !existingUser

  return (
    <AuthLayout title={`Join ${invite.planName}`} subtitle={`Invited by ${invite.from}.`}>
      <div className="neo-box neo-box--flat neo-box--highlight row gap-4">
        <ServiceLogo serviceKey={invite.serviceKey} name={invite.planName} size="compact" />
        <div className="grid gap-1">
          <p className="t-sub">{invite.planName}</p>
          <p className="t-meta">
            {invite.seats} seats · invite expires {fmtShort(invite.expiresOn)}
          </p>
        </div>
      </div>

      {existingUser && (
        <div className="grid gap-4">
          <p>This invite is for your account. Nobody is added to a plan until they accept.</p>
          <div className="row">
            <Button variant="accept" icon={Check} busy={accept.isPending} onClick={() => accept.mutate()}>
              Accept
            </Button>
            <Button variant="ghost" icon={X} busy={decline.isPending} onClick={() => decline.mutate()}>
              Decline
            </Button>
          </div>
          {accept.error && (
            <p className="field__error" role="alert">
              {accept.error.message}
            </p>
          )}
        </div>
      )}

      {wrongAccount && (
        <p className="neo-box neo-box--flat neo-box--danger">
          You are logged in with a different email. This invite only works for <strong>{invite.email}</strong>. Ask {invite.from} to invite your email instead.
        </p>
      )}

      {!isAuthed && (
        <form
          className="grid gap-5"
          noValidate
          onSubmit={(e) => {
            e.preventDefault()
            const fields = {}
            const nm = validateName(form.name)
            if (nm) fields.name = nm
            const pw = validatePassword(form.password)
            if (pw) fields.password = pw
            if (Object.keys(fields).length) {
              setClientFields(fields)
              focusFirstInvalid()
              return
            }
            setClientFields({})
            signUp.mutate()
          }}
        >
          <Input label="Email" value={invite.email} locked help="Opening this invite from that inbox proves the email is yours." />
          <Input
            label="Your name"
            autoComplete="name"
            maxLength={255}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            onBlur={() => {
              const nm = validateName(form.name)
              setClientFields((p) => {
                const next = { ...p }
                if (nm) next.name = nm
                else delete next.name
                return next
              })
            }}
            error={clientFields.name ?? signUp.error?.fields?.name}
          />
          <PasswordInput
            label="Choose a password"
            autoComplete="new-password"
            maxLength={128}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            onBlur={() => {
              const pw = form.password ? validatePassword(form.password) : null
              setClientFields((p) => {
                const next = { ...p }
                if (pw) next.password = pw
                else delete next.password
                return next
              })
            }}
            error={clientFields.password ?? signUp.error?.fields?.password}
            help="At least 8 characters."
          />
          <Button type="submit" variant="accept" block icon={ArrowRight} busy={signUp.isPending}>
            Create account and join
          </Button>
          <p className="t-meta">
            Already have an account with this email?{' '}
            <Link to="/login" state={{ from: `/invite/${token}` }} className="text-link">
              Log in to accept
            </Link>
          </p>
        </form>
      )}
    </AuthLayout>
  )
}
