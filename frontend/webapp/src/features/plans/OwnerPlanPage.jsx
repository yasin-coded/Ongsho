import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowRightLeft, Ban, Download, Eye, Pause, Play, RotateCcw, Trash2 } from 'lucide-react'
import * as plansApi from '@/api/plans'
import { METHODS, STATUS } from '@/lib/colors'
import { MOCK_TODAY, diffDays, fmtFull, fmtShort, fmtWhen, monthKey, plural } from '@/lib/dates'
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
import { MarkPaidModal, SetDueModal, WaiveModal } from './PaymentModals'
import { ConfirmModal, DeletePlanModal, EditRateModal, InviteModal, LeaveModal, PriceChangeModal, RenewModal, TransferModal } from './OwnerModals'

const TONE = { pending: STATUS.pending.fill, paid: STATUS.paid.fill, due: STATUS.due.fill, info: '#14b3f2' }

function renewsIn(date) {
  if (!date) return '—'
  const n = diffDays(date, MOCK_TODAY)
  return n <= 0 ? 'today' : plural(n, 'day')
}

function lastPay(m) {
  if (m.isOwnerSeat) return 'No proof needed'
  if (!m.lastPayment) return 'No payment yet'
  return `${fmtWhen(m.lastPayment.at)} · ${METHODS[m.lastPayment.method]?.label ?? m.lastPayment.method}`
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

function MembersCard({ plan, onOpen, onInvite, openId, rowRefs }) {
  const [tab, setTab] = useState('full')
  const pendingInvites = plan.invites.filter((i) => i.status === 'pending')
  const free = plan.seatsCap - plan.seatsTaken - pendingInvites.length
  const reseller = plan.mode === 'reseller'
  const list = reseller ? plan.members.filter((m) => !m.isOwnerSeat) : plan.members

  return (
    <Box>
      <div className="row-between mb-5">
        <h2 className="t-card">{reseller ? 'Buyers' : 'Members'}</h2>
        <div className="row gap-2" role="group" aria-label="Members or invite">
          <button type="button" className="chip" aria-pressed={tab === 'full'} onClick={() => setTab('full')}>
            Full
          </button>
          <button
            type="button"
            className="chip"
            aria-pressed={tab === 'invite'}
            disabled={free <= 0}
            onClick={() => {
              setTab('invite')
              onInvite()
            }}
            title={free <= 0 ? 'All seats are taken' : undefined}
          >
            Invite
          </button>
        </div>
      </div>

      <ul className="dashed-rows">
        {list.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-3 py-3">
            <Avatar name={m.name} color={m.avatarColor} size="md" status={m.dueStatus ?? undefined} decorative />
            <div className="min-w-0 flex-[1_1_12rem]">
              <p className="font-bold">
                {m.firstName}
                {m.isOwnerSeat ? ' (owner)' : ''}
              </p>
              <p className="t-meta break-all">{m.email}</p>
              <p className="t-meta">{lastPay(m)}</p>
              {m.leaveRequested && (
                <button type="button" className="mt-1 text-[0.8rem] font-bold text-[#846ace] underline" onClick={() => onOpen('leave', m)}>
                  Asked to leave
                </button>
              )}
            </div>
            {m.dueStatus && <StatusDot status={m.dueStatus} />}
            {m.isOwnerSeat && m.dueId && m.dueStatus !== 'due' ? (
              <Button variant="solo-navy" size="sm" onClick={() => onOpen('setDue', m)}>
                Set to Due
              </Button>
            ) : m.dueStatus === 'pending' ? (
              <LinkButton to={`/app/plans/${plan.id}/review`} variant="review" size="sm" icon={Eye}>
                Review
              </LinkButton>
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
        {!list.length && <li className="t-meta py-4">Nobody yet. Invite people by email.</li>}
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
    toastMessage: (r) => `Statement ${r.number} is ready. In the real app the PDF downloads now.`,
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
              <table className="neo-table">
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
                      <td>{r.monthLabel}</td>
                      <td>
                        {r.firstName}
                        {r.isOwnerSeat ? ' (you)' : ''}
                        {r.coveredBy && <span className="t-meta block">covered by {r.coveredBy}</span>}
                      </td>
                      <td className="t-num">{formatBDT(r.amount)}</td>
                      <td>
                        <StatusPill status={r.status} small />
                      </td>
                      <td className="t-meta">
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

  const pendingInvites = plan.invites.filter((i) => i.status === 'pending')
  const free = plan.seatsCap - plan.seatsTaken - pendingInvites.length
  const origin = typeof window !== 'undefined' ? window.location.origin : ''

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
            {plan.status === 'paused' && (
              <Button variant="accept" icon={Play} onClick={() => setModal({ type: 'resume' })}>
                Resume
              </Button>
            )}
            {['active', 'trial'].includes(plan.status) && (
              <Button variant="ghost" icon={Pause} onClick={() => setModal({ type: 'pause' })}>
                Pause
              </Button>
            )}
            {['active', 'trial', 'paused'].includes(plan.status) && (
              <Button variant="reject-outline" icon={Ban} onClick={() => setModal({ type: 'cancel' })}>
                Cancel plan
              </Button>
            )}
            {plan.renewal === 'fixed' && (
              <Button variant="accept" icon={RotateCcw} onClick={() => setModal({ type: 'renew' })}>
                Renew
              </Button>
            )}
          </>
        }
      />

      <div className="stat-grid">
        <StatCard label="Plan price" value={formatBDT(plan.price.amount, { trim: true })} helper={perCycleLabel(plan.cycle)} />
        <StatCard label="Each seat" value={formatBDT(plan.perSeat, { trim: true })} helper={perCycleLabel(plan.cycle)} />
        <StatCard label="Renews in" value={renewsIn(plan.nextRenewal)} helper={plan.nextRenewal ? fmtShort(plan.nextRenewal) : undefined} />
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
          onInvite={() => setModal({ type: 'invite' })}
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
        <BoxHead title="Invite details" />
        <p>
          {free <= 0
            ? `All ${plan.seatsCap} seats are taken. If someone leaves, you can invite someone by email.`
            : `${plural(free, 'free seat')}. Each invite works for one email, and comes with a single-use backup link you can copy.`}
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
                <p className="t-meta">expires {fmtShort(i.expiresOn)}</p>
                {i.status === 'pending' && (
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
      {modal?.type === 'setDue' && <SetDueModal dueId={modal.member.dueId} name={modal.member.firstName} ownSeat={modal.member.isOwnerSeat} onClose={() => setModal(null)} />}
      {modal?.type === 'markPaid' && <MarkPaidModal dueId={modal.member.dueId} name={modal.member.firstName} method={plan.method} onClose={() => setModal(null)} />}
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
