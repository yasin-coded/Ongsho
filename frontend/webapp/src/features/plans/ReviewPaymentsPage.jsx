import { useState } from 'react'
import { useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Check, CheckCheck, HandCoins, X } from 'lucide-react'
import { getReview } from '@/api/plans'
import { confirmPayment, reversePayment } from '@/api/payments'
import { useAction } from '@/hooks/useAction'
import { fmtShort, fmtWhen, plural } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead, StatCard } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { MethodTag, Pill, StatusDot } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { CopyField, EmptyState, SkeletonCard } from '@/components/ui/Misc'
import { Loadable } from '@/features/common/PlanBits'
import { NotFoundPage } from '@/features/NotFoundPage'
import { RejectPaymentModal, WaiveModal } from './PaymentModals'

function ReviewCard({ p, onReject, onWaive }) {
  const accept = useAction(() => confirmPayment(p.id))
  const others = p.covers.filter((c) => !c.self)
  return (
    <Box as="article" className="grid gap-5" aria-label={`${p.name}, ${formatBDT(p.amount)}`}>
      <div className="flex flex-wrap items-start gap-4">
        <Avatar name={p.name} color={p.avatarColor} size="md" decorative />
        <div className="grid min-w-0 flex-1 gap-1">
          <p className="t-sub">{p.name}</p>
          <p className="t-meta break-all">{p.email}</p>
          {p.leaveRequested && (
            <Pill small fill="#846ace" className="w-fit">
              Asked to leave
            </Pill>
          )}
        </div>
        <p className="t-mid">{formatBDT(p.amount, { trim: true })}</p>
      </div>
      <dl className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-1">
          <dt className="t-label">Payment method</dt>
          <dd>
            <MethodTag method={p.method} />
          </dd>
        </div>
        <div className="grid gap-1">
          <dt className="t-label">Sent for review</dt>
          <dd>{fmtWhen(p.submittedAt)}</dd>
        </div>
        <div className="grid gap-1">
          <dt className="t-label">Due for</dt>
          <dd>{p.cycleLabel} cycle</dd>
        </div>
      </dl>
      <CopyField label="Transaction ID" value={p.tid} />
      {others.length > 0 && (
        <ul className="grid gap-1">
          {others.map((c) => (
            <li key={c.dueId} className="t-meta font-bold">
              Also covers: {c.name}’s {c.monthLong} share ({formatBDT(c.amount, { trim: true })})
            </li>
          ))}
        </ul>
      )}
      <p className="t-meta">Rejecting sends this due back to Due, and {p.firstName} is told.</p>
      <div className="row justify-end">
        <Button variant="waive" icon={HandCoins} onClick={() => onWaive(p)}>
          Waive
        </Button>
        <Button variant="reject" icon={X} onClick={() => onReject(p)}>
          Reject
        </Button>
        <Button variant="accept" icon={Check} busy={accept.busy} onClick={() => accept.run()}>
          Accept
        </Button>
      </div>
    </Box>
  )
}

function DecidedRow({ d }) {
  const reverse = useAction(() => reversePayment(d.paymentId), { tone: 'due' })
  const detail = d.isOwnerSeat
    ? 'No proof needed for your own seat'
    : d.status === 'waived'
      ? `Waived${d.waiverNote ? `: ${d.waiverNote}` : ''}`
      : [d.method && <MethodTag key="m" method={d.method} />, d.tid && `ID ${d.tid}`, d.recordedByOwner && 'recorded by owner', d.decidedOn && `confirmed on ${fmtShort(d.decidedOn)}`].filter(Boolean)
  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <Avatar name={d.name} color={d.avatarColor} size="sm" decorative />
      <div className="min-w-0 flex-[1_1_14rem]">
        <p className="font-bold">{d.isOwnerSeat ? `${d.name} (you)` : d.name}</p>
        <p className="t-meta row gap-1.5">{Array.isArray(detail) ? detail.map((x, i) => <span key={i}>{i > 0 && '· '}{x}</span>) : detail}</p>
      </div>
      <span className="t-num font-bold">{formatBDT(d.amount, { trim: true })}</span>
      <StatusDot status={d.status} />
      {d.status === 'paid' && d.paymentId && !d.isOwnerSeat && (
        <button type="button" className="text-link t-meta" onClick={() => reverse.run()} disabled={reverse.busy}>
          Reverse
        </button>
      )}
    </li>
  )
}

