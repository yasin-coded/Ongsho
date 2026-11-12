import { db, ME, nextId } from '@/mocks/db'
import { chargeById, dueById, firstName, memberById, myMemberRow, paymentById, planById, settlingPayment, userById } from '@/mocks/selectors'
import { audit, notifyMe, resolveNotifications, setDueStatus } from '@/mocks/engine'
import { MOCK_TODAY, fmtMonth, mockNow } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { METHODS } from '@/lib/colors'
import { ApiError, write } from '../client'

function ownedPlanOf(planId) {
  const plan = planById(planId)
  if (!plan || plan.ownerId !== ME) throw new ApiError('Only the owner can do this.', { status: 404 })
  return plan
}

const whoPaid = (payment) => firstName(userById(memberById(payment.payerMemberId).userId))
const monthsOf = (payment) =>
  [...new Set(payment.allocations.map((a) => fmtMonth(chargeById(dueById(a.dueId).chargeId).dueDate).split(' ')[0]))]
const monthNames = { Jan: 'January', Feb: 'February', Mar: 'March', Apr: 'April', May: 'May', Jun: 'June', Jul: 'July', Aug: 'August', Sep: 'September', Oct: 'October', Nov: 'November', Dec: 'December' }
const coveredText = (payment) => monthsOf(payment).map((m) => monthNames[m]).join(' and ')

export const normalizeTid = (tid) => String(tid ?? '').replace(/\s+/g, '').toUpperCase()

// ---------- owner ----------
export function confirmPayment(paymentId) {
  return write(() => {
    const payment = paymentById(paymentId)
    ownedPlanOf(payment.planId)
    if (payment.review !== 'pending') throw new ApiError('This payment was already decided.', { status: 409 })
    payment.review = 'confirmed'
    payment.reviewedAt = mockNow()
    for (const a of payment.allocations) {
      const due = dueById(a.dueId)
      setDueStatus(due, 'paid', { paidOn: MOCK_TODAY, rejectionReason: null })
    }
    resolveNotifications((a) => a.type === 'payment' && a.paymentId === paymentId, 'approved')
    return { message: `Payment confirmed. It covered ${coveredText(payment)}.` }
  })
}

export function rejectPayment(paymentId, { reason }) {
  return write(() => {
    const payment = paymentById(paymentId)
    ownedPlanOf(payment.planId)
    const clean = (reason ?? '').trim()
    if (!clean) throw new ApiError('Tell the member why.', { fields: { reason: 'Write a short reason. The member will see it.' } })
    if (payment.review !== 'pending') throw new ApiError('This payment was already decided.', { status: 409 })
    payment.review = 'rejected'
    payment.reviewedAt = mockNow()
    payment.rejectionReason = clean
    for (const a of payment.allocations) setDueStatus(dueById(a.dueId), 'due', { rejectionReason: clean })
    resolveNotifications((a) => a.type === 'payment' && a.paymentId === paymentId, 'rejected')
    return { message: `Rejected. ${whoPaid(payment)}'s due is back to Due, and they can see your reason.` }
  })
}

export function reversePayment(paymentId) {
  return write(() => {
    const payment = paymentById(paymentId)
    ownedPlanOf(payment.planId)
    if (payment.review !== 'confirmed') throw new ApiError('Only a confirmed payment can be reversed.', { status: 409 })
    payment.review = 'reversed'
    payment.reviewedAt = mockNow()
    for (const a of payment.allocations) setDueStatus(dueById(a.dueId), 'due', { paidOn: null })
    audit({ planId: payment.planId, action: 'reversed', entity: paymentId, tone: 'due', text: `You reversed ${whoPaid(payment)}'s payment`, amount: payment.amount })
    return { message: 'Reversed. The original stays in the history, and the due is back to Due.' }
  })
}

export function waivePayment(paymentId, { note }) {
  return write(() => {
    const payment = paymentById(paymentId)
    ownedPlanOf(payment.planId)
    const clean = (note ?? '').trim()
    if (!clean) throw new ApiError('Add a note.', { fields: { note: 'Add a short note, for example "Birthday month".' } })
    payment.review = 'rejected'
    payment.reviewedAt = mockNow()
    payment.rejectionReason = 'The owner waived this due.'
    for (const a of payment.allocations) setDueStatus(dueById(a.dueId), 'waived', { waiverNote: clean })
    resolveNotifications((a) => a.type === 'payment' && a.paymentId === paymentId, 'waived')
    audit({ planId: payment.planId, action: 'waived', tone: 'info', text: `You waived ${whoPaid(payment)}'s due: ${clean}`, amount: payment.amount })
    return { message: 'Waived. Nothing is owed for that due now.' }
  })
}

