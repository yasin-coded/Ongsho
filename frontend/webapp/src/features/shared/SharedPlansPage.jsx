import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Inbox, LogOut, ReceiptText } from 'lucide-react'
import { getMyShared } from '@/api/shared'
import { memberSharedStatus } from '@/api/adapters/shared'
import { METHODS } from '@/lib/colors'
import { fmtShort, plural } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { perCycleLabel } from '@/mocks/schedule'
import { TopBar } from '@/components/layout/TopBar'
import { Box, StatCard } from '@/components/ui/Box'
import { Button, LinkButton } from '@/components/ui/Button'
import { MemberChip } from '@/components/ui/Avatar'
import { MethodTag, RoleTag, StatusPill } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { DashedDivider, EmptyState, FilterChip, Pagination, SkeletonCard } from '@/components/ui/Misc'
import { Loadable, renewText } from '@/features/common/PlanBits'
import { EnterTidModal } from './EnterTidModal'
import { RequestLeaveModal } from './RequestLeaveModal'

export function historyLine(row) {
  if (row.status === 'waived') return `${row.monthLabel} · Owner waived your payment`
  const parts = [row.monthLabel]
  if (row.method) parts.push(METHODS[row.method]?.label ?? row.method)
  if (row.tid) parts.push(`ID ${row.tid}`)
  return parts.join(' · ')
}

