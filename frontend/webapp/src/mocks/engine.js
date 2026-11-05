import { MOCK_TODAY, addDays, mockNow } from '@/lib/dates'
import { db, ME, LEAD_DAYS, nextId } from './db'
import { dueDatesBetween, periodEndFor, priceAt, splitCharge, isActiveOn } from './schedule'
import { chargesOf, duesOfCharge, memberById } from './selectors'

export function audit(entry) {
  db.audit.push({ id: nextId('a'), ts: mockNow(), actor: ME, ...entry })
}

export function resolveNotifications(match, resolved) {
  for (const n of db.notifications) {
    if (n.action && match(n.action) && !n.resolved) {
      n.resolved = resolved
      n.readAt = n.readAt ?? mockNow()
    }
  }
}

export function notifyMe(fields) {
  db.notifications.push({ id: nextId('n'), userId: ME, readAt: null, link: null, action: null, resolved: null, createdAt: mockNow(), ...fields })
}

function newDue(charge, member, amount) {
  return {
    id: `due-${charge.id}-${member.id}`, chargeId: charge.id, planId: charge.planId, memberId: member.id, amount,
    status: member.isOwnerSeat ? 'paid' : 'due', waiverNote: null, rejectionReason: null,
    paidOn: member.isOwnerSeat ? charge.dueDate : null, recordedByOwner: false, note: null,
  }
}

/** Create any charge that should exist (renewal within the lead window). Safe to run twice. */
export function generateMissingCharges(plan) {
  const horizon = addDays(MOCK_TODAY, LEAD_DAYS)
  const until = plan.status === 'trial' ? MOCK_TODAY : horizon
  if (['paused', 'cancelled', 'expired'].includes(plan.status)) return
  for (const date of dueDatesBetween(plan, plan.createdOnDate ?? plan.startDate, until)) {
    const id = `ch-${plan.id}-${date}`
    if (db.charges.some((c) => c.id === id)) continue
    db.charges.push({ id, planId: plan.id, periodStart: date, periodEnd: periodEndFor(plan, date), dueDate: date, ...priceAt(plan, date), locked: date <= MOCK_TODAY })
  }
  recalcUnlocked(plan)
}

/**
 * Charges not yet locked (renewal date still ahead) follow the current seats and price.
 * Only dues still at Due are rewritten; Pending and Paid dues are never touched.
 */
export function recalcUnlocked(plan) {
  if (!plan.shared) return
  const members = db.members.filter((m) => m.planId === plan.id)
  for (const charge of chargesOf(plan.id).filter((c) => c.dueDate > MOCK_TODAY)) {
    const shares = splitCharge(plan, members.filter((m) => m.status !== 'left' || isActiveOn(m, charge.periodStart)), charge.amount, charge.periodStart)
    const existing = duesOfCharge(charge.id)
    for (const due of existing) {
      const share = shares.find((s) => s.memberId === due.memberId)
      if (!share && due.status === 'due') db.dues.splice(db.dues.indexOf(due), 1)
      else if (share && due.status === 'due') due.amount = share.amount
      else if (share && memberById(due.memberId).isOwnerSeat && due.status === 'paid') due.amount = share.amount
    }
    for (const share of shares) {
      if (existing.some((d) => d.memberId === share.memberId)) continue
      db.dues.push(newDue(charge, memberById(share.memberId), share.amount))
    }
  }
}

export function setDueStatus(due, status, extra = {}) {
  const before = due.status
  Object.assign(due, { status, ...extra })
  audit({ planId: due.planId, action: 'due_status', entity: due.id, old: before, new: status })
}

export { MOCK_TODAY }
