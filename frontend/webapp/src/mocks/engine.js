import { MOCK_TODAY, addDays, mockNow } from '@/lib/dates'
import { db, ME, LEAD_DAYS, nextId } from './db'
import { billingPeriodsBetween, periodEndFor, priceAt, splitCharge, isActiveOn } from './schedule'
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
    status: 'due', waiverNote: null, rejectionReason: null,
    paidOn: null, recordedByOwner: false, note: null,
  }
}

function syncDuesForCharge(plan, charge) {
  if (!plan.shared) return
  const members = db.members.filter((m) => m.planId === plan.id && (m.status !== 'left' || isActiveOn(m, charge.periodStart)))
  const shares = splitCharge(plan, members, charge.amount, charge.periodStart)
  const existing = duesOfCharge(charge.id)
  for (const share of shares) {
    if (existing.some((d) => d.memberId === share.memberId)) continue
    db.dues.push(newDue(charge, memberById(share.memberId), share.amount))
  }
}

/** Create any charge that should exist (renewal within the lead window). Safe to run twice. */
export function generateMissingCharges(plan) {
  const horizon = addDays(MOCK_TODAY, LEAD_DAYS)
  const until = plan.status === 'trial' ? MOCK_TODAY : horizon
  if (['paused', 'cancelled', 'expired'].includes(plan.status)) return
  const from = plan.billingFrom ?? plan.createdOnDate ?? plan.startDate
  for (const period of billingPeriodsBetween(plan, from, until)) {
    const id = `ch-${plan.id}-${period.periodStart}`
    if (db.charges.some((c) => c.id === id)) continue
    const pricing = priceAt(plan, period.dueDate)
    const charge = {
      id,
      planId: plan.id,
      periodStart: period.periodStart,
      periodEnd: periodEndFor(plan, period.dueDate),
      dueDate: period.dueDate,
      ...pricing,
      locked: period.dueDate <= MOCK_TODAY,
    }
    db.charges.push(charge)
    if (period.periodStart <= MOCK_TODAY && period.dueDate >= MOCK_TODAY) {
      syncDuesForCharge(plan, charge)
    }
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
