import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowRightLeft, Ban, BadgeCheck, ChevronDown, Download, Eye, Mail, Pause, Play, RotateCcw, Trash2, UserPlus } from 'lucide-react'
import { canSendInvite, freeSeats, inviteReservesSeat, pendingInvitesReservingSeats } from '@/lib/planSeats'
import * as plansApi from '@/api/plans'
import { METHODS, STATUS } from '@/lib/colors'
import { MOCK_TODAY, fmtFull, fmtShort, fmtWhen, monthKey, plural, renewsInLabel } from '@/lib/dates'
import { formatBDT, formatRate, formatUSD, parseTaka } from '@/lib/money'
import { cycleLabel, perCycleLabel } from '@/mocks/schedule'
import { useAction } from '@/hooks/useAction'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead, StatCard } from '@/components/ui/Box'
import { Button, LinkButton } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { Input, Select, Switch } from '@/components/ui/Field'
import { LockedNote, MethodTag, PlanStatusPill, RoleTag, StatusDot, StatusPill } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { CopyField, EmptyState, FilterChip, Pagination, ProgressBar, SkeletonCard } from '@/components/ui/Misc'
import { Loadable, ownerMeta } from '@/features/common/PlanBits'
import { NotFoundPage } from '@/features/NotFoundPage'
import { FloatingMember } from './FloatingMember'
import { MarkPaidModal, WaiveModal } from './PaymentModals'
import { ConfirmModal, DeletePlanModal, EditRateModal, InviteModal, LeaveModal, PriceChangeModal, RenewModal, TransferModal } from './OwnerModals'

const TONE = { pending: STATUS.pending.fill, paid: STATUS.paid.fill, due: STATUS.due.fill, info: '#14b3f2' }

