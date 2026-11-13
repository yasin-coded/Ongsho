import { useState } from 'react'
import { useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Download, LogOut, ReceiptText, TriangleAlert } from 'lucide-react'
import { cancelLeaveRequest, downloadMyStatement, getMySharedPlan } from '@/api/shared'
import { memberSharedStatus } from '@/api/adapters/shared'
import { fmtShort, fmtWhen, monthKey, renewsInLabel, todayDhaka } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { cycleLabel, perCycleLabel } from '@/mocks/schedule'
import { useAction } from '@/hooks/useAction'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead, StatCard } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { Select } from '@/components/ui/Field'
import { MethodTag, RoleTag, StatusPill } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { EmptyState, SkeletonCard, Stepper } from '@/components/ui/Misc'
import { Loadable } from '@/features/common/PlanBits'
import { NotFoundPage } from '@/features/NotFoundPage'
import { EnterTidModal } from './EnterTidModal'
import { RequestLeaveModal } from './RequestLeaveModal'

function StatementPicker({ plan }) {
  const months = [...new Map(plan.history.map((h) => [monthKey(h.dueDate), h.monthLabel])).entries()]
  const [month, setMonth] = useState(months[0]?.[0] ?? monthKey(todayDhaka()))
  const download = useAction(() => downloadMyStatement(plan.id, { month }), { toastMessage: (r) => `Statement ${r.number} is ready. In the real app the PDF downloads now.` })
  if (!months.length) return null
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select label="Statement month" value={month} onChange={(e) => setMonth(e.target.value)} options={months.map(([value, label]) => ({ value, label }))} fieldClass="min-w-[10rem]" />
      <Button variant="ghost" icon={Download} busy={download.busy} onClick={() => download.run()}>
        Download statement
      </Button>
    </div>
  )
}

