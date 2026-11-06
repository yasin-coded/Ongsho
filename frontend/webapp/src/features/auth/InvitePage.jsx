import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, X } from 'lucide-react'
import { getInvite, getMe } from '@/api/accounts'
import { snapshotNavCounts } from '@/api/dashboard'
import { acceptInvite, acceptInviteAsNewUser, declineInvite } from '@/api/shared'
import { useAuth } from '@/auth/auth-context'
import { useAction } from '@/hooks/useAction'
import { formatBDT } from '@/lib/money'
import { fmtShort } from '@/lib/dates'
import { perCycleLabel } from '@/mocks/schedule'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Field'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { ErrorBox, Skeleton } from '@/components/ui/Misc'
import { AuthLayout } from './AuthLayout'

export function InvitePage() {
  const { token } = useParams()
  const { isAuthed, session, signInDirect } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: invite, isPending, error, refetch } = useQuery({ queryKey: ['invite', token], queryFn: () => getInvite(token) })
  const [form, setForm] = useState({ name: '', password: '' })

  const signUp = useMutation({
    mutationFn: () => acceptInviteAsNewUser(token, form),
    onSuccess: async () => {
      signInDirect({ name: form.name, email: invite.email })
      queryClient.setQueryData(['nav-counts'], snapshotNavCounts())
      await queryClient.invalidateQueries({ refetchType: 'all' })
      navigate('/app')
    },
  })
  const accept = useAction(() => acceptInvite(invite.id), { onSuccess: (r) => navigate(`/app/shared/${r.planId}`) })
  const decline = useAction(() => declineInvite(invite.id), { onSuccess: () => navigate('/app/notifications') })
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe, enabled: isAuthed })

  if (isPending) {
    return (
      <AuthLayout title="Opening your invite">
        <Skeleton className="h-24" />
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
    <AuthLayout title={`Join ${invite.planName}`} subtitle={`Invited by ${invite.from}. Your share is about ${formatBDT(invite.share)} ${perCycleLabel(invite.cycle)}.`}>
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
          {accept.error && <p className="field__error">{accept.error.message}</p>}
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
            signUp.mutate()
          }}
        >
          <Input label="Email" value={invite.email} locked help="Opening this invite from that inbox proves the email is yours." />
          <Input label="Your name" autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} error={signUp.error?.fields?.name} />
          <PasswordInput label="Choose a password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} error={signUp.error?.fields?.password} help="At least 8 characters." />
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