function SharedCard({ plan, onPay, onLeave }) {
  const status = memberSharedStatus(plan)
  return (
    <Box as="article" className="grid gap-5" aria-labelledby={`shared-${plan.id}`}>
      <div className="flex flex-wrap items-start gap-4">
        <ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="row" />
        <div className="grid min-w-0 flex-[1_1_16rem] gap-2">
          <h2 id={`shared-${plan.id}`} className="t-card">
            {plan.planName}
          </h2>
          <div className="row gap-2">
            <RoleTag role="member" />
            <StatusPill status={status} small />
          </div>
          <p className="t-meta">
            Owner: {plan.owner.firstName} · {renewText(plan)}
          </p>
        </div>
        <p className="basis-full text-left sm:ml-auto sm:basis-auto sm:text-right">
          <span className="t-mid block">{formatBDT(plan.myShare, { trim: true })}</span>
          <span className="t-meta block">{perCycleLabel(plan.cycle)} · your share</span>
        </p>
      </div>

      <div className="row gap-2">
        <span className="t-label">Members:</span>
        {plan.members.map((m) => (
          <MemberChip key={m.id} name={m.name} label={m.firstName} color={m.avatarColor} status={m.status} />
        ))}
      </div>

      <div className="row gap-2">
        <span className="t-label">Recommended:</span>
        <MethodTag method={plan.method} />
        {plan.note && <span className="t-meta">Note: {plan.note}</span>}
      </div>

      {plan.openDues.length > 0 && (
        <>
          <DashedDivider />
          <div className="row-between">
            <div>
              <p className="t-sub">Paid?</p>
              <p className="t-meta">
                {plural(plan.openDues.length, 'due')} open, {formatBDT(plan.openDues.reduce((a, d) => a + d.amount, 0))} in total. Pay {plan.owner.firstName}, then send the transaction ID.
              </p>
            </div>
            <Button variant="accept" icon={ReceiptText} onClick={() => onPay(plan.id)}>
              Enter TID
            </Button>
          </div>
        </>
      )}

      <DashedDivider />
      <div className="grid gap-3">
        <p className="t-label">Your payments for this plan</p>
        {plan.history.length ? (
          <ul className="dashed-rows">
            {plan.history.slice(0, 3).map((h) => (
              <li key={h.id} className="row-between py-2.5">
                <span className="t-meta font-bold">{historyLine(h)}</span>
                <span className="row gap-3">
                  <span className="t-num">{formatBDT(h.amount, { trim: true })}</span>
                  <StatusPill status={h.status} small />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="t-meta">No payments yet.</p>
        )}
        <p className="t-label">Total spent: {formatBDT(plan.totalSpent, { trim: true })}</p>
      </div>

      <div className="row">
        <LinkButton to={`/app/shared/${plan.id}`} variant="ghost" size="sm">
          See payments
        </LinkButton>
        {plan.me.leaveRequested ? (
          <span className="neo-pill neo-pill--sm" style={{ background: '#846ace', color: '#000' }}>
            Leave requested
          </span>
        ) : plan.canRequestLeave === false ? null : (
          <Button variant="reject-outline" size="sm" icon={LogOut} onClick={() => onLeave(plan)}>
            Request leave
          </Button>
        )}
      </div>
    </Box>
  )
}

export function SharedPlansPage() {
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [payFor, setPayFor] = useState(null)
  const [leaving, setLeaving] = useState(null)
  const query = useQuery({ queryKey: ['shared', { filter, page }], queryFn: () => getMyShared({ filter, page }), placeholderData: keepPreviousData })
  const pick = (f) => {
    setFilter(f)
    setPage(1)
  }

  return (
    <div className="stack-lg">
      <TopBar title="Shared Plans" subtitle="Plans you joined. You pay your share to the owner." />
      <Loadable
        query={query}
        skeleton={
          <div className="stack">
            <div className="stat-grid">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
            <SkeletonCard lines={4} />
          </div>
        }
      >
        {(d) => (
          <>
            <div className="stat-grid">
              <StatCard label="Your shares this month" value={formatBDT(d.totals.shares, { trim: true })} helper={`across ${plural(d.totals.planCount, 'plan')}`} />
              <StatCard
                label="Due now"
                value={formatBDT(d.totals.dueNow, { trim: true })}
                tone={d.totals.dueNow ? '#d40000' : undefined}
                helper={d.totals.dueNow ? `${d.totals.dueNames.join(', ')}${d.totals.dueBy ? `, by ${fmtShort(d.totals.dueBy)}` : ''}` : 'Nothing due. You are all caught up.'}
              />
              <StatCard label="Waiting for review" value={formatBDT(d.totals.waiting, { trim: true })} helper={d.totals.waiting ? `${d.totals.waitingNames.join(', ')}, ID sent` : 'No IDs waiting.'} />
            </div>

            <div className="grid gap-4">
              <div className="row" role="group" aria-label="Filter shared plans">
                <FilterChip selected={filter === 'all'} count={d.counts.all} onClick={() => pick('all')}>
                  All Plans
                </FilterChip>
                <FilterChip selected={filter === 'due'} count={d.counts.due} alert onClick={() => pick('due')}>
                  Due
                </FilterChip>
                <FilterChip selected={filter === 'pending'} count={d.counts.pending} onClick={() => pick('pending')}>
                  Pending
                </FilterChip>
                <FilterChip selected={filter === 'paid'} count={d.counts.paid} onClick={() => pick('paid')}>
                  Paid up
                </FilterChip>
              </div>
              {d.items.length ? (
                <div className="stack">
                  {d.items.map((p) => (
                    <SharedCard key={p.id} plan={p} onPay={setPayFor} onLeave={setLeaving} />
                  ))}
                </div>
              ) : (
                <Box>
                  <EmptyState icon={Inbox} title={filter === 'all' ? 'Nothing shared yet' : 'Nothing here'} helper={filter === 'all' ? 'When someone invites you to a plan, it shows up here.' : 'No plan matches this filter.'} />
                </Box>
              )}
            </div>
            <Pagination page={d.page} pages={d.pages} onPage={setPage} />
          </>
        )}
      </Loadable>
      {payFor && <EnterTidModal planId={payFor} onClose={() => setPayFor(null)} />}
      {leaving && <RequestLeaveModal plan={leaving} onClose={() => setLeaving(null)} />}
    </div>
  )
}
