import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ArrowRightLeft, Check, Mail, Trash2, UserPlus, X } from 'lucide-react'
import * as plans from '@/api/plans'
import { todayDhaka, fmtShort } from '@/lib/dates'
import { formatBDT, formatRate, formatUSD, parseTaka, splitExact } from '@/lib/money'
import {
  validateAmount,
  validateDateNotBeforeToday,
  validateEmail,
  validateLeaveDate,
  validateMemberId,
  validateRate,
  validateRequiredPassword,
} from '@/lib/validation'
import { useAction } from '@/hooks/useAction'
import { useValidatedAction } from '@/hooks/useValidatedAction'
import { focusFirstInvalid } from '@/lib/formFocus'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput, Select } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'

function FormModal({ title, subtitle, onClose, onSubmit, children, submit }) {
  return (
    <Modal open onClose={onClose} title={title} subtitle={subtitle}>
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        {children}
        <div className="modal__footer row justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {submit}
        </div>
      </form>
    </Modal>
  )
}

/** A simple yes / no step for pause, resume, cancel. */
export function ConfirmModal({ title, body, confirmLabel, variant = 'accept', icon, action, onClose, tone, toastMessage }) {
  const act = useAction(action, { onSuccess: onClose, tone, toastMessage })
  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={variant} icon={icon} busy={act.busy} onClick={() => act.run()}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p>{body}</p>
    </Modal>
  )
}

export function RenewModal({ plan, onClose }) {
  const today = todayDhaka()
  const [endDate, setEndDate] = useState(plan.endDate ?? '')
  const act = useValidatedAction(() => plans.renewPlan(plan.id, { endDate }), {
    validate: () => {
      const fields = {}
      if (!endDate) fields.endDate = 'Pick the new end date.'
      else if (plan.startDate && endDate <= plan.startDate) fields.endDate = 'The end date must be after the start date.'
      else {
        const nb = validateDateNotBeforeToday(endDate, 'End date')
        if (nb) fields.endDate = nb
      }
      return fields
    },
    knownFieldKeys: ['endDate'],
    onSuccess: onClose,
    toastMessage: 'Renewed. New charges follow the same rules.',
  })
  return (
    <FormModal title="Renew this plan" subtitle="Fixed-term plans stop at their end date. Pick the new one." onClose={onClose} onSubmit={() => act.run()} submit={<Button type="submit" variant="accept" icon={Check} busy={act.busy}>Renew</Button>}>
      <Input label="New end date" type="date" min={today} value={endDate} onChange={(e) => setEndDate(e.target.value)} error={act.fields.endDate} />
      {act.formAlert && (
        <p role="alert" className="field__error">
          {act.formAlert}
        </p>
      )}
    </FormModal>
  )
}

