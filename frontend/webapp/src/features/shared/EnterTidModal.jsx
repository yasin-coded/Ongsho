import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { getMySharedPlan } from '@/api/shared'
import { normalizeTid, submitPayment } from '@/api/payments'
import { METHODS, METHOD_KEYS } from '@/lib/colors'
import { fmtShort } from '@/lib/dates'
import { formatBDT, sum } from '@/lib/money'
import { useAction } from '@/hooks/useAction'
import { focusFirstInvalid } from '@/lib/formFocus'
import { validateTid } from '@/lib/validation'
import { Box } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { ErrorBox, Skeleton, Stepper } from '@/components/ui/Misc'

function dueLabel(d, { name } = {}) {
  const bits = []
  if (name) bits.push(`${name}’s`)
  if (d.monthLabel) bits.push(d.monthLabel)
  return bits.join(' · ') || (d.dueDate ? `Due ${fmtShort(d.dueDate)}` : 'Due')
}

function TidForm({ plan, onClose, othersOnly = false }) {
  const mine = othersOnly ? [] : plan.openDues
  const coverable = plan.coverable ?? []
  const [picked, setPicked] = useState(() => new Set(mine.map((d) => d.id)))
  const [method, setMethod] = useState(plan.method)
  const [tid, setTid] = useState('')
  const [clientFields, setClientFields] = useState({})
  const send = useAction(submitPayment, { onSuccess: onClose })
  const selectable = [...mine, ...coverable]
  const amount = sum(selectable.filter((d) => picked.has(d.id)), (d) => d.amount)
  const owner = plan.owner.firstName
  const firstDue = mine.at(-1)?.dueDate
  const toggle = (id) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <form
      className="modal__form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        const fields = {}
        if (!picked.size) fields.dues = 'Pick at least one due to cover.'
        const tidErr = validateTid(tid)
        if (tidErr) fields.tid = tidErr
        if (Object.keys(fields).length) {
          setClientFields(fields)
          focusFirstInvalid()
          return
        }
        setClientFields({})
        send.run({ planId: plan.id, dueIds: [...picked], method, tid })
      }}
    >
      <div className="modal__form-scroll modal__scroll grid gap-5">
      <Box variant="highlight" className="flex flex-wrap items-center gap-4 !p-4 !shadow-none">
        <ServiceLogo serviceKey={plan.serviceKey} name={plan.serviceName} size="small" />
        <div className="min-w-0 flex-1">
          <p className="t-sub">{plan.planName}</p>
          <p className="t-meta">
            Owner: {owner}
            {firstDue && ` · due ${fmtShort(firstDue)}`}
          </p>
        </div>
        <p className="text-right">
          <span className="t-mid block">{formatBDT(amount, { trim: true })}</span>
          <span className="t-meta">{mine.length > 1 ? 'selected total' : 'your share'}</span>
        </p>
      </Box>

      <fieldset className="grid gap-2">
        <legend className="field__label mb-2">{othersOnly ? 'Dues to cover' : 'Your open dues'}</legend>
        {mine.map((d) => (
          <label key={d.id} className="check">
            <input type="checkbox" checked={picked.has(d.id)} onChange={() => toggle(d.id)} />
            <span className="flex-1 font-bold">{dueLabel(d)}</span>
            <span className="t-num">{formatBDT(d.amount)}</span>
          </label>
        ))}
        {coverable.length > 0 && (
          <div className={`grid gap-2 ${mine.length ? 'mt-3' : ''}`}>
            <p className="t-label">Paying for someone else?</p>
            <p className="t-meta">Selected members will owe you. Confirm the ID on Review payments.</p>
            {coverable.map((d) => (
              <label key={d.id} className="check">
                <input type="checkbox" checked={picked.has(d.id)} onChange={() => toggle(d.id)} />
                <span className="flex-1">
                  <span className="font-bold">{dueLabel(d, { name: d.name })}</span>
                  <span className="t-meta block">They will owe you</span>
                </span>
                <span className="t-num">{formatBDT(d.amount)}</span>
              </label>
            ))}
          </div>
        )}
        {(clientFields.dues ?? send.fields.dues) && <p className="field__error">{clientFields.dues ?? send.fields.dues}</p>}
      </fieldset>

      <Select
        label="Payment method"
        value={method}
        onChange={(e) => setMethod(e.target.value)}
        options={METHOD_KEYS.map((k) => ({ value: k, label: METHODS[k].label }))}
        help={`${owner} recommends ${METHODS[plan.method]?.label ?? 'bKash'}, but pick whatever you used.`}
        error={send.fields.method}
      />
      <Input
        label="Transaction ID"
        value={tid}
        onChange={(e) => setTid(normalizeTid(e.target.value))}
        autoComplete="off"
        spellCheck="false"
        className="uppercase tabular-nums"
        help="You will find it in the confirmation message or in your payment app's history. Copy it exactly."
        maxLength={64}
        onBlur={() => {
          const err = tid ? validateTid(tid) : null
          setClientFields((p) => {
            const next = { ...p }
            if (err) next.tid = err
            else delete next.tid
            return next
          })
        }}
        error={clientFields.tid ?? send.fields.tid}
      />
      <Input label="Amount" value={formatBDT(amount)} locked help="Part payments are not supported yet, so this is always the full amount. No date is needed." />

      <div className="grid gap-3">
        <p className="t-label">What happens next</p>
        <Stepper
          current="pending"
          labels={
            othersOnly
              ? { due: 'Due', pending: 'Pending, after you send', paid: 'Paid, when you confirm on Review payments' }
              : { due: 'Due', pending: 'Pending, after you send', paid: `Paid, when ${owner} confirms` }
          }
        />
        <p className="t-meta">
          {othersOnly
            ? 'If the ID does not match, reject it on Review payments. Dues go back to Due.'
            : `If ${owner} cannot match the ID, this goes back to Due and you can send a new one.`}
        </p>
      </div>
      </div>

      <div className="modal__footer row-between border-t-[0.125rem] border-dashed border-[var(--color-dash)] pt-4">
        <p className="t-meta font-bold">Payments are made outside Ongsho.</p>
        <div className="row">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="accept" icon={ArrowRight} busy={send.busy} disabled={!picked.size}>
            Send for review
          </Button>
        </div>
      </div>
    </form>
  )
}

export function EnterTidModal({ planId, onClose }) {
  const query = useQuery({ queryKey: ['shared-plan', planId], queryFn: () => getMySharedPlan(planId) })
  const owner = query.data?.owner?.firstName ?? 'the owner'
  return (
    <Modal
      open
      onClose={onClose}
      title="Add your transaction ID"
      subtitle={`Paid ${owner} already? Send us the ID so they can confirm it.`}
      wide
      className="modal--tid"
    >
      {query.isPending && <Skeleton className="h-64" />}
      {query.isError && <ErrorBox error={query.error} onRetry={() => query.refetch()} />}
      {query.data && !query.data.notFound && <TidForm plan={query.data} onClose={onClose} />}
    </Modal>
  )
}
