import { useState } from 'react'
import { BadgeCheck, HandCoins, RotateCcw, X } from 'lucide-react'
import { markDuePaid, normalizeTid, rejectPayment, setDueBack, submitPayment, waiveDue, waivePayment } from '@/api/payments'
import { METHODS, METHOD_KEYS } from '@/lib/colors'
import { MOCK_TODAY, todayDhaka } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { useAction } from '@/hooks/useAction'
import { focusFirstInvalid } from '@/lib/formFocus'
import { validateTid } from '@/lib/validation'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'

const methodOptions = METHOD_KEYS.map((k) => ({ value: k, label: METHODS[k].label }))

export function RejectPaymentModal({ paymentId, name, onClose }) {
  const [reason, setReason] = useState('')
  const act = useAction(() => rejectPayment(paymentId, { reason }), { onSuccess: onClose, tone: 'due' })
  return (
    <Modal open onClose={onClose} title="Reject this payment?" subtitle={name ? `${name} will see your reason, and the due goes back to Due.` : 'The member will see your reason, and the due goes back to Due.'}>
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (!reason.trim()) {
            act.setFields({ reason: 'Write a short reason. The member will see it.' })
            return
          }
          act.run()
        }}
      >
        <Textarea label="Reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="For example: I cannot find this ID in my bKash history." error={act.fields.reason} />
        <div className="row justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="reject" icon={X} busy={act.busy}>
            Reject
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** Waive a pending payment (paymentId) or a due directly (dueId). */
export function WaiveModal({ paymentId, dueId, name, onClose }) {
  const [note, setNote] = useState('')
  const act = useAction(() => (paymentId ? waivePayment(paymentId, { note }) : waiveDue(dueId, { note })), { onSuccess: onClose, tone: 'waived' })
  return (
    <Modal open onClose={onClose} title="Waive this due?" subtitle={`${name ? `${name} owes` : 'They owe'} nothing for it after this. The note stays in the history.`}>
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (!note.trim()) {
            act.setFields({ note: 'Add a short note, for example "Birthday month".' })
            return
          }
          act.run()
        }}
      >
        <Textarea label="Note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: Birthday month." error={act.fields.note} />
        <div className="modal__footer row justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="waive" icon={HandCoins} busy={act.busy}>
            Waive
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function MarkPaidModal({ dueId, planId, name, method = 'bkash', ownSeat = false, coverable: coverableProp = [], onClose }) {
  const coverable = ownSeat ? coverableProp : []
  const [form, setForm] = useState({ date: MOCK_TODAY, method, note: '' })
  const [pickedMembers, setPickedMembers] = useState(() => new Set())
  const [tid, setTid] = useState('')
  const [clientFields, setClientFields] = useState({})

  const act = useAction(
    async () => {
      await markDuePaid(dueId, form)
      const memberDueIds = [...pickedMembers]
      if (memberDueIds.length) {
        await submitPayment({ planId, dueIds: memberDueIds, method: form.method, tid })
      }
    },
    { onSuccess: onClose },
  )

  const toggleMember = (id) =>
    setPickedMembers((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const coveringMembers = pickedMembers.size > 0

  return (
    <Modal
      open
      onClose={onClose}
      wide={ownSeat && coverable.length > 0}
      title={ownSeat ? 'Mark your seat as paid' : 'Mark as paid'}
      subtitle={
        ownSeat
          ? 'Record your share for this cycle. Optionally cover other members — they will owe you; confirm on Review payments.'
          : `Recorded by owner. Use this when ${name ?? 'a member'} paid you without sending an ID.`
      }
    >
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          const fields = {}
          if (form.date > todayDhaka()) {
            fields.date = 'The date cannot be in the future.'
          }
          if (coveringMembers) {
            const tidErr = validateTid(tid)
            if (tidErr) fields.tid = tidErr
          }
          if (Object.keys(fields).length) {
            act.setFields(fields)
            setClientFields(fields)
            focusFirstInvalid()
            return
          }
          setClientFields({})
          act.run()
        }}
      >
        <Input label="Date paid" type="date" max={todayDhaka()} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} error={act.fields.date ?? clientFields.date} />
        <Select label="Method" value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} options={methodOptions} error={act.fields.method} />
        <Textarea label="Note (optional)" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />

        {ownSeat && coverable.length > 0 && (
          <fieldset className="grid gap-2">
            <legend className="field__label mb-1">Also paying for members?</legend>
            <p className="t-meta mb-2">Optional. Pick whose dues you covered in the same payment. They will owe you (IOU).</p>
            {coverable.map((d) => (
              <label key={d.id} className="check">
                <input type="checkbox" checked={pickedMembers.has(d.id)} onChange={() => toggleMember(d.id)} />
                <span className="flex-1">
                  <span className="font-bold">
                    {d.name}’s {d.monthLabel}
                  </span>
                </span>
                <span className="t-num">{formatBDT(d.amount)}</span>
              </label>
            ))}
          </fieldset>
        )}

        {ownSeat && coveringMembers && (
          <Input
            label="Transaction ID"
            value={tid}
            onChange={(e) => setTid(normalizeTid(e.target.value))}
            autoComplete="off"
            spellCheck="false"
            className="uppercase tabular-nums"
            help="Required when you cover other members. Confirm this ID on Review payments."
            maxLength={64}
            error={clientFields.tid ?? act.fields.tid ?? act.fields.dues}
          />
        )}

        <div className="row justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="accept" icon={BadgeCheck} busy={act.busy}>
            {coveringMembers ? 'Mark paid & send for review' : 'Mark as paid'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function SetDueModal({ dueId, name, ownSeat, onClose }) {
  const act = useAction(() => setDueBack(dueId), { onSuccess: onClose, tone: 'due' })
  return (
    <Modal
      open
      onClose={onClose}
      title="Set back to Due?"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="solo-navy" icon={RotateCcw} busy={act.busy} onClick={() => act.run()}>
            Set to Due
          </Button>
        </>
      }
    >
      <p>
        {ownSeat
          ? 'Your own seat starts as Paid. Setting it to Due is only a reminder for you; nobody else is told.'
          : `${name}'s due goes back to Due. A confirmed payment for it is reversed, and ${name} is told.`}
      </p>
    </Modal>
  )
}