/** Approve a leave request, or remove a member (same fields). */
export function LeaveModal({ plan, member, mode = 'leave', onClose }) {
  const [leaveDate, setLeaveDate] = useState(todayDhaka())
  const [leaveError, setLeaveError] = useState(null)
  const [unpaid, setUnpaid] = useState('keep')
  const approve = useAction(() => plans.decideLeave(member.id, { approve: true, leaveDate, unpaid }), {
    onSuccess: onClose,
    toastMessage: `${member.firstName} ${mode === 'remove' ? 'was removed' : 'left the plan'}. The next charge is recalculated.`,
  })
  const decline = useAction(() => plans.decideLeave(member.id, { approve: false }), { onSuccess: onClose, tone: 'waived', toastMessage: `${member.firstName} stays in the plan.` })
  const remaining = plan.members.filter((m) => m.id !== member.id).length
  const shares = remaining ? splitExact(plan.price.amount, remaining, 0) : []

  return (
    <Modal
      open
      onClose={onClose}
      title={mode === 'remove' ? `Remove ${member.firstName}?` : `${member.firstName} wants to leave`}
      subtitle={plan.planName}
      footer={
        <>
          {mode === 'leave' ? (
            <Button variant="ghost" busy={decline.busy} icon={X} onClick={() => decline.run()}>
              Decline
            </Button>
          ) : (
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          )}
          <Button
            variant={mode === 'remove' ? 'reject' : 'accept'}
            icon={Check}
            busy={approve.busy}
            onClick={() => {
              const err = validateLeaveDate(leaveDate)
              if (err) {
                setLeaveError(err)
                focusFirstInvalid()
                return
              }
              setLeaveError(null)
              approve.run()
            }}
          >
            {mode === 'remove' ? 'Remove' : 'Approve'}
          </Button>
        </>
      }
    >
      <div className="grid gap-5">
        <Input label="Leave date" type="date" min={todayDhaka()} value={leaveDate} onChange={(e) => setLeaveDate(e.target.value)} onBlur={() => setLeaveError(validateLeaveDate(leaveDate))} error={leaveError ?? approve.fields.leaveDate} help="No new dues are created for them from this date." />
        <fieldset className="grid gap-2">
          <legend className="field__label mb-2">Their unpaid dues</legend>
          {[
            { value: 'keep', label: 'Keep as debt record', help: 'They still owe it, and it stays in the ledger.' },
            { value: 'waive', label: 'Waive', help: 'Nothing is owed. A note says it was waived when they left.' },
          ].map((o) => (
            <label key={o.value} className="check items-start">
              <input type="radio" name="unpaid" value={o.value} checked={unpaid === o.value} onChange={() => setUnpaid(o.value)} className="mt-0.5" />
              <span>
                <span className="font-bold">{o.label}</span>
                <span className="t-meta block">{o.help}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <p className="neo-box neo-box--flat neo-box--highlight !p-4 t-meta">
          {plan.split === 'custom'
            ? 'This plan uses a custom split. After they leave, fix the amounts in Edit so they add up again.'
            : remaining
              ? `The next charge splits ${formatBDT(plan.price.amount, { trim: true })} between ${remaining} ${remaining === 1 ? 'person' : 'people'}, about ${formatBDT(shares.at(-1), { trim: true })} each.`
              : 'Nobody is left to split the next charge with.'}
        </p>
      </div>
    </Modal>
  )
}

export function ReplaceModal({ member, onClose }) {
  const [email, setEmail] = useState('')
  const act = useValidatedAction(() => plans.replaceMember(member.id, { email }), {
    validate: () => {
      const em = validateEmail(email)
      return em ? { email: em } : {}
    },
    knownFieldKeys: ['email'],
    onSuccess: onClose,
    toastMessage: `Invite sent. ${member.firstName} leaves when the new person joins.`,
  })
  return (
    <FormModal title={`Replace ${member.firstName}`} subtitle="Nobody else's share changes." onClose={onClose} onSubmit={() => act.run()} submit={<Button type="submit" variant="accept" icon={Mail} busy={act.busy}>Send invite</Button>}>
      <Input label="Email of the new person" type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} error={act.fields.email} />
      {act.formAlert && (
        <p role="alert" className="field__error">
          {act.formAlert}
        </p>
      )}
    </FormModal>
  )
}

export function InviteModal({ plan, onClose }) {
  const [email, setEmail] = useState('')
  const act = useValidatedAction(() => plans.createInvite(plan.id, { email }), {
    validate: () => {
      const em = validateEmail(email)
      return em ? { email: em } : {}
    },
    knownFieldKeys: ['email'],
    onSuccess: onClose,
    toastMessage: (inv) => `Invite sent to ${inv.email}. It expires on ${fmtShort(inv.expiresOn)}.`,
  })
  return (
    <FormModal
      title="Invite by email"
      subtitle="Each invite works for one email, and comes with a single-use backup link you can copy."
      onClose={onClose}
      onSubmit={() => act.run()}
      submit={<Button type="submit" variant="primary-orange" icon={UserPlus} busy={act.busy}>Send invite</Button>}
    >
      <Input label="Email" type="email" autoComplete="off" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} error={act.fields.email} help="People who do not have an Ongsho account get a sign-up page from the invite." />
      {act.formAlert && (
        <p role="alert" className="field__error">
          {act.formAlert}
        </p>
      )}
    </FormModal>
  )
}

export function TransferModal({ plan, onClose }) {
  const candidates = plan.members.filter((m) => !m.isOwnerSeat && m.status !== 'left')
  const [memberId, setMemberId] = useState('')
  const [password, setPassword] = useState('')
  const act = useValidatedAction(() => plans.startTransfer(plan.id, { memberId, password }), {
    validate: () => {
      const fields = {}
      const mid = validateMemberId(memberId)
      if (mid) fields.memberId = mid
      const pw = validateRequiredPassword(password)
      if (pw) fields.password = pw
      return fields
    },
    knownFieldKeys: ['memberId', 'password'],
    onSuccess: onClose,
    tone: 'pending',
    toastMessage: 'Request sent. Nothing changes until they accept.',
  })
  return (
    <FormModal title="Transfer ownership" subtitle="The new owner must accept. Until then nothing changes." onClose={onClose} onSubmit={() => act.run()} submit={<Button type="submit" variant="accept" icon={ArrowRightLeft} busy={act.busy} disabled={!candidates.length}>Send request</Button>}>
      {candidates.length ? (
        <>
          <Select label="New owner" value={memberId} placeholder="Pick a member" onChange={(e) => setMemberId(e.target.value)} options={candidates.map((m) => ({ value: m.id, label: m.name }))} error={act.fields.memberId} />
          <PasswordInput label="Your password" autoComplete="current-password" maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} error={act.fields.password} />
          <p className="t-meta">You become a member with a seat, and all history stays with the plan.</p>
          {act.formAlert && (
            <p role="alert" className="field__error">
              {act.formAlert}
            </p>
          )}
        </>
      ) : (
        <p>Nobody else is in this plan yet. Invite someone first.</p>
      )}
    </FormModal>
  )
}