function MemberPlan({ plan }) {
  const [paying, setPaying] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const cancelLeave = useAction(() => cancelLeaveRequest(plan.id), { tone: 'waived' })
  const owner = plan.owner.firstName
  const open = plan.openDues.length > 0
  const status = memberSharedStatus(plan)
  const openTotal = plan.openDues.reduce((a, d) => a + d.amount, 0)
  const rows = showAll ? plan.history : plan.history.slice(0, 5)

  return (
    <div className="stack-lg">
      <TopBar
        breadcrumb={[{ label: 'Shared Plans', to: '/app/shared' }, { label: plan.planName }]}
        title={plan.planName}
        subtitle={`Owner: ${owner} · ${cycleLabel(plan.cycle).toLowerCase()} · ${plan.nextRenewal ? `renews ${fmtShort(plan.nextRenewal)}` : 'no next renewal'}`}
        lead={<ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="large" />}
        tools={false}
        actions={
          <>
            <StatusPill status={status} />
            {open && (
              <Button variant="accept" size="lg" icon={ReceiptText} onClick={() => setPaying(true)}>
                Enter TID
              </Button>
            )}
          </>
        }
      />

      <div className="stat-grid">
        <StatCard label="Your share" value={formatBDT(plan.myShare, { trim: true })} helper={perCycleLabel(plan.cycle)} />
        <StatCard label="Total you spent" value={formatBDT(plan.totalSpent, { trim: true })} helper="on this plan" />
        <StatCard label="Renews in" value={renewsInLabel(plan.nextRenewal)} helper={plan.nextRenewal ? fmtShort(plan.nextRenewal) : undefined} />
      </div>

      <Box roomy className="grid gap-6">
        <Stepper current={status} />
        {open && plan.lastRejection && (
          <div className="neo-box neo-box--flat neo-box--danger row gap-3 !p-4" role="alert">
            <TriangleAlert aria-hidden="true" className="size-6 flex-none" />
            <p>
              <strong>{owner} could not match your last ID.</strong> Reason: “{plan.lastRejection}”. Send a new one.
            </p>
          </div>
        )}
        <div className="row-between">
          <p className="t-sub">
            {open
              ? `Pay ${owner} ${formatBDT(openTotal, { trim: true })}, then add your transaction ID`
              : plan.pendingAmount
                ? `Waiting for ${owner} to confirm${plan.pendingSince ? `, sent ${fmtWhen(plan.pendingSince)}` : ''}`
                : 'You are paid up. Nothing to do.'}
          </p>
          {open && (
            <Button variant="accept" icon={ReceiptText} onClick={() => setPaying(true)}>
              {plan.lastRejection ? 'Send a new ID' : 'Enter TID'}
            </Button>
          )}
        </div>
      </Box>

      <div className="two-col">
        <Box>
          <BoxHead title="Your payments on this plan" />
          {plan.history.length ? (
            <div className="grid gap-5">
              <div className="table-scroll">
                <table className="neo-table">
                  <thead>
                    <tr>
                      <th scope="col">Month</th>
                      <th scope="col">Method</th>
                      <th scope="col">Amount</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((h) => (
                      <tr key={h.id}>
                        <td className="font-bold">
                          {h.monthLabel}
                          {h.tid && <span className="t-meta block font-normal">ID {h.tid}</span>}
                          {h.waiverNote && <span className="t-meta block font-normal">{h.waiverNote}</span>}
                        </td>
                        <td>{h.method ? <MethodTag method={h.method} /> : <span className="t-muted">—</span>}</td>
                        <td className="t-num">{formatBDT(h.amount)}</td>
                        <td>
                          <StatusPill status={h.status} small />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {plan.history.length > 5 && (
                <button type="button" className="text-link w-fit" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
                  {showAll ? 'Show fewer' : `View all ${plan.history.length}`}
                </button>
              )}
              <StatementPicker plan={plan} />
            </div>
          ) : (
            <EmptyState title="No payments yet" />
          )}
        </Box>

        <div className="stack">
          <Box>
            <BoxHead title="Plan details" />
            <dl className="dashed-rows">
              {[
                ['Owner', plan.owner.name],
                ['Plan price', `${formatBDT(plan.price.amount)} ${perCycleLabel(plan.cycle)}`],
                ['Seats', `${plan.seats}, ${formatBDT(plan.myShare, { trim: true })} each`],
                ['Recommended payment', <MethodTag key="m" method={plan.method} />],
                ["Owner's note", plan.note || '—'],
              ].map(([k, v]) => (
                <div key={k} className="row-between py-2.5">
                  <dt className="t-label">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
          </Box>

          <Box>
            <BoxHead title="In this plan" sub="You can see names and avatars only." />
            <ul className="dashed-rows">
              {plan.members.map((m) => (
                <li key={m.id} className="row-between py-2.5">
                  <span className="row gap-3">
                    <Avatar name={m.name} color={m.avatarColor} size="sm" status={m.isYou ? m.status : undefined} decorative={!m.isYou} />
                    <span className="font-bold">{m.isYou ? 'You' : m.name}</span>
                  </span>
                  <RoleTag role={m.isOwner ? 'ownerTag' : 'member'} />
                </li>
              ))}
            </ul>
          </Box>

          <Box>
            <BoxHead title="IOUs" />
            {plan.ious.length ? (
              <ul className="dashed-rows">
                {plan.ious.map((i) => (
                  <li key={i.text} className="row-between py-2.5">
                    <span className="font-bold">{i.text.trim()}</span>
                    <span className="t-num font-bold" style={{ color: i.youOwe ? '#d40000' : '#1d7a00' }}>
                      {formatBDT(i.amount, { trim: true })}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="t-meta">All settled.</p>
            )}
          </Box>

          <Box>
            <BoxHead title="Leaving?" />
            {plan.me.leaveRequested ? (
              <div className="grid gap-3">
                <p className="font-bold">Leave requested{plan.me.leaveRequestedAt ? ` on ${fmtShort(dhakaDate(plan.me.leaveRequestedAt))}` : ''}.</p>
                <button type="button" className="text-link w-fit" onClick={() => cancelLeave.run()} disabled={cancelLeave.busy}>
                  Cancel request
                </button>
              </div>
            ) : (
              <div className="grid gap-4">
                <p>
                  Ask {owner} to let you leave. You stay in the plan until they approve.
                </p>
                <Button variant="reject-outline" icon={LogOut} onClick={() => setLeaving(true)}>
                  Ask to leave this plan
                </Button>
              </div>
            )}
          </Box>
        </div>
      </div>

      {paying && <EnterTidModal planId={plan.id} onClose={() => setPaying(false)} />}
      {leaving && <RequestLeaveModal plan={plan} onClose={() => setLeaving(false)} />}
    </div>
  )
}

export function MemberPlanPage() {
  const { id } = useParams()
  const query = useQuery({ queryKey: ['shared-plan', id], queryFn: () => getMySharedPlan(id) })
  return (
    <Loadable
      query={query}
      skeleton={
        <div className="stack">
          <SkeletonCard />
          <SkeletonCard lines={5} />
        </div>
      }
    >
      {(plan) => (plan.notFound ? <NotFoundPage inApp /> : <MemberPlan plan={plan} />)}
    </Loadable>
  )
}
