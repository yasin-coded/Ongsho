import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, X } from 'lucide-react'
import { getMe } from '@/api/accounts'
import { acceptPlanJoin, getPlanJoin, signupAndJoinPlan } from '@/api/shared'
import { snapshotNavCounts } from '@/api/dashboard'
import { useAuth } from '@/auth/auth-context'
import { useAction } from '@/hooks/useAction'
import { focusFirstInvalid } from '@/lib/formFocus'
import { validateEmail, validateName, validatePassword } from '@/lib/validation'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Field'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { ErrorBox, InvitePageSkeleton } from '@/components/ui/Misc'
import { Modal } from '@/components/ui/Modal'
import { shouldShowInitialSkeleton } from '@/lib/queryLoading'
import { AuthLayout } from './AuthLayout'

export function PlanJoinPage() {
  const { token } = useParams()
  const { isAuthed, session, adoptSession, signInDirect } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['plan-join', token], queryFn: () => getPlanJoin(token) })
  const { data: plan, error, refetch } = query
  const [form, setForm] = useState({ email: '', name: '', password: '' })
  const [clientFields, setClientFields] = useState({})
  const [guestModalOpen, setGuestModalOpen] = useState(true)

  const signUp = useMutation({
    mutationFn: () => signupAndJoinPlan(token, form),
    onSuccess: async (result) => {
      if (result?.access) adoptSession({ access: result.access, user: result.user })
      else signInDirect({ name: form.name, email: form.email })
      const snap = snapshotNavCounts()
      if (snap) queryClient.setQueryData(['nav-counts'], snap)
      await queryClient.invalidateQueries({ refetchType: 'all' })
      navigate(result.planId ? `/app/shared/${result.planId}` : '/app')
    },
  })
  const accept = useAction(() => acceptPlanJoin(token), {
    onSuccess: (r) => navigate(`/app/shared/${r.planId}`),
  })
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe, enabled: isAuthed })

  if (shouldShowInitialSkeleton(query)) {
    return (
      <AuthLayout title="Opening invite">
        <InvitePageSkeleton />
      </AuthLayout>
    )
  }
  if (error || plan?.notFound) {
    return (
      <AuthLayout title="This link does not work">
        <ErrorBox error={error ?? { message: 'This invite link does not exist.' }} onRetry={refetch} />
      </AuthLayout>
    )
  }

  if (plan.planFull && !plan.alreadyMember) {
    return (
      <AuthLayout
        title={`${plan.planName} is full`}
        subtitle="Every seat is taken right now. Ask the owner to tell you when a spot opens."
      >
        <Link to="/" className="neo-btn btn-ghost neo-btn--block">
          Go to the home page
        </Link>
      </AuthLayout>
    )
  }

  if (plan.alreadyMember) {
    return (
      <AuthLayout title={`You are already in ${plan.planName}`} subtitle="Open it from Shared plans in the app.">
        <Button variant="primary-orange" block onClick={() => navigate(`/app/shared/${plan.planId}`)}>
          Open plan
        </Button>
      </AuthLayout>
    )
  }

  return (
    <>
      <AuthLayout title={`Join ${plan.planName}`} subtitle={`Invited by ${plan.from}. Shared plan · ${plan.seats} seats.`}>
        <div className="neo-box neo-box--flat neo-box--highlight row gap-4">
          <ServiceLogo serviceKey={plan.serviceKey} name={plan.planName} size="compact" />
          <div className="grid gap-1">
            <p className="t-sub">{plan.planName}</p>
            <p className="t-meta">
              {plan.seatsTaken} of {plan.seats} seats taken
            </p>
          </div>
        </div>

        {isAuthed && (
          <div className="grid gap-4">
            <p>Do you want to join this plan as {me?.email ?? session?.user?.email}?</p>
            <div className="row">
              <Button variant="accept" icon={Check} busy={accept.isPending} onClick={() => accept.mutate()}>
                Join plan
              </Button>
              <Button variant="ghost" icon={X} onClick={() => navigate('/app')}>
                Not now
              </Button>
            </div>
            {accept.error && (
              <p className="field__error" role="alert">
                {accept.error.message}
              </p>
            )}
          </div>
        )}

        {!isAuthed && (
          <form
            className="grid gap-5"
            noValidate
            onSubmit={(e) => {
              e.preventDefault()
              const fields = {}
              const em = validateEmail(form.email)
              if (em) fields.email = em
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
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              maxLength={254}
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              error={clientFields.email ?? signUp.error?.fields?.email}
            />
            <Input
              label="Your name"
              autoComplete="name"
              maxLength={255}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              error={clientFields.name ?? signUp.error?.fields?.name}
            />
            <PasswordInput
              label="Choose a password"
              autoComplete="new-password"
              maxLength={128}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              error={clientFields.password ?? signUp.error?.fields?.password}
              help="At least 8 characters."
            />
            <Button type="submit" variant="accept" block icon={ArrowRight} busy={signUp.isPending}>
              Create account and join
            </Button>
            <p className="t-meta">
              Already have an account?{' '}
              <Link to="/login" state={{ from: `/join/${token}` }} className="text-link">
                Log in to join
              </Link>
            </p>
          </form>
        )}
      </AuthLayout>

      {!isAuthed && guestModalOpen && (
        <Modal
          open
          onClose={() => setGuestModalOpen(false)}
          title="You have an invite"
          subtitle="Seems like you got an invite — make an account or log in to continue."
          footer={
            <div className="modal__footer row justify-end gap-2">
              <Button variant="ghost" onClick={() => setGuestModalOpen(false)}>
                Continue on this page
              </Button>
              <Link to="/login" state={{ from: `/join/${token}` }} className="neo-btn btn-ghost">
                Log in
              </Link>
            </div>
          }
        >
          <p className="t-meta">You can sign up below with any email, or log in if you already use Ongsho.</p>
        </Modal>
      )}
    </>
  )
}