import { CalendarX } from 'lucide-react'
import { CHART, STATUS } from '@/lib/colors'
import { fmtShort, plural } from '@/lib/dates'
import { formatBDT, formatRate, formatUSD } from '@/lib/money'
import { cycleLabel, perCycleLabel } from '@/mocks/schedule'
import { DateBadge, EmptyState, ErrorBox, SkeletonCard } from '@/components/ui/Misc'
import { cx } from '@/components/ui/Box'

/** Renders a query's skeleton, error box, or its data. */
export function Loadable({ query, skeleton, children }) {
  if (query.isPending) return skeleton ?? <SkeletonCard />
  if (query.isError) return <ErrorBox error={query.error} onRetry={() => query.refetch()} />
  return children(query.data)
}

export function usdLine(price) {
  return `${formatUSD(price.usdCents)} at ${formatRate(price.rate)}`
}

export function renewText(plan) {
  if (plan.status === 'paused') return plan.pausedOn ? `paused since ${fmtShort(plan.pausedOn)}` : 'paused'
  if (plan.status === 'cancelled') return 'cancelled'
  if (plan.status === 'expired') return 'expired'
  if (plan.status === 'trial' && plan.trialEnd) return `trial ends ${fmtShort(plan.trialEnd)}`
  return plan.nextRenewal ? `renews ${fmtShort(plan.nextRenewal)}` : 'no next renewal'
}

/** "Monthly · $20 at ৳122 · renews 12 Nov · 4 seats" */
export function ownerMeta(plan, { seats = true } = {}) {
  const parts = [cycleLabel(plan.cycle)]
  if (plan.currency === 'USD') parts.push(usdLine(plan.price))
  parts.push(renewText(plan))
  if (seats && plan.shared) parts.push(plural(plan.seatsTaken, 'seat'))
  return parts.join(' · ')
}

export function Price({ amount, cycle, className, small }) {
  return (
    <p className={cx('basis-full text-left sm:basis-auto sm:text-right', className)}>
      <span className={cx('t-num block font-[family-name:var(--font-display)] font-bold', small ? 'text-[1.25rem]' : 'text-[1.6rem]')}>{formatBDT(amount, { trim: true })}</span>
      <span className="t-meta block">{perCycleLabel(cycle)}</span>
    </p>
  )
}

const EVENT_WORD = { renews: 'Renews', trial_end: 'Trial ends', expires: 'Ends', due: 'Due' }

export function eventWord(event) {
  if (event.kind === 'due' && event.status && event.status !== 'due') return `Due · ${STATUS[event.status].label}`
  return EVENT_WORD[event.kind]
}

export function eventDotColor(event) {
  return event.role === 'owner' ? CHART.owned : STATUS[event.status ?? 'due'].fill
}

export function EventList({ events, empty = 'Nothing in the next 7 days.' }) {
  if (!events.length) return <EmptyState icon={CalendarX} title="All quiet" helper={empty} />
  return (
    <ul className="dashed-rows">
      {events.map((e) => (
        <li key={e.id} className="flex items-center gap-3 py-3">
          <DateBadge date={e.date} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-bold">{e.planName}</p>
            <p className="t-meta row gap-2">
              <span className="status-dot !size-3" style={{ background: eventDotColor(e) }} aria-hidden="true" />
              {eventWord(e)}
              <span className="sr-only">on {fmtShort(e.date)}</span>
            </p>
          </div>
          {e.amount > 0 && <span className="t-num shrink-0 font-bold">{formatBDT(e.amount, { trim: true, compact: true })}</span>}
        </li>
      ))}
    </ul>
  )
}