export function DeletePlanModal({ plan, onClose }) {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const act = useValidatedAction(() => plans.deletePlan(plan.id, { password }), {
    validate: () => {
      const pw = validateRequiredPassword(password)
      return pw ? { password: pw } : {}
    },
    knownFieldKeys: ['password'],
    tone: 'due',
    toastMessage: (r) => (r.archived ? `${plan.planName} is archived. Members are told, and confirmed payments stay on record.` : `${plan.planName} is deleted. Members are told.`),
    onSuccess: () => navigate('/app/plans', { replace: true }),
  })
  return (
    <FormModal
      title={`Delete ${plan.planName}?`}
      subtitle="Members are told. Plans with confirmed payments are archived, not erased."
      onClose={onClose}
      onSubmit={() => act.run()}
      submit={<Button type="submit" variant="reject" icon={Trash2} busy={act.busy}>Delete plan</Button>}
    >
      <p>Archived plans are hidden everywhere but keep their payment history for statements. A plan with no confirmed member payments is erased.</p>
      <PasswordInput label="Your password" autoComplete="current-password" maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} error={act.fields.password} />
      {act.formAlert && (
        <p role="alert" className="field__error">
          {act.formAlert}
        </p>
      )}
    </FormModal>
  )
}

export function PriceChangeModal({ plan, onClose }) {
  const usd = plan.currency === 'USD'
  const today = todayDhaka()
  const [form, setForm] = useState({ amount: '', usd: '', rate: usd ? String(plan.price.rate / 100) : '', effectiveFrom: plan.nextRenewal ?? today })
  const amountPaisa = parseTaka(form.amount)
  const usdCents = parseTaka(form.usd)
  const ratePaisa = parseTaka(form.rate)
  const act = useValidatedAction(
    () => plans.addPriceChange(plan.id, usd ? { usd: (usdCents ?? 0) / 100, rate: (ratePaisa ?? 0) / 100, effectiveFrom: form.effectiveFrom } : { amount: (amountPaisa ?? 0) / 100, effectiveFrom: form.effectiveFrom }),
    {
      validate: () => {
        const fields = {}
        if (usd) {
          const u = validateAmount(form.usd)
          if (u) fields.usd = u
          const r = validateRate(form.rate)
          if (r) fields.rate = r
        } else {
          const a = validateAmount(form.amount)
          if (a) fields.amount = a
        }
        const eff = validateDateNotBeforeToday(form.effectiveFrom, 'Effective date')
        if (eff) fields.effectiveFrom = eff
        return fields
      },
      knownFieldKeys: ['amount', 'usd', 'rate', 'effectiveFrom'],
      onSuccess: onClose,
      toastMessage: `Price change saved. Charges from ${fmtShort(form.effectiveFrom)} use it; older ones keep the old price.`,
    },
  )
  return (
    <FormModal title="Add a price change" subtitle="Charges before the date keep the old price." onClose={onClose} onSubmit={() => act.run()} submit={<Button type="submit" variant="accept" icon={Check} busy={act.busy}>Save change</Button>}>
      {usd ? (
        <div className="grid gap-5 sm:grid-cols-2">
          <Input label="New price ($)" inputMode="decimal" numeric value={form.usd} onChange={(e) => setForm({ ...form, usd: e.target.value })} error={act.fields.usd} />
          <Input label="Rate (৳ for $1)" inputMode="decimal" numeric value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} error={act.fields.rate} />
          {usdCents > 0 && ratePaisa > 0 && (
            <p className="t-meta font-bold sm:col-span-2">
              {formatUSD(usdCents)} × {formatRate(ratePaisa)} = {formatBDT(Math.round((usdCents * ratePaisa) / 100))}
            </p>
          )}
        </div>
      ) : (
        <Input label="New price (৳)" inputMode="decimal" numeric value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} error={act.fields.amount} />
      )}
      <Input label="Starts from" type="date" min={today} value={form.effectiveFrom} onChange={(e) => setForm({ ...form, effectiveFrom: e.target.value })} error={act.fields.effectiveFrom} />
      {act.formAlert && (
        <p role="alert" className="field__error">
          {act.formAlert}
        </p>
      )}
    </FormModal>
  )
}

export function EditRateModal({ charge, onClose }) {
  const [rate, setRate] = useState(String(charge.rate / 100))
  const ratePaisa = parseTaka(rate)
  const act = useValidatedAction(() => plans.correctRate(charge.id, { rate: (ratePaisa ?? 0) / 100 }), {
    validate: () => {
      const r = validateRate(rate)
      return r ? { rate: r } : {}
    },
    knownFieldKeys: ['rate'],
    onSuccess: onClose,
    toastMessage: 'Rate corrected. The shares were recalculated.',
  })
  return (
    <FormModal title={`Edit rate for ${charge.monthLabel}`} subtitle="Use the rate your card was actually charged. Possible until a member sends a payment." onClose={onClose} onSubmit={() => act.run()} submit={<Button type="submit" variant="accept" icon={Check} busy={act.busy}>Save rate</Button>}>
      <Input label="Rate (৳ for $1)" inputMode="decimal" numeric value={rate} onChange={(e) => setRate(e.target.value)} error={act.fields.rate} />
      {ratePaisa > 0 && (
        <p className="t-meta font-bold">
          {formatUSD(charge.usdCents)} × {formatRate(ratePaisa)} = {formatBDT(Math.round((charge.usdCents * ratePaisa) / 100))}
        </p>
      )}
    </FormModal>
  )
}
