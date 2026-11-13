import { useState } from 'react'
import { BadgeCheck, HandCoins, RotateCcw, X } from 'lucide-react'
import { markDuePaid, rejectPayment, setDueBack, waiveDue, waivePayment } from '@/api/payments'
import { METHODS, METHOD_KEYS } from '@/lib/colors'
import { MOCK_TODAY, todayDhaka } from '@/lib/dates'
import { useAction } from '@/hooks/useAction'
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

export function MarkPaidModal({ dueId, name, method = 'bkash', onClose }) {
  const [form, setForm] = useState({ date: MOCK_TODAY, method, note: '' })
  const act = useAction(() => markDuePaid(dueId, form), { onSuccess: onClose })
  return (
    <Modal open onClose={onClose} title="Mark as paid" subtitle={`Recorded by owner. Use this when ${name ?? 'a member'} paid you without sending an ID.`}>
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (form.date > todayDhaka()) {
            act.setFields({ date: 'The date cannot be in the future.' })
            return
          }
          act.run()
        }}
      >
        <Input label="Date paid" type="date" max={todayDhaka()} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} error={act.fields.date} />
        <Select label="Method" value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })} options={methodOptions} error={act.fields.method} />
        <Textarea label="Note (optional)" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        <div className="row justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="accept" icon={BadgeCheck} busy={act.busy}>
            Mark as paid
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
