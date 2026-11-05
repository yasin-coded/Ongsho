import { Link, useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Check, Eye, Inbox, LogOut, X } from 'lucide-react'
import { notificationLook } from '@/lib/notificationLook'
import { getDashboard } from '@/api/dashboard'
import { acceptInvite, acceptTransfer, declineInvite, declineTransfer } from '@/api/shared'
import { useAction } from '@/hooks/useAction'
import { CHART, categoryColor } from '@/lib/colors'
import { fmtShort, plural } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead, LinkBox, StatCard } from '@/components/ui/Box'
import { Button, LinkButton } from '@/components/ui/Button'
import { Avatar, AvatarStack } from '@/components/ui/Avatar'
import { OwnerPlanPill, RoleTag, StatusPill } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { DashedDivider, EmptyState, SkeletonCard } from '@/components/ui/Misc'
import { Donut, ForecastBars, Legend } from '@/components/ui/Charts'
import { EventList, Loadable, ownerMeta, Price, renewText } from '@/features/common/PlanBits'

const HOME_PLAN_LIMIT = 5

function OwnerRow({ plan }) {
  return (
    <li>
      <LinkBox to={`/app/plans/${plan.id}`} className="neo-box--flat flex flex-wrap items-center gap-4 !p-4">
        <ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="compact" />
        <div className="grid min-w-0 flex-[1_1_12rem] gap-1.5">
          <p className="t-sub truncate">{plan.planName}</p>
          <p className="t-meta">{ownerMeta(plan)}</p>
          <div className="row gap-2">
            {plan.shared && plan.members.length > 1 && <AvatarStack people={plan.members} />}
            <OwnerPlanPill pill={plan.statusPill} small />
            {plan.rarelyUsed && <RoleTag role="rarely" />}
          </div>
        </div>
        <Price amount={plan.price.amount} cycle={plan.cycle} />
      </LinkBox>
    </li>
  )
}

function MemberRow({ plan }) {
  return (
    <li>
      <LinkBox to={`/app/shared/${plan.id}`} className="neo-box--flat flex flex-wrap items-center gap-4 !p-4">
        <ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="compact" />
        <div className="grid min-w-0 flex-[1_1_12rem] gap-1.5">
          <p className="t-sub truncate">{plan.planName}</p>
          <p className="t-meta">
            Owner: {plan.owner.firstName} · {renewText(plan)}
          </p>
          <div className="row gap-2">
            <Avatar name={plan.me.name} color={plan.me.avatarColor} size="sm" status={plan.myStatus} />
            <StatusPill status={plan.myStatus} small />
          </div>
        </div>
        <Price amount={plan.myShare} cycle={plan.cycle} />
      </LinkBox>
    </li>
  )
}

function AttentionItem({ item }) {
  const navigate = useNavigate()
  const acceptI = useAction(() => acceptInvite(item.inviteId))
  const declineI = useAction(() => declineInvite(item.inviteId), { tone: 'waived' })
  const acceptT = useAction(() => acceptTransfer(item.transferId))
  const declineT = useAction(() => declineTransfer(item.transferId), { tone: 'waived' })

  const { icon: KindIcon, tile } = notificationLook(item)

  if (item.kind === 'review') {
    return (
      <div className="grid gap-3">
        <div className="row gap-3">
          <span className="icon-tile !size-10 shrink-0" style={{ background: tile }} aria-hidden="true">
            <KindIcon />
          </span>
          <div className="min-w-0">
            <p className="t-sub">{plural(item.count, 'payment')} to review</p>
            <p className="t-meta">{item.planName}, transaction IDs waiting</p>
          </div>
        </div>
        <LinkButton to={`/app/plans/${item.planId}/review`} variant="review" size="sm" icon={Eye} className="neo-btn--block w-full">
          Review
        </LinkButton>
      </div>
    )
  }
  if (item.kind === 'leave') {
    return (
      <div className="grid gap-3">
        <div className="row gap-3">
          <span className="icon-tile !size-10 shrink-0" style={{ background: tile }} aria-hidden="true">
            <KindIcon />
          </span>
          <div className="min-w-0">
            <p className="t-sub">{item.name} wants to leave</p>
            <p className="t-meta">{item.planName}, needs your OK</p>
          </div>
        </div>
        <Button variant="request" size="sm" icon={LogOut} className="neo-btn--block w-full" onClick={() => navigate(`/app/plans/${item.planId}?leave=${item.memberId}`)}>
          Open request
        </Button>
      </div>
    )
  }
  const invite = item.kind === 'invite'
  const accept = invite ? acceptI : acceptT
  const decline = invite ? declineI : declineT
  return (
    <div className="grid gap-3">
      <div className="row gap-3">
        <span className="icon-tile !size-10 shrink-0" style={{ background: tile }} aria-hidden="true">
          <KindIcon />
        </span>
        <div className="min-w-0">
          <p className="t-sub">{invite ? `Invite from ${item.from}` : `${item.from} wants you to own a plan`}</p>
          <p className="t-meta">{invite ? `${item.planName}, shared plan` : `${item.planName}, ownership transfer`}</p>
        </div>
      </div>
      <div className="attention-actions">
        <Button variant="accept" size="sm" icon={Check} busy={accept.busy} onClick={() => accept.run()}>
          Accept
        </Button>
        <Button variant="reject" size="sm" icon={X} busy={decline.busy} onClick={() => decline.run()}>
          Decline
        </Button>
      </div>
    </div>
  )
}

