import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Check, CheckCheck, Inbox, LogOut, X } from 'lucide-react'
import { notificationLook } from '@/lib/notificationLook'
import { getNotifications, markAllRead, markRead } from '@/api/dashboard'
import { confirmPayment } from '@/api/payments'
import { acceptInvite, acceptTransfer, declineInvite, declineTransfer } from '@/api/shared'
import { useAction } from '@/hooks/useAction'
import { MOCK_TODAY, diffDays, dhakaDate, fmtWhen } from '@/lib/dates'
import { TopBar } from '@/components/layout/TopBar'
import { Box } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { DashedDivider, EmptyState, FilterChip, Pagination, SkeletonCard } from '@/components/ui/Misc'
import { Loadable } from '@/features/common/PlanBits'
import { RejectPaymentModal } from '@/features/plans/PaymentModals'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'action', label: 'Needs action' },
  { key: 'payments', label: 'Payments' },
  { key: 'plans', label: 'Plans & members' },
  { key: 'reminders', label: 'Reminders' },
]

const RESOLVED = { approved: 'Approved', rejected: 'Rejected', joined: 'Joined', declined: 'Declined', accepted: 'Accepted', waived: 'Waived' }

function groupOf(n) {
  const gap = diffDays(MOCK_TODAY, dhakaDate(n.createdAt))
  if (gap <= 0) return 'Today'
  if (gap < 7) return 'Earlier this week'
  return 'Earlier'
}

function Actions({ n, onReject }) {
  const navigate = useNavigate()
  const a = n.action
  const approve = useAction(() => confirmPayment(a.paymentId))
  const acceptI = useAction(() => acceptInvite(a.inviteId))
  const declineI = useAction(() => declineInvite(a.inviteId), { tone: 'waived' })
  const acceptT = useAction(() => acceptTransfer(a.transferId))
  const declineT = useAction(() => declineTransfer(a.transferId), { tone: 'waived' })

  if (n.resolved) return <span className="neo-pill neo-pill--sm neo-pill--plain">{RESOLVED[n.resolved] ?? n.resolved}</span>
  if (!a) return null
  if (a.type === 'payment') {
    return (
      <div className="row gap-2">
        <Button variant="accept" size="sm" icon={Check} busy={approve.busy} onClick={() => approve.run()}>
          Approve
        </Button>
        <Button variant="reject" size="sm" icon={X} onClick={() => onReject(a.paymentId)}>
          Reject
        </Button>
      </div>
    )
  }
  if (a.type === 'leave') {
    return (
      <Button variant="request" size="sm" icon={LogOut} onClick={() => navigate(`/app/plans/${a.planId}?leave=${a.memberId}`)}>
        Open request
      </Button>
    )
  }
  const invite = a.type === 'invite'
  const yes = invite ? acceptI : acceptT
  const no = invite ? declineI : declineT
  return (
    <div className="row gap-2">
      <Button variant="accept" size="sm" icon={Check} busy={yes.busy} onClick={() => yes.run()}>
        Accept
      </Button>
      <Button variant="ghost" size="sm" icon={X} busy={no.busy} onClick={() => no.run()}>
        Decline
      </Button>
    </div>
  )
}

function Row({ n, onReject }) {
  const { icon: Icon, tile } = notificationLook(n)
  const read = useAction(() => markRead(n.id), { toastMessage: null, optimisticNav: 'decrement-unread', invalidate: ['notifications', 'nav'] })
  const unread = !n.readAt
  return (
    <li className="flex flex-wrap items-start gap-4 py-4">
      <span className="relative flex-none">
        <span className="icon-tile" style={{ background: tile }} aria-hidden="true">
          <Icon />
        </span>
        {unread && <span className="absolute -top-1.5 -left-1.5 size-4 rounded-full border-[0.1875rem] border-black" style={{ background: tile }} aria-hidden="true" />}
      </span>
      <div className="grid min-w-0 flex-[1_1_16rem] gap-1">
        <p className="font-[family-name:var(--font-display)] text-[1.05rem] leading-tight font-bold">
          {unread && <span className="sr-only">Unread: </span>}
          {n.link ? (
            <Link to={n.link} className="hover:underline" onClick={() => unread && read.run()}>
              {n.title}
            </Link>
          ) : (
            n.title
          )}
        </p>
        <p className="t-meta font-bold">{n.detail}</p>
      </div>
      <div className="grid flex-none justify-items-end gap-2">
        <time className="t-meta" dateTime={n.createdAt}>
          {fmtWhen(n.createdAt)}
        </time>
        <Actions n={n} onReject={onReject} />
        {unread && !n.needsAction && !n.link && (
          <button type="button" className="text-link t-meta" onClick={() => read.run()}>
            Mark as read
          </button>
        )}
      </div>
    </li>
  )
}

export function NotificationsPage() {
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [rejecting, setRejecting] = useState(null)
  const query = useQuery({ queryKey: ['notifications', { filter, page }], queryFn: () => getNotifications({ filter, page }), placeholderData: keepPreviousData })
  const allRead = useAction(markAllRead, { toastMessage: 'All caught up. Everything is marked as read.' })
  const action = query.data?.counts.action ?? 0

  const groups = []
  for (const n of query.data?.items ?? []) {
    const g = groupOf(n)
    const last = groups.at(-1)
    if (last?.title === g) last.items.push(n)
    else groups.push({ title: g, items: [n] })
  }

  return (
    <div className="stack-lg">
      <TopBar
        title="Notifications"
        subtitle={`${action} need${action === 1 ? 's' : ''} you. Everything here is also sent to your email.`}
        tools={false}
        actions={
          <Button variant="brand" icon={CheckCheck} busy={allRead.busy} disabled={!query.data?.unread} onClick={() => allRead.run()}>
            Mark all as read
          </Button>
        }
      />
      <div className="row" role="group" aria-label="Filter notifications">
        {FILTERS.map((f) => (
          <FilterChip
            key={f.key}
            selected={filter === f.key}
            count={query.data?.counts[f.key]}
            alert={f.key === 'action'}
            onClick={() => {
              setFilter(f.key)
              setPage(1)
            }}
          >
            {f.label}
          </FilterChip>
        ))}
      </div>
      <Loadable query={query} skeleton={<SkeletonCard lines={6} />}>
        {(d) => (
          <>
            <Box roomy className="!rounded-[2rem]">
              {d.items.length ? (
                <div className="grid gap-6">
                  {groups.map((g) => (
                    <section key={g.title} aria-label={g.title}>
                      <h2 className="t-label">{g.title}</h2>
                      <DashedDivider className="mt-2" />
                      <ul className="dashed-rows">
                        {g.items.map((n) => (
                          <Row key={n.id} n={n} onReject={setRejecting} />
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              ) : (
                <EmptyState icon={Inbox} title="Inbox empty" helper={filter === 'all' ? 'New invites, payments and reminders show up here.' : 'Nothing under this filter.'} />
              )}
            </Box>
            <Pagination page={d.page} pages={d.pages} onPage={setPage} />
          </>
        )}
      </Loadable>
      {rejecting && <RejectPaymentModal paymentId={rejecting} onClose={() => setRejecting(null)} />}
    </div>
  )
}