export function waiveDue(dueId, { note }) {
  return write(() => {
    const due = dueById(dueId)
    ownedPlanOf(due.planId)
    const clean = (note ?? '').trim()
    if (!clean) throw new ApiError('Add a note.', { fields: { note: 'Add a short note, for example "Birthday month".' } })
    const pending = settlingPayment(dueId)
    if (pending?.review === 'pending') {
      pending.review = 'rejected'
      pending.reviewedAt = mockNow()
      pending.rejectionReason = 'The owner waived this due.'
    }
    setDueStatus(due, 'waived', { waiverNote: clean })
    const who = firstName(userById(memberById(due.memberId).userId))
    audit({ planId: due.planId, action: 'waived', tone: 'info', text: `You waived ${who}'s due: ${clean}`, amount: due.amount })
    return { message: 'Waived.' }
  })
}

export function markDuePaid(dueId, { date, method, note }) {
  return write(() => {
    const due = dueById(dueId)
    ownedPlanOf(due.planId)
    const fields = {}
    if (!date) fields.date = 'Pick the date you were paid.'
    else if (date > MOCK_TODAY) fields.date = 'The date cannot be in the future.'
    if (!METHODS[method]) fields.method = 'Pick how you were paid.'
    if (Object.keys(fields).length) throw new ApiError('Check the fields.', { fields })
    if (due.status === 'paid') throw new ApiError('This due is already Paid.', { status: 409 })
    const member = memberById(due.memberId)
    db.payments.push({
      id: nextId('pay'), planId: due.planId, payerMemberId: member.id, method, tid: null, amount: due.amount, paidOn: date, recordedBy: ME,
      review: 'confirmed', submittedAt: mockNow(), reviewedAt: mockNow(), rejectionReason: null, note: (note ?? '').trim(),
      allocations: [{ dueId, amount: due.amount }],
    })
    setDueStatus(due, 'paid', { paidOn: date, recordedByOwner: true, note: (note ?? '').trim() || null })
    return { message: `Marked as Paid (recorded by owner). ${firstName(userById(member.userId))} is told.` }
  })
}

export function setDueBack(dueId) {
  return write(() => {
    const due = dueById(dueId)
    ownedPlanOf(due.planId)
    const payment = settlingPayment(dueId)
    if (payment?.review === 'confirmed' && payment.recordedBy !== ME) {
      payment.review = 'reversed'
      payment.reviewedAt = mockNow()
    }
    setDueStatus(due, 'due', { paidOn: null, recordedByOwner: false })
    const m = memberById(due.memberId)
    audit({ planId: due.planId, action: 'set_due', tone: 'due', text: m.isOwnerSeat ? 'You set your own seat back to Due' : `You set ${firstName(userById(m.userId))}'s due back to Due`, amount: due.amount })
    return { message: 'Set back to Due.' }
  })
}

// ---------- member ----------
export function submitPayment({ planId, dueIds, method, tid }) {
  return write(() => {
    const plan = planById(planId)
    const me = myMemberRow(planId, ME)
    if (!plan || !me) throw new ApiError('You are not in this plan.', { status: 404 })
    const fields = {}
    const clean = normalizeTid(tid)
    if (!dueIds?.length) fields.dues = 'Pick at least one due to cover.'
    if (!METHODS[method]) fields.method = 'Pick the method you used.'
    if (!clean) fields.tid = 'Enter the transaction ID from your payment app.'
    else if (clean.length < 6) fields.tid = 'That looks too short. Copy the full ID.'
    else if (db.payments.some((p) => p.planId === planId && p.tid && normalizeTid(p.tid) === clean)) fields.tid = 'This ID was already used on this plan.'
    if (Object.keys(fields).length) throw new ApiError('Check the highlighted fields.', { fields })
    const dues = dueIds.map(dueById)
    if (dues.some((d) => !d || d.planId !== planId || d.status !== 'due')) throw new ApiError('One of those dues is no longer open. Refresh and try again.', { status: 409 })
    if (plan.mode === 'reseller' && dues.some((d) => d.memberId !== me.id)) throw new ApiError('Paying for someone else is off in Reseller plans.', { status: 409 })
    const amount = dues.reduce((a, d) => a + d.amount, 0)
    const payment = {
      id: nextId('pay'), planId, payerMemberId: me.id, method, tid: clean, amount, paidOn: null, recordedBy: ME, review: 'pending',
      submittedAt: mockNow(), reviewedAt: null, rejectionReason: null, allocations: dues.map((d) => ({ dueId: d.id, amount: d.amount })),
    }
    db.payments.push(payment)
    for (const d of dues) setDueStatus(d, 'pending', { rejectionReason: null })
    if (plan.ownerId === ME) {
      notifyMe({ kind: 'payment_submitted', title: 'You sent a transaction ID', detail: `${plan.planName} · ${METHODS[method].label} · ID ${clean} · ${formatBDT(amount)}`, link: `/app/plans/${planId}/review`, action: { type: 'payment', paymentId: payment.id } })
    }
    const owner = firstName(userById(plan.ownerId))
    return { message: `Sent. ${owner} will confirm it. Until then your due shows Pending.`, paymentId: payment.id }
  })
}
