import { useSearchParams } from 'react-router'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Eye, Inbox, Plus } from 'lucide-react'
import { getSubscriptions } from '@/api/plans'
import { STATUS } from '@/lib/colors'
import { formatBDT } from '@/lib/money'
import { plural } from '@/lib/dates'
import { perCycleLabel } from '@/mocks/schedule'
import { TopBar } from '@/components/layout/TopBar'
import { Box, StatCard } from '@/components/ui/Box'
import { LinkButton } from '@/components/ui/Button'
import { MemberChip } from '@/components/ui/Avatar'
import { MethodTag, OwnerPlanPill, RoleTag } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { EmptyState, FilterChip, Pagination, ProgressBar, SkeletonCard } from '@/components/ui/Misc'
import { Loadable, ownerMeta } from '@/features/common/PlanBits'

function seatsText(plan) {
  if (!plan.shared) return 'just you'
  if (plan.mode === 'reseller') return plural(plan.seatsCap, 'buyer')
  return `${plural(plan.seatsCap, 'seat')} (1 is yours)`
}

function PlanCard({ plan }) {
  const reseller = plan.mode === 'reseller'
  const others = plan.members.filter((m) => !m.isOwnerSeat)
  return (
    <Box as="article" className="grid gap-5" aria-labelledby={`plan-${plan.id}`}>
      <div className="flex flex-wrap items-start gap-4">
        <ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="row" />
        <div className="grid min-w-0 flex-[1_1_16rem] gap-2">
          <h2 id={`plan-${plan.id}`} className="t-card">
            {plan.planName}
          </h2>
          <div className="row gap-2">
            {reseller ? <RoleTag role="reseller" /> : plan.shared ? <RoleTag role="owner" /> : <RoleTag role="solo" />}
            <OwnerPlanPill pill={plan.statusPill} small />
            {plan.rarelyUsed && <RoleTag role="rarely" />}
          </div>
          <p className="t-meta">{`${ownerMeta(plan, { seats: false })} · ${seatsText(plan)}`}</p>
        </div>
        <p className="basis-full text-left sm:ml-auto sm:basis-auto sm:text-right">
          <span className="t-mid block">{formatBDT(plan.price.amount, { trim: true })}</span>
          <span className="t-meta block">
            {perCycleLabel(plan.cycle)}
            {plan.shared && ` · ${formatBDT(plan.perSeat, { trim: true })} per seat`}
          </span>
        </p>
      </div>

      {plan.shared && (
        <div className="row gap-2">
          <span className="t-label">{reseller ? 'Buyers:' : 'Members:'}</span>
          {plan.members.length ? (
            plan.members.map((m) => <MemberChip key={m.id} name={m.name} label={m.isOwnerSeat ? 'You' : m.firstName} color={m.avatarColor} status={m.dueStatus ?? undefined} />)
          ) : (
            <span className="t-meta">Nobody yet. Invite people from the plan page.</span>
          )}
          {!others.length && plan.members.length > 0 && <span className="t-meta">Invite people from the plan page.</span>}
        </div>
      )}

      <div className="row-between border-t-[0.125rem] border-dashed border-[var(--color-dash)] pt-4">
        <div className="row gap-2">
          {plan.shared && (
            <>
              <span className="t-label">Recommended:</span>
              <MethodTag method={plan.method} />
            </>
          )}
          {plan.note && <span className="t-meta">Note: {plan.note}</span>}
        </div>
        <div className="row">
          {plan.pendingCount > 0 && (
            <LinkButton to={`/app/plans/${plan.id}/review`} variant="yellow" size="sm" icon={Eye}>
              Review payments
            </LinkButton>
          )}
          <LinkButton to={`/app/plans/${plan.id}`} variant="ghost" size="sm">
            Open plan
          </LinkButton>
        </div>
      </div>
    </Box>
  )
}

export function MyPlansPage() {
  const [params, setParams] = useSearchParams()
  const filter = params.get('filter') ?? 'all'
  const search = params.get('q') ?? ''
  const page = Number(params.get('page') ?? 1)
  const query = useQuery({
    queryKey: ['subscriptions', { filter, search, page }],
    queryFn: () => getSubscriptions({ filter, search, page }),
    placeholderData: keepPreviousData,
  })

  const update = (next) => {
    const merged = { filter, q: search, page: String(page), ...next }
    const clean = Object.fromEntries(Object.entries(merged).filter(([k, v]) => v && !(k === 'filter' && v === 'all') && !(k === 'page' && v === '1')))
    setParams(clean)
  }

  return (
    <div className="stack-lg">
      <TopBar title="My Plans" subtitle="Plans you own. You pay the provider, members pay you." />
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
              <StatCard label="Plans you own" value={d.totals.count} helper={`${formatBDT(d.totals.toProviders, { trim: true })} a month to the providers`} />
              <StatCard label="Collected from members" value={formatBDT(d.totals.confirmed, { trim: true })} helper={`of ${formatBDT(d.totals.expected, { trim: true })} expected this month`}>
                <ProgressBar
                  total={d.totals.expected}
                  label={`${formatBDT(d.totals.confirmed)} confirmed and ${formatBDT(d.totals.pending)} pending, of ${formatBDT(d.totals.expected)}`}
                  parts={[
                    { key: 'paid', value: d.totals.confirmed, fill: STATUS.paid.fill },
                    { key: 'pending', value: d.totals.pending, fill: STATUS.pending.fill },
                  ]}
                />
              </StatCard>
              <StatCard
                label="Waiting for your review"
                value={d.totals.reviewCount}
                helper={d.totals.reviewCount ? `transaction IDs on ${d.totals.reviewPlans.join(', ')}` : 'Nothing to check right now.'}
              />
            </div>

            <div className="grid gap-4">
              <div className="row" role="group" aria-label="Filter plans">
                <FilterChip selected={filter === 'all'} count={d.counts.all} onClick={() => update({ filter: 'all', page: '1' })}>
                  All Plans
                </FilterChip>
                <FilterChip selected={filter === 'review'} count={d.counts.review} alert onClick={() => update({ filter: 'review', page: '1' })}>
                  Needs Review
                </FilterChip>
                <FilterChip selected={filter === 'rarely'} count={d.counts.rarely} onClick={() => update({ filter: 'rarely', page: '1' })}>
                  Rarely Used
                </FilterChip>
                {search && (
                  <button type="button" className="text-link t-meta" onClick={() => update({ q: '', page: '1' })}>
                    Clear search “{search}”
                  </button>
                )}
              </div>

              {d.items.length ? (
                <div className="stack">
                  {d.items.map((p) => (
                    <PlanCard key={p.id} plan={p} />
                  ))}
                </div>
              ) : (
                <Box>
                  <EmptyState
                    icon={Inbox}
                    title={search || filter !== 'all' ? 'Nothing matches' : 'No plans yet'}
                    helper={search || filter !== 'all' ? 'Try another filter or search.' : 'Add your first subscription.'}
                  />
                </Box>
              )}
            </div>

            <div className="grid justify-items-center gap-6">
              <LinkButton to="/app/plans/new" variant="primary-orange" size="lg" icon={Plus} italic>
                Add plan
              </LinkButton>
              <Pagination page={d.page} pages={d.pages} onPage={(n) => update({ page: String(n) })} />
            </div>
          </>
        )}
      </Loadable>
    </div>
  )
}