function Review({ r }) {
  const [rejecting, setRejecting] = useState(null)
  const [waiving, setWaiving] = useState(null)
  const plan = r.plan
  return (
    <div className="stack-lg">
      <TopBar
        breadcrumb={[{ label: 'My Plans', to: '/app/plans' }, { label: plan.planName, to: `/app/plans/${plan.id}` }, { label: 'Review payments' }]}
        title="Review Payments"
        subtitle={`${plan.planName}${r.cycleLabel ? ` · ${r.cycleLabel.split(' ')[0]} cycle` : ''}${plan.nextRenewal ? ` · renews ${fmtShort(plan.nextRenewal)}` : ''}`}
        lead={<ServiceLogo serviceKey={plan.serviceKey} name={plan.planName} size="large" />}
      />
      <div className="stat-grid">
        <StatCard label="Waiting for you" value={r.waiting.count} helper={`${r.waiting.count === 1 ? 'transaction ID' : 'transaction IDs'}, ${formatBDT(r.waiting.total, { trim: true })} together`} />
        <StatCard label="Confirmed from members" value={formatBDT(r.confirmed.amount, { trim: true })} helper={`of ${formatBDT(r.confirmed.expected, { trim: true })} from ${plural(r.confirmed.members, 'member')}`} />
        <StatCard label="Still Due" value={r.stillDue} tone={r.stillDue ? '#d40000' : undefined} helper={r.stillDue ? `${r.stillDue === 1 ? 'member has' : 'members have'} not paid or sent an ID` : 'everyone has either paid or sent an ID'} />
      </div>

      <section aria-labelledby="waiting-title" className="grid gap-5">
        <h2 id="waiting-title" className="t-section">
          Waiting for Review
        </h2>
        <div className="two-col">
          <div className="stack">
            {r.pending.length ? (
              r.pending.map((p) => <ReviewCard key={p.id} p={p} onReject={setRejecting} onWaive={setWaiving} />)
            ) : (
              <Box>
                <EmptyState icon={CheckCheck} title="All reviewed" helper="No transaction IDs are waiting on this plan." />
              </Box>
            )}
          </div>
          <Box variant="highlight">
            <BoxHead title="How to check an ID?" />
            <ol className="grid gap-4">
              {[
                'Open the app you were paid in, such as bKash or your bank.',
                'Find the transaction ID in your history and match it with the one above.',
                'Check the amount is as expected, then confirm. If it does not match, reject it.',
              ].map((t) => (
                <li key={t} className="flex gap-3">
                  <span className="mt-1 size-4 flex-none rounded-full border-[0.1875rem] border-black bg-[#fff200]" aria-hidden="true" />
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          </Box>
        </div>
      </section>

      <Box>
        <BoxHead title="Already decided" sub={r.cycleLabel ? `${r.cycleLabel} cycle` : undefined} />
        {r.decided.length ? (
          <ul className="dashed-rows">
            {r.decided.map((d) => (
              <DecidedRow key={d.id} d={d} />
            ))}
          </ul>
        ) : (
          <p className="t-meta">Nothing decided yet this cycle.</p>
        )}
      </Box>

      {rejecting && <RejectPaymentModal paymentId={rejecting.id} name={rejecting.firstName} onClose={() => setRejecting(null)} />}
      {waiving && <WaiveModal paymentId={waiving.id} name={waiving.firstName} onClose={() => setWaiving(null)} />}
    </div>
  )
}

export function ReviewPaymentsPage() {
  const { id } = useParams()
  const query = useQuery({ queryKey: ['review', id], queryFn: () => getReview(id), retry: false })
  if (query.error?.status === 404) return <NotFoundPage inApp />
  return (
    <Loadable query={query} skeleton={<SkeletonCard lines={5} />}>
      {(r) => <Review r={r} />}
    </Loadable>
  )
}