function PlanActionsMenu({ plan, onPick }) {
  const [open, setOpen] = useState(false)
  const wrap = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (wrap.current && !wrap.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const pick = (type) => {
    setOpen(false)
    onPick(type)
  }

  return (
    <div className="action-menu" ref={wrap}>
      <Button variant="ghost" size="sm" icon={ChevronDown} aria-expanded={open} aria-haspopup="menu" onClick={() => setOpen((v) => !v)}>
        Actions
      </Button>
      {open && (
        <div className="action-menu__panel" role="menu">
          <Link role="menuitem" className="action-menu__item" to={`/app/plans/${plan.id}/review`} onClick={() => setOpen(false)}>
            <Eye aria-hidden="true" />
            Review payments
            {plan.pendingCount > 0 ? <span className="action-menu__badge">{plan.pendingCount}</span> : null}
          </Link>
          {plan.status === 'paused' && (
            <button type="button" role="menuitem" className="action-menu__item" onClick={() => pick('resume')}>
              <Play aria-hidden="true" />
              Resume
            </button>
          )}
          {['active', 'trial'].includes(plan.status) && (
            <button type="button" role="menuitem" className="action-menu__item" onClick={() => pick('pause')}>
              <Pause aria-hidden="true" />
              Pause
            </button>
          )}
          {['active', 'trial', 'paused'].includes(plan.status) && (
            <button type="button" role="menuitem" className="action-menu__item action-menu__item--danger" onClick={() => pick('cancel')}>
              <Ban aria-hidden="true" />
              Cancel plan
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function SeatSplitCard({ plan }) {
  const [split, setSplit] = useState(plan.split)
  const [amounts, setAmounts] = useState(() =>
    Object.fromEntries(plan.members.map((m) => [m.id, m.customShare != null ? String(m.customShare / 100) : ''])),
  )
  const saveSplit = useAction((p) => plansApi.updatePlanSplit(plan.id, p), { toastMessage: 'Seat split saved.' })

  useEffect(() => {
    setSplit(plan.split)
    setAmounts(Object.fromEntries(plan.members.map((m) => [m.id, m.customShare != null ? String(m.customShare / 100) : ''])))
  }, [plan.id, plan.split, plan.members])

  if (plan.mode !== 'owner' || !plan.shared) return null

  const chargeTotal = plan.price.amount
  const lineTotal = plan.members.reduce((a, m) => a + (parseTaka(amounts[m.id]) ?? 0), 0)
  const customValid =
    split !== 'custom' || (plan.members.every((m) => (parseTaka(amounts[m.id]) ?? 0) > 0) && lineTotal === chargeTotal)

  return (
    <Box>
      <BoxHead
        title="Seat split"
        sub={`The plan price is ${formatBDT(chargeTotal, { trim: true })} each cycle. Equal divides it across ${plan.members.length} seat${plan.members.length === 1 ? '' : 's'}. Custom lets you set each person’s share; they must add up to that total.`}
      />
      <div className="row gap-2" role="group" aria-label="Split type">
        <button type="button" className="chip" aria-pressed={split === 'equal'} onClick={() => setSplit('equal')}>
          Equal
        </button>
        <button type="button" className="chip" aria-pressed={split === 'custom'} onClick={() => setSplit('custom')}>
          Custom
        </button>
      </div>
      {split === 'custom' && (
        <div className="mt-4 grid gap-3">
          {plan.members.map((m) => (
            <Input
              key={m.id}
              label={m.isOwnerSeat ? `${m.firstName} (you, owner seat)` : m.firstName}
              inputMode="decimal"
              numeric
              value={amounts[m.id] ?? ''}
              onChange={(e) => setAmounts((prev) => ({ ...prev, [m.id]: e.target.value }))}
              error={saveSplit.fields[m.id]}
            />
          ))}
          <p className={customValid ? 't-meta font-bold' : 'field__error'}>
            Running total {formatBDT(lineTotal, { trim: true })} of {formatBDT(chargeTotal, { trim: true })}
            {customValid ? '' : ` · off by ${formatBDT(Math.abs(chargeTotal - lineTotal), { trim: true })}`}
          </p>
          {saveSplit.fields._total && <p className="field__error">{saveSplit.fields._total}</p>}
        </div>
      )}
      <div className="mt-4 row justify-end">
        <Button
          type="button"
          variant="accept"
          busy={saveSplit.busy}
          disabled={split === 'custom' && !customValid}
          onClick={() =>
            saveSplit.run(
              split === 'equal'
                ? { split: 'equal' }
                : {
                    split: 'custom',
                    shares: Object.fromEntries(plan.members.map((m) => [m.id, amounts[m.id] ?? ''])),
                  },
            )
          }
        >
          Save split
        </Button>
      </div>
    </Box>
  )
}

function MembersCard({ plan, onOpen, onInvite, onCancelInvite, openId, rowRefs, cancelInviteBusy }) {
  const reservedInvites = pendingInvitesReservingSeats(plan.invites)
  const free = freeSeats(plan)
  const reseller = plan.mode === 'reseller'
  const list = reseller ? plan.members.filter((m) => !m.isOwnerSeat) : plan.members
  const inviteLabel = reseller ? 'Invite buyer' : 'Invite member'
  const canInvite = canSendInvite(plan)
  const seatsFullReason =
    free <= 0 && reservedInvites.length > 0
      ? `${reservedInvites.length} pending invite${reservedInvites.length === 1 ? '' : 's'} — cancel one to free a seat`
      : free <= 0
        ? 'All seats are taken'
        : undefined

  return (
    <Box>
      <div className="row-between mb-5 gap-3 flex-wrap">
        <h2 className="t-card">{reseller ? 'Buyers' : 'Members'}</h2>
        <Button
          variant="primary-orange"
          size="sm"
          icon={UserPlus}
          disabled={!canInvite}
          title={!canInvite && seatsFullReason ? seatsFullReason : !canInvite ? 'Invites are not available for this plan status' : undefined}
          onClick={onInvite}
        >
          {inviteLabel}
        </Button>
      </div>

      <ul className="dashed-rows">
        {reservedInvites.map((inv) => (
          <li key={inv.id} className="owner-member-row flex w-full flex-wrap items-center gap-3 py-3">
            <div className="grid min-h-[2.75rem] min-w-[2.75rem] place-items-center rounded-full border-[0.1875rem] border-dashed border-black bg-[var(--color-cream)]">
              <Mail aria-hidden="true" className="size-5" />
            </div>
            <div className="min-w-0 flex-[1_1_12rem]">
              <p className="font-bold break-all">{inv.email}</p>
              <p className="t-meta">
                {inv.status === 'expired' ? 'Invite expired — still holding a seat until you cancel' : 'Invited — not joined yet'}
              </p>
            </div>
            <StatusPill status={inv.status === 'expired' ? 'due' : 'pending'} small>
              {inv.status === 'expired' ? 'Expired' : 'Pending'}
            </StatusPill>
            {String(inv.id).startsWith('email-') ? null : (
              <Button size="sm" variant="ghost" busy={cancelInviteBusy} onClick={() => onCancelInvite(inv.id)}>
                Cancel invite
              </Button>
            )}
          </li>
        ))}
        {list.map((m) => (
          <li key={m.id} className="owner-member-row flex w-full flex-wrap items-center gap-3 py-3">
            <Avatar name={m.name} color={m.avatarColor} size="md" status={m.dueStatus ?? undefined} decorative />
            <div className="min-w-0 flex-[1_1_12rem]">
              <p className="truncate font-bold" title={`${m.firstName}${m.isOwnerSeat ? ' (owner)' : ''}`}>
                {m.firstName}
                {m.isOwnerSeat ? ' (owner)' : ''}
              </p>
              <p className="t-meta break-all" title={m.email}>
                {m.email}
              </p>
              {m.leaveRequested && (
                <button type="button" className="mt-1 text-[0.8rem] font-bold text-[#846ace] underline" onClick={() => onOpen('leave', m)}>
                  Asked to leave
                </button>
              )}
            </div>
            {m.dueStatus && <StatusDot status={m.dueStatus} />}
            {m.dueStatus === 'pending' ? (
              <LinkButton to={`/app/plans/${plan.id}/review`} variant="review" size="sm" icon={Eye}>
                Review
              </LinkButton>
            ) : m.isOwnerSeat && m.dueId && m.dueStatus === 'due' ? (
              <Button variant="accept" size="sm" icon={BadgeCheck} onClick={() => onOpen('markPaid', m)}>
                Mark as paid
              </Button>
            ) : (
              <Button
                ref={(el) => {
                  rowRefs.current[m.id] = el
                }}
                variant="ghost"
                size="sm"
                aria-pressed={openId === m.id}
                onClick={() => onOpen('window', m)}
              >
                Open
              </Button>
            )}
          </li>
        ))}
        {!list.length && !reservedInvites.length && <li className="t-meta py-4">Nobody yet. Invite people by email.</li>}
      </ul>

      {plan.leftMembers.length > 0 && (
        <details className="mt-5">
          <summary className="t-label cursor-pointer">Left members ({plan.leftMembers.length})</summary>
          <ul className="dashed-rows mt-2">
            {plan.leftMembers.map((m) => (
              <li key={m.id} className="row-between py-2.5">
                <span className="row gap-3">
                  <Avatar name={m.name} color={m.avatarColor} size="sm" decorative />
                  <span className="font-bold">{m.name}</span>
                </span>
                <span className="t-meta">left {m.leftOn ? fmtShort(m.leftOn) : ''}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Box>
  )
}

function LedgerCard({ plan }) {
  const [member, setMember] = useState('all')
  const [month, setMonth] = useState('all')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [stmt, setStmt] = useState(monthKey(MOCK_TODAY))
  const [rateCharge, setRateCharge] = useState(null)
  const query = useQuery({
    queryKey: ['ledger', plan.id, { member, month, status, page }],
    queryFn: () => plansApi.getLedger(plan.id, { member, month, status, page }),
    placeholderData: keepPreviousData,
  })
  const download = useAction(() => plansApi.downloadOwnerStatement(plan.id, { month: stmt }), {
    toastMessage: (r) => (r?.number ? `Downloaded statement ${r.number}.` : 'Statement downloaded.'),
    invalidate: ['plans', 'nav', 'dashboard'],
  })

  return (
    <Box>
      <BoxHead title="Ledger" sub="Who paid you, and when. Filters apply to the totals too." />
      <Loadable query={query} skeleton={<SkeletonCard lines={4} />}>
        {(d) => (
          <div className="grid gap-5">
            <div className="flex flex-wrap gap-3">
              <Select label="Member" value={member} onChange={(e) => { setMember(e.target.value); setPage(1) }} options={[{ value: 'all', label: 'Everyone' }, ...d.people.map((p) => ({ value: p.id, label: p.name }))]} fieldClass="min-w-[10rem]" />
              <Select label="Month" value={month} onChange={(e) => { setMonth(e.target.value); setPage(1) }} options={[{ value: 'all', label: 'All months' }, ...d.months.map((m) => ({ value: m.key, label: m.label }))]} fieldClass="min-w-[10rem]" />
            </div>
            <div className="row" role="group" aria-label="Filter by status">
              {['all', 'paid', 'pending', 'due', 'waived'].map((s) => (
                <FilterChip key={s} selected={status === s} onClick={() => { setStatus(s); setPage(1) }}>
                  {s === 'all' ? 'All' : STATUS[s].label}
                </FilterChip>
              ))}
            </div>
            <div className="table-scroll">
              <table className="neo-table neo-table--stack">
                <thead>
                  <tr>
                    <th scope="col">Month</th>
                    <th scope="col">Member</th>
                    <th scope="col">Amount</th>
                    <th scope="col">Status</th>
                    <th scope="col">Proof</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((r) => (
                    <tr key={r.id}>
                      <td data-label="Month">{r.monthLabel}</td>
                      <td data-label="Member">
                        {r.firstName}
                        {r.isOwnerSeat ? ' (you)' : ''}
                        {r.coveredBy && <span className="t-meta block">covered by {r.coveredBy}</span>}
                      </td>
                      <td className="t-num" data-label="Amount">{formatBDT(r.amount)}</td>
                      <td data-label="Status">
                        <StatusPill status={r.status} small />
                      </td>
                      <td className="t-meta" data-label="Proof">
                        {r.tid ? `${METHODS[r.method]?.label ?? ''} · ${r.tid}` : r.recordedByOwner ? 'recorded by owner' : '—'}
                        {r.paidOn && <span className="block">{fmtShort(r.paidOn)}</span>}
                      </td>
                    </tr>
                  ))}
                  {!d.items.length && (
                    <tr>
                      <td colSpan={5} className="t-meta">
                        Nothing matches these filters.
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}>Totals</td>
                    <td className="t-num" colSpan={3}>
                      Paid {formatBDT(d.totals.paid, { trim: true })} · Pending {formatBDT(d.totals.pending, { trim: true })} · Due {formatBDT(d.totals.due, { trim: true })}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <Pagination page={d.page} pages={d.pages} onPage={setPage} />
            {plan.currency === 'USD' && (
              <div className="grid gap-2">
                <p className="t-label">Exchange rate on a charge</p>
                {plan.charges.map((c) => (
                  <div key={c.id} className="row-between">
                    <span className="t-meta">
                      {c.monthLabel}: {formatUSD(c.usdCents)} × {formatRate(c.rate)} = {formatBDT(c.amount)}
                    </span>
                    <button
                      type="button"
                      className="text-link t-meta"
                      disabled={c.hasPayments}
                      title={c.hasPayments ? 'A member already sent a payment, so the rate is locked.' : 'Correct the rate you were charged'}
                      onClick={() => setRateCharge(c)}
                    >
                      Edit rate
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <Select label="Statement month" value={stmt} onChange={(e) => setStmt(e.target.value)} options={(d.months.length ? d.months : [{ key: stmt, label: stmt }]).map((m) => ({ value: m.key, label: m.label ?? m.key }))} fieldClass="min-w-[10rem]" />
              <Button variant="ghost" icon={Download} busy={download.busy} onClick={() => download.run()}>
                Download statement
              </Button>
            </div>
          </div>
        )}
      </Loadable>
      {rateCharge && <EditRateModal charge={rateCharge} onClose={() => setRateCharge(null)} />}
    </Box>
  )
}

function OwnerPlan({ plan }) {
  const [params, setParams] = useSearchParams()
  const [openId, setOpenId] = useState(null)
  const [modal, setModal] = useState(null)
  const rowRefs = useRef({})
  const rarely = useAction((value) => plansApi.setRarelyUsed(plan.id, value), { toastMessage: (d, v) => (v ? 'Flagged as rarely used. It shows on Home.' : 'Removed the rarely used flag.') })
  const cancelInv = useAction((id) => plansApi.cancelInvite(id), { tone: 'waived', toastMessage: 'Invite cancelled.' })
  const cancelTr = useAction(() => plansApi.cancelTransfer(plan.transfer.id), { tone: 'waived', toastMessage: 'Transfer cancelled. Nothing changed.' })
  const leaveId = params.get('leave')
  const leaveMember = leaveId ? plan.members.find((m) => m.id === leaveId) : null
  const closeModal = () => {
    setModal(null)
    if (leaveId) {
      const next = new URLSearchParams(params)
      next.delete('leave')
      setParams(next, { replace: true })
    }
  }

  const free = freeSeats(plan)
  const reservedInvites = pendingInvitesReservingSeats(plan.invites)
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const canInvite = canSendInvite(plan)
  const seatsFullReason =
    free <= 0 && reservedInvites.length > 0
      ? `${reservedInvites.length} pending invite${reservedInvites.length === 1 ? '' : 's'} — cancel one to free a seat`
      : free <= 0
        ? 'All seats are taken'
        : undefined
  const openInvite = () => setModal({ type: 'invite' })

  return (
    <div className="stack-lg">
      <TopBar
        breadcrumb={[{ label: 'My Plans', to: '/app/plans' }, { label: plan.planName }]}
        title={plan.planName}
        subtitle={`${ownerMeta(plan, { seats: false })} · ${plan.seatsCap} seats${plan.seatsTaken >= plan.seatsCap ? ', all taken' : `, ${plan.seatsTaken} taken`}`}
        lead={<ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="large" />}
        actions={
          <>
            <PlanStatusPill status={plan.status} />
            {plan.renewal === 'fixed' && (
              <Button variant="accept" icon={RotateCcw} onClick={() => setModal({ type: 'renew' })}>
                Renew
              </Button>
            )}
            <PlanActionsMenu plan={plan} onPick={(type) => setModal({ type })} />
          </>
        }
      />

      <div className="stat-grid">
        <StatCard label="Plan price" value={formatBDT(plan.price.amount, { trim: true })} helper={perCycleLabel(plan.cycle)} />
        <StatCard label="Each seat" value={formatBDT(plan.perSeat, { trim: true })} helper={perCycleLabel(plan.cycle)} />
        <StatCard label="Renews in" value={renewsInLabel(plan.nextRenewal)} helper={plan.nextRenewal ? fmtShort(plan.nextRenewal) : undefined} />
      </div>

      <Box>
        <div className="row-between mb-4">
          <h2 className="t-card">Confirmed so far</h2>
          <p className="t-num font-bold">
            {formatBDT(plan.confirmedSoFar.paid + plan.confirmedSoFar.waived, { trim: true })} / {formatBDT(plan.confirmedSoFar.total, { trim: true })}
          </p>
        </div>
        <ProgressBar
          total={plan.confirmedSoFar.total}
          label={[
            `${formatBDT(plan.confirmedSoFar.paid + plan.confirmedSoFar.waived)} confirmed`,
            plan.confirmedSoFar.waived > 0 && `${formatBDT(plan.confirmedSoFar.waived)} waived`,
            `${formatBDT(plan.confirmedSoFar.pending)} pending`,
          ]
            .filter(Boolean)
            .join(', ')}
          parts={[
            { key: 'paid', value: plan.confirmedSoFar.paid, fill: STATUS.paid.fill },
            { key: 'waived', value: plan.confirmedSoFar.waived, fill: STATUS.waived.fill },
            { key: 'pending', value: plan.confirmedSoFar.pending, fill: STATUS.pending.fill },
          ]}
        />
      </Box>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,1fr)]">
        <MembersCard
          plan={plan}
          openId={openId}
          rowRefs={rowRefs}
          onInvite={openInvite}
          onCancelInvite={(id) => cancelInv.run(id)}
          cancelInviteBusy={cancelInv.busy}
          onOpen={(type, member) => {
            if (type === 'window') setOpenId(member.id)
            else setModal({ type, member })
          }}
        />
        <>
          <FloatingMember memberId={openId} planId={plan.id} onClose={() => setOpenId(null)} onRemove={(m) => { setOpenId(null); setModal({ type: 'remove', member: m }) }} rowRefs={rowRefs} />
          <FloatingMember sheet memberId={openId} planId={plan.id} onClose={() => setOpenId(null)} onRemove={(m) => { setOpenId(null); setModal({ type: 'remove', member: m }) }} rowRefs={rowRefs} />
        </>
      </div>

      <div className="two-col">
        <Box>
          <BoxHead title="Activity" sub={plan.activity.length ? 'Latest 10' : undefined} />
          {plan.activity.length ? (
            <ul className="dashed-rows">
              {plan.activity.map((a) => (
                <li key={a.id} className="flex items-start gap-3 py-3">
                  <span className="status-dot mt-1" style={{ background: TONE[a.tone] ?? TONE.info }} aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p>
                      {a.text}
                      {a.amount ? ` ${formatBDT(a.amount, { trim: true })}` : ''}
                    </p>
                    <p className="t-meta">{fmtWhen(a.ts)}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No activity yet" />
          )}
        </Box>

        <div className="stack">
          <Box>
            <BoxHead title="Details" action={<Link to={`/app/plans/${plan.id}/edit`} className="text-link">Edit</Link>} />
            <dl className="dashed-rows">
              {[
                ['Mode', plan.mode === 'owner' ? 'Owner (locked)' : 'Reseller (locked)'],
                ['Category', plan.categoryName],
                ['Billing', `${cycleLabel(plan.cycle)}, ${formatBDT(plan.price.amount, { trim: true })}`],
                ['Seats', plan.mode === 'reseller' ? `${plan.seatsCap}, you take none` : `${plan.seatsCap}, owner takes 1`],
                ['Recommended payment', <MethodTag key="m" method={plan.method} />],
                ['Note', plan.note || '—'],
              ].map(([k, v]) => (
                <div key={k} className="row-between py-2.5">
                  <dt className="t-label">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="row-between mt-5">
              <span className="t-label">Rarely used</span>
              <Switch checked={plan.rarelyUsed} label="Rarely used" onChange={(v) => rarely.run(v)} />
            </div>
            {plan.rarelyUsed && <RoleTag role="rarely" />}
            <div className="mt-6 grid gap-3">
              <div className="row-between">
                <p className="t-label">Price history</p>
                <Button size="sm" variant="ghost" onClick={() => setModal({ type: 'price' })}>
                  Add price change
                </Button>
              </div>
              <ul className="dashed-rows">
                {plan.prices.map((p) => (
                  <li key={p.effectiveFrom} className="row-between py-2.5">
                    <span>from {fmtFull(p.effectiveFrom)}</span>
                    <span className="t-num font-bold">
                      {plan.currency === 'USD' ? `${formatUSD(p.usdCents)} at ${formatRate(p.rate)}` : formatBDT(p.amount, { trim: true })}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Box>

          <SeatSplitCard plan={plan} />

          <Box>
            <BoxHead title="IOUs in this plan" />
            {plan.mode === 'reseller' ? (
              <p className="t-meta">Reseller plans have no IOUs. Each buyer pays you their own share.</p>
            ) : plan.ious.length ? (
              <ul className="dashed-rows">
                {plan.ious.map((i) => (
                  <li key={`${i.debtorId}-${i.creditorId}`} className="row-between py-2.5">
                    <span className="font-bold">
                      {i.debtor} owes {i.creditor}
                    </span>
                    <span className="t-num font-bold">{formatBDT(i.amount, { trim: true })}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="t-meta">All settled.</p>
            )}
          </Box>
        </div>
      </div>

      <LedgerCard plan={plan} />

      <Box>
        <BoxHead
          title="Invite details"
          action={
            <Button size="sm" variant="ghost" icon={UserPlus} disabled={!canInvite} onClick={openInvite}>
              Invite by email
            </Button>
          }
        />
        {plan.joinLink && (
          <div className="grid gap-2 mb-4">
            {plan.joinLinkAvailable && canInvite ? (
              <CopyField label="Plan invite link" value={plan.joinLink} />
            ) : (
              <div className="grid gap-1.5">
                <p className="t-label">Plan invite link</p>
                <code className="t-meta break-all opacity-60">{plan.joinLink}</code>
                <p className="t-meta">All seats are taken. Copy is disabled until a seat opens.</p>
              </div>
            )}
            {plan.joinLinkAvailable && canInvite && (
              <p className="t-meta">Anyone with this link can sign up or log in and join while seats are free.</p>
            )}
          </div>
        )}
        <p>
          {free <= 0
            ? `All ${plan.seatsCap} seats are taken. If someone leaves, you can share the plan link or invite by email.`
            : `${plural(free, 'free seat')}. Share the plan link above, or invite one person by email (each email invite includes a backup link).`}
        </p>
        {plan.invites.length > 0 && (
          <ul className="dashed-rows mt-4">
            {plan.invites.map((i) => (
              <li key={i.id} className="grid gap-2 py-3">
                <div className="row-between">
                  <span className="font-bold break-all">{i.email}</span>
                  <StatusPill status={i.status === 'pending' ? 'pending' : i.status === 'accepted' ? 'paid' : 'due'} small>
                    {i.status}
                  </StatusPill>
                </div>
                <p className="t-meta">{i.expiresOn ? `expires ${fmtShort(i.expiresOn)}` : 'No expiry date'}</p>
                {inviteReservesSeat(i) && (
                  <div className="grid gap-3">
                    <CopyField label="Backup link" value={`${origin}/invite/${i.token}`} />
                    <Button size="sm" variant="ghost" onClick={() => cancelInv.run(i.id)} busy={cancelInv.busy}>
                      Cancel invite
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Box>

      <Box>
        <BoxHead title="Owner actions" />
        <div className="stack-sm">
          {plan.mode === 'owner' ? (
            <>
              {plan.transfer ? (
                <div className="neo-box neo-box--flat neo-box--highlight grid gap-3 !p-4">
                  <p className="font-bold">Waiting for {plan.members.find((m) => m.userId === plan.transfer.toUserId)?.firstName ?? 'a member'} to accept ownership.</p>
                  <Button size="sm" variant="ghost" busy={cancelTr.busy} onClick={() => cancelTr.run()}>
                    Cancel transfer
                  </Button>
                </div>
              ) : (
                <div className="grid gap-2">
                  <Button variant="ghost" icon={ArrowRightLeft} onClick={() => setModal({ type: 'transfer' })}>
                    Transfer ownership
                  </Button>
                  <p className="t-meta">Needs your password. The new owner must accept, and you become a member.</p>
                </div>
              )}
            </>
          ) : (
            <p className="t-meta">
              <LockedNote>Reseller plans cannot change owner.</LockedNote>
            </p>
          )}
          <div className="grid gap-2">
            <Button variant="reject" icon={Trash2} onClick={() => setModal({ type: 'delete' })}>
              Delete plan
            </Button>
            <p className="t-meta">Needs your password. Members are told. Plans with confirmed payments are archived, not erased.</p>
          </div>
        </div>
      </Box>

      {modal?.type === 'pause' && (
        <ConfirmModal title="Pause this plan?" body="No new charges until you resume. Open dues stay as they are." confirmLabel="Pause" icon={Pause} action={() => plansApi.pausePlan(plan.id)} onClose={() => setModal(null)} toastMessage="Paused. No new charges until you resume." tone="pending" />
      )}
      {modal?.type === 'resume' && (
        <ConfirmModal title="Resume this plan?" body="Dates you skipped while paused stay skipped. The next renewal follows the usual day." confirmLabel="Resume" icon={Play} action={() => plansApi.resumePlan(plan.id)} onClose={() => setModal(null)} toastMessage="Resumed." />
      )}
      {modal?.type === 'cancel' && (
        <ConfirmModal title="Cancel this plan?" body="It stays active until the end of the paid period. Members keep access until then." confirmLabel="Cancel plan" variant="reject" icon={Ban} action={() => plansApi.cancelPlan(plan.id)} onClose={() => setModal(null)} toastMessage="Cancelled. It ends at the close of the paid period." tone="due" />
      )}
      {modal?.type === 'renew' && <RenewModal plan={plan} onClose={() => setModal(null)} />}
      {modal?.type === 'invite' && <InviteModal plan={plan} onClose={() => setModal(null)} />}
      {(modal?.type === 'leave' || leaveMember) && <LeaveModal plan={plan} member={modal?.type === 'leave' ? modal.member : leaveMember} onClose={closeModal} />}
      {modal?.type === 'remove' && <LeaveModal plan={plan} member={modal.member} mode="remove" onClose={() => setModal(null)} />}
      {modal?.type === 'transfer' && <TransferModal plan={plan} onClose={() => setModal(null)} />}
      {modal?.type === 'delete' && <DeletePlanModal plan={plan} onClose={() => setModal(null)} />}
      {modal?.type === 'price' && <PriceChangeModal plan={plan} onClose={() => setModal(null)} />}
      {modal?.type === 'markPaid' && (
        <MarkPaidModal
          dueId={modal.member.dueId}
          planId={plan.id}
          name={modal.member.firstName}
          method={plan.method}
          ownSeat={modal.member.isOwnerSeat}
          coverable={plan.coverable ?? []}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.type === 'waive' && <WaiveModal dueId={modal.member.dueId} name={modal.member.firstName} onClose={() => setModal(null)} />}
    </div>
  )
}

export function OwnerPlanPage() {
  const { id } = useParams()
  const query = useQuery({ queryKey: ['plan', id], queryFn: () => plansApi.getSubscription(id) })
  return (
    <Loadable query={query} skeleton={<SkeletonCard lines={6} />}>
      {(plan) => (plan.notFound ? <NotFoundPage inApp /> : <OwnerPlan plan={plan} />)}
    </Loadable>
  )
}