function NeedsAttention({ items }) {
  return (
    <div className="needs-attention-wrap">
      {items.length > 0 && (
        <span className="needs-attention__badge bubble bubble--notify" aria-hidden="true">
          {items.length}
        </span>
      )}
      <Box>
      <BoxHead title="Needs attention" sub={items.length ? `${plural(items.length, 'thing')} waiting for you` : undefined} />
      {items.length ? (
        <div className="grid gap-4">
          {items.map((item, i) => (
            <div key={item.id} className="grid gap-4">
              {i > 0 && <DashedDivider />}
              <AttentionItem item={item} />
            </div>
          ))}
        </div>
      ) : (
        <p className="t-meta">Nothing needs you right now.</p>
      )}
      <Link to="/app/notifications" className="text-link mt-5 inline-block">
        See all notifications
      </Link>
      </Box>
    </div>
  )
}

function HomeSkeleton() {
  return (
    <div className="stack-lg">
      <div className="stat-grid">
        <SkeletonCard tall />
        <SkeletonCard tall />
        <SkeletonCard tall />
      </div>
      <div className="two-col">
        <SkeletonCard lines={5} />
        <SkeletonCard lines={5} />
      </div>
    </div>
  )
}

export function HomePage() {
  const query = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard })

  return (
    <div className="stack-lg">
      <TopBar title={query.data ? `Hi, ${query.data.firstName}` : 'Hi'} subtitle="Here is where your subscriptions stand as of today." />
      <Loadable query={query} skeleton={<HomeSkeleton />}>
        {(d) => (
          <>
            <div className="stat-grid">
              <StatCard
                className="stat-card--spend"
                label="You spent this month"
                value={formatBDT(d.spend.total, { trim: true })}
                visual={
                  <Donut
                    size={5.25}
                    label="Spent this month"
                    data={[
                      { name: 'Plans you own', value: d.spend.owned, fill: CHART.owned },
                      { name: 'Plans you joined', value: d.spend.joined, fill: CHART.joined },
                    ]}
                  />
                }
              >
                <Legend
                  compact
                  items={[
                    { name: 'your seats in plans you own', value: d.spend.owned, fill: CHART.owned },
                    { name: 'your shares in plans you joined', value: d.spend.joined, fill: CHART.joined },
                  ]}
                />
              </StatCard>
              <StatCard
                className="stat-card--due"
                label="Due in seven days"
                value={d.dueSoon.count}
                helper={`${d.dueSoon.count === 1 ? 'payment' : 'payments'}, ${formatBDT(d.dueSoon.total, { trim: true, compact: true })} together`}
              >
                {d.dueSoon.first && <span className="chip w-fit cursor-default">First on {fmtShort(d.dueSoon.first)}</span>}
              </StatCard>
              <StatCard
                label="Rarely used"
                value={formatBDT(d.rarely.yearly, { trim: true })}
                helper={d.rarely.plans.length ? `a year on ${plural(d.rarely.plans.length, 'plan')} you flagged` : 'Flag a plan as rarely used to see what it costs you a year.'}
              >
                {d.rarely.plans.length > 0 && (
                  <div className="row gap-2">
                    {d.rarely.plans.map((p) => (
                      <Link key={p.id} to="/app/plans?filter=rarely" className="neo-pill neo-pill--sm" style={{ background: '#000c7c', color: '#fff' }}>
                        {p.planName}
                      </Link>
                    ))}
                  </div>
                )}
              </StatCard>
            </div>

            <div className="two-col dash-home__cols">
              <div className="stack">
                <Box>
                  <BoxHead
                    title="My Plans"
                    tag={<RoleTag role="asOwner" />}
                    sub="Plans you own and pay the provider for"
                    action={
                      d.owned.length > HOME_PLAN_LIMIT ? (
                        <Link to="/app/plans" className="text-link t-meta">
                          See all · {plural(d.owned.length, 'plan')}
                        </Link>
                      ) : undefined
                    }
                  />
                  {d.owned.length ? (
                    <ul className="stack-sm">
                      {d.owned.slice(0, HOME_PLAN_LIMIT).map((p) => (
                        <OwnerRow key={p.id} plan={p} />
                      ))}
                    </ul>
                  ) : (
                    <EmptyState icon={Inbox} title="No plans yet" helper="Add your first subscription.">
                      <LinkButton to="/app/plans/new" variant="primary-orange" italic>
                        Add plan
                      </LinkButton>
                    </EmptyState>
                  )}
                </Box>
                <Box>
                  <BoxHead
                    title="Shared with me"
                    tag={<RoleTag role="asMember" />}
                    sub="Plans you joined. You pay your share to the owner."
                    action={
                      d.joined.length > HOME_PLAN_LIMIT ? (
                        <Link to="/app/shared" className="text-link t-meta">
                          See all · {plural(d.joined.length, 'plan')}
                        </Link>
                      ) : undefined
                    }
                  />
                  {d.joined.length ? (
                    <ul className="stack-sm">
                      {d.joined.slice(0, HOME_PLAN_LIMIT).map((p) => (
                        <MemberRow key={p.id} plan={p} />
                      ))}
                    </ul>
                  ) : (
                    <EmptyState icon={Inbox} title="Nothing shared yet" helper="When someone invites you to a plan, it shows up here." />
                  )}
                </Box>
              </div>

              <div className="stack dash-home__aside min-w-0">
                <NeedsAttention items={d.attention} />
                <Box>
                  <BoxHead title="Next 7 days" />
                  <EventList events={d.next7} />
                </Box>
                <Box>
                  <BoxHead title="Spend by category" sub="This month, your part only" />
                  {d.byCategory.length ? (
                    <div className="grid min-w-0 justify-items-center gap-4">
                      <Donut size={6.5} label="Spend by category" data={d.byCategory.map((c) => ({ name: c.name, value: c.amount, fill: categoryColor(c.name) }))} />
                      <div className="w-full min-w-0">
                        <Legend compact items={d.byCategory.map((c) => ({ name: c.name, value: c.amount, fill: categoryColor(c.name) }))} />
                      </div>
                    </div>
                  ) : (
                    <p className="t-meta">No spending this month yet.</p>
                  )}
                </Box>
              </div>
            </div>

            <Box>
              <BoxHead title="Next 6 months" sub="What you pay each month, your part only. Yearly renewals stand out." />
              {d.forecast.some((m) => m.total > 0) ? (
                <div className="grid gap-4">
                  <ForecastBars data={d.forecast} colors={{ this: CHART.thisMonth, regular: CHART.regular, yearly: CHART.yearly }} />
                  <div className="row gap-6">
                    <Legend items={[{ name: 'This month', fill: CHART.thisMonth }]} />
                    <Legend items={[{ name: 'Regular month', fill: CHART.regular }]} />
                    <Legend items={[{ name: 'Has a yearly renewal', fill: CHART.yearly }]} />
                  </div>
                </div>
              ) : (
                <EmptyState title="No upcoming charges yet" />
              )}
            </Box>
          </>
        )}
      </Loadable>
    </div>
  )
}
