import { MOCK_TODAY, addDays, diffDays, monthStart, monthEnd, addMonthsToKey, monthKey, fmtMonth, fmtShort, dhakaDate } from '@/lib/dates'
import { splitExact, sum } from '@/lib/money'
import { db, LEAD_DAYS } from './db'
import { dueDatesBetween, monthlyEquivalent, nextDueDate, priceAt, splitCharge } from './schedule'

// ---------- lookups ----------
export const userById = (id) => db.users.find((u) => u.id === id)
export const firstName = (user) => (user?.name ?? '').split(' ')[0]
export const planById = (id) => db.plans.find((p) => p.id === id && !p.archivedOn)
export const categoryById = (id) => db.categories.find((c) => c.id === id)
export const memberById = (id) => db.members.find((m) => m.id === id)
export const membersOf = (planId, { includeLeft = false } = {}) =>
  db.members.filter((m) => m.planId === planId && (includeLeft || m.status !== 'left'))
export const chargesOf = (planId) => db.charges.filter((c) => c.planId === planId).sort((a, b) => (a.dueDate < b.dueDate ? -1 : 1))
export const duesOfCharge = (chargeId) => db.dues.filter((d) => d.chargeId === chargeId)
export const chargeById = (id) => db.charges.find((c) => c.id === id)
export const dueById = (id) => db.dues.find((d) => d.id === id)
export const paymentById = (id) => db.payments.find((p) => p.id === id)

export const ownedPlans = (userId) => db.plans.filter((p) => p.ownerId === userId && !p.archivedOn)
export const joinedPlans = (userId) =>
  db.plans.filter(
    (p) => p.ownerId !== userId && !p.archivedOn && db.members.some((m) => m.planId === p.id && m.userId === userId && m.status !== 'left'),
  )
export const myMemberRow = (planId, userId) => db.members.find((m) => m.planId === planId && m.userId === userId && m.status !== 'left')

export function visibleCategories(userId) {
  return db.categories.filter((c) => c.ownerId === null || c.ownerId === userId)
}
export function visibleServiceNames(userId) {
  return db.serviceNames.filter((s) => s.ownerId === null || s.ownerId === userId)
}
export function categoryInUse(categoryId) {
  return db.plans.some((p) => p.categoryId === categoryId && !p.archivedOn)
}

// ---------- plan facts ----------
export const latestCharge = (planId) => chargesOf(planId).at(-1) ?? null

/** The cycle the owner is collecting for now: the latest charge whose due date has arrived, else the latest created. */
export function currentCharge(planId) {
  const list = chargesOf(planId)
  const arrived = list.filter((c) => c.dueDate <= MOCK_TODAY)
  return arrived.at(-1) ?? list.at(-1) ?? null
}

export function nextRenewal(plan) {
  if (plan.status === 'trial') return plan.trialEnd
  if (['paused', 'cancelled', 'expired'].includes(plan.status)) return null
  return nextDueDate(plan, MOCK_TODAY)
}

export const priceNow = (plan) => priceAt(plan, nextRenewal(plan) ?? MOCK_TODAY)

export function paymentsForDue(dueId) {
  return db.payments.filter((p) => p.allocations.some((a) => a.dueId === dueId))
}

/** The payment that settled or is waiting on a due (confirmed beats pending beats the rest). */
export function settlingPayment(dueId) {
  const list = paymentsForDue(dueId)
  return list.find((p) => p.review === 'confirmed') ?? list.find((p) => p.review === 'pending') ?? null
}

export function seatShareNow(plan) {
  const members = membersOf(plan.id)
  const price = priceNow(plan)
  const date = nextRenewal(plan) ?? MOCK_TODAY
  const shares = splitCharge(plan, members.map((m) => ({ ...m, joinedOn: '0000-01-01', leftOn: null })), price.amount, date)
  /**
   * "Each seat" in the UI should follow the configured seat count for equal splits — not only
   * people who have joined yet. Otherwise a 5-seat plan with only the owner present shows the
   * full plan price as one person's share (min of one due = total).
   */
  let perSeat = price.amount
  if (!plan.shared) {
    perSeat = shares.length ? Math.min(...shares.map((s) => s.amount)) : price.amount
  } else if (plan.split === 'equal' && plan.seats > 0) {
    const parts = splitExact(price.amount, plan.seats, 0)
    perSeat = Math.min(...parts)
  } else if (shares.length) {
    perSeat = Math.min(...shares.map((s) => s.amount))
  } else if (plan.seats > 0) {
    perSeat = splitExact(price.amount, plan.seats, 0)[0]
  }
  return { shares, perSeat }
}

/** What `userId` personally pays for one cycle of `plan` dated `date`. */
export function myPortion(plan, userId, date) {
  const charge = db.charges.find((c) => c.planId === plan.id && c.dueDate === date)
  const amount = charge ? charge.amount : priceAt(plan, date).amount
  const isOwner = plan.ownerId === userId
  if (isOwner && plan.mode === 'reseller') return 0
  if (!plan.shared) return isOwner ? amount : 0
  const me = db.members.find((m) => m.planId === plan.id && m.userId === userId)
  if (!me) return 0
  if (charge) {
    const due = db.dues.find((d) => d.chargeId === charge.id && d.memberId === me.id)
    if (due) return due.amount
    if (date <= MOCK_TODAY) return 0
  }
  const projected = membersOf(plan.id).map((m) => ({ ...m, leftOn: null }))
  return splitCharge(plan, projected, amount, date).find((s) => s.memberId === me.id)?.amount ?? 0
}

// ---------- events (calendar, next 7 days) ----------
/**
 * Every date that matters to `userId` between `from` and `to`.
 * Owned plans: renewals and trial ends (amount = what the owner pays the provider).
 * Joined plans: dues (amount = my share, status = my due status).
 */
export function eventsBetween(userId, from, to) {
  const events = []
  for (const plan of ownedPlans(userId)) {
    for (const date of dueDatesBetween(plan, plan.startDate, to)) {
      if (date < from) continue
      const isTrialEnd = plan.trialEnd === date
      events.push({
        id: `${plan.id}-${date}`, date, planId: plan.id, planName: plan.planName, serviceKey: plan.serviceKey, role: 'owner',
        kind: isTrialEnd ? 'trial_end' : 'renews', amount: priceAt(plan, date).amount, status: null,
      })
    }
    if (plan.renewal === 'fixed' && plan.endDate >= from && plan.endDate <= to) {
      events.push({ id: `${plan.id}-end`, date: plan.endDate, planId: plan.id, planName: plan.planName, serviceKey: plan.serviceKey, role: 'owner', kind: 'expires', amount: 0, status: null })
    }
  }
  for (const plan of joinedPlans(userId)) {
    const me = myMemberRow(plan.id, userId)
    for (const date of dueDatesBetween(plan, plan.startDate, to)) {
      if (date < from || date < me.joinedOn) continue
      const charge = db.charges.find((c) => c.planId === plan.id && c.dueDate === date)
      const due = charge ? db.dues.find((d) => d.chargeId === charge.id && d.memberId === me.id) : null
      if (charge && !due) continue
      events.push({
        id: `${plan.id}-${date}`, date, planId: plan.id, planName: plan.planName, serviceKey: plan.serviceKey, role: 'member',
        kind: 'due', amount: due ? due.amount : myPortion(plan, userId, date), status: due ? due.status : 'due',
      })
    }
  }
  return events.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.planName.localeCompare(b.planName)))
}

export function nextSevenDays(userId) {
  return eventsBetween(userId, MOCK_TODAY, addDays(MOCK_TODAY, 6))
}

/** Payments the user still has to make in the next 7 days (provider renewals plus open member dues). */
export function dueInSevenDays(userId) {
  const list = nextSevenDays(userId).filter((e) => e.role === 'owner' || e.status === 'due')
  return { count: list.length, total: sum(list, (e) => e.amount), first: list[0]?.date ?? null, items: list }
}

// ---------- spend ----------
export function spendInMonth(userId, key) {
  const from = `${key}-01`
  const to = monthEnd(from)
  const rows = []
  for (const plan of [...ownedPlans(userId), ...joinedPlans(userId)]) {
    const role = plan.ownerId === userId ? 'owner' : 'member'
    for (const date of dueDatesBetween(plan, plan.startDate, to)) {
      if (date < from) continue
      if (role === 'member' && date < myMemberRow(plan.id, userId).joinedOn) continue
      const amount = myPortion(plan, userId, date)
      if (amount > 0) rows.push({ planId: plan.id, plan, role, date, amount, yearly: plan.cycle.unit === 'year' })
    }
  }
  return rows
}

export function monthSpend(userId) {
  const rows = spendInMonth(userId, monthKey(MOCK_TODAY))
  const owned = sum(rows.filter((r) => r.role === 'owner'), (r) => r.amount)
  const joined = sum(rows.filter((r) => r.role === 'member'), (r) => r.amount)
  return { total: owned + joined, owned, joined, rows }
}

export function spendByCategory(userId) {
  const { rows } = monthSpend(userId)
  const map = new Map()
  for (const r of rows) {
    const name = categoryById(r.plan.categoryId)?.name ?? 'Other'
    map.set(name, (map.get(name) ?? 0) + r.amount)
  }
  return [...map.entries()].map(([name, amount]) => ({ name, amount })).sort((a, b) => b.amount - a.amount)
}

export function forecast(userId, months = 6) {
  const start = monthKey(MOCK_TODAY)
  return Array.from({ length: months }, (_, i) => {
    const key = addMonthsToKey(start, i)
    const rows = spendInMonth(userId, key)
    const hasYearly = rows.some((r) => r.yearly)
    return {
      key,
      label: fmtMonth(`${key}-01`).split(' ')[0],
      year: key.slice(0, 4),
      total: sum(rows, (r) => r.amount),
      kind: i === 0 ? 'this' : hasYearly ? 'yearly' : 'regular',
      yearlyPlans: rows.filter((r) => r.yearly).map((r) => r.plan.planName),
    }
  })
}

export function rarelyUsed(userId) {
  const list = ownedPlans(userId).filter((p) => p.rarelyUsed && !['paused', 'cancelled', 'expired'].includes(p.status))
  const yearly = sum(list, (p) => monthlyEquivalent(p, myPortion(p, userId, nextRenewal(p) ?? MOCK_TODAY)) * 12)
  return { plans: list.map((p) => ({ id: p.id, planName: p.planName })), yearly }
}

// ---------- owner views ----------
export function memberView(member, charge) {
  const user = userById(member.userId)
  const due = charge ? db.dues.find((d) => d.chargeId === charge.id && d.memberId === member.id) : null
  const payment = due ? settlingPayment(due.id) : null
  return {
    id: member.id, userId: user.id, name: user.name, firstName: firstName(user), email: user.email, avatarColor: user.avatarColor,
    isOwnerSeat: member.isOwnerSeat, status: member.status, joinedOn: member.joinedOn, leftOn: member.leftOn,
    customShare: member.customShare ?? null,
    leaveRequested: member.status === 'leave_requested', leaveRequestedAt: member.leaveRequestedAt,
    dueId: due?.id ?? null, dueStatus: due?.status ?? null, dueAmount: due?.amount ?? null,
    lastPayment: payment ? { method: payment.method, at: payment.submittedAt, review: payment.review, id: payment.id } : null,
    pendingPaymentId: payment?.review === 'pending' ? payment.id : null,
  }
}

export function ownerPlanStatus(plan, members) {
  if (plan.status === 'trial') return { key: 'trial', label: 'Trial' }
  if (plan.status !== 'active') return { key: plan.status, label: plan.status }
  if (!plan.shared) return { key: 'solo', label: 'Just me' }
  const pending = members.filter((m) => m.dueStatus === 'pending').length
  const due = members.filter((m) => m.dueStatus === 'due').length
  if (pending) return { key: 'review', label: `${pending} to review`, count: pending }
  if (due) return { key: 'due', label: `${due} due`, count: due }
  if (!members.length) return { key: 'empty', label: 'No members yet' }
  return { key: 'allpaid', label: 'All paid' }
}

export function ownerPlanSummary(plan) {
  const charge = currentCharge(plan.id)
  const members = membersOf(plan.id).map((m) => memberView(m, charge))
  const price = priceNow(plan)
  const { perSeat } = seatShareNow(plan)
  const category = categoryById(plan.categoryId)
  return {
    id: plan.id, planName: plan.planName, serviceName: plan.serviceName, serviceKey: plan.serviceKey, mode: plan.mode, status: plan.status,
    cycle: plan.cycle, currency: plan.currency, price, perSeat, seatsCap: plan.seats, seatsTaken: members.length, shared: plan.shared,
    nextRenewal: nextRenewal(plan), trialEnd: plan.trialEnd ?? null, pausedOn: plan.pausedOn ?? null,
    members, statusPill: ownerPlanStatus(plan, members), rarelyUsed: plan.rarelyUsed, method: plan.method, note: plan.note,
    category: category ? { id: category.id, name: category.name } : null,
    pendingCount: members.filter((m) => m.dueStatus === 'pending').length,
    chargeId: charge?.id ?? null, monthly: monthlyEquivalent(plan, price.amount),
  }
}

export function pendingPaymentsFor(planId) {
  return db.payments.filter((p) => p.planId === planId && p.review === 'pending')
}

export function ownerTotals(userId) {
  const plans = ownedPlans(userId)
  const running = plans.filter((p) => ['active', 'trial'].includes(p.status))
  let confirmed = 0
  let pending = 0
  let expected = 0
  for (const plan of plans.filter((p) => p.shared)) {
    const charge = currentCharge(plan.id)
    if (!charge) continue
    const memberDues = duesOfCharge(charge.id).filter((d) => !memberById(d.memberId).isOwnerSeat)
    expected += sum(memberDues, (d) => d.amount)
    confirmed += sum(memberDues.filter((d) => d.status === 'paid'), (d) => d.amount)
    pending += sum(memberDues.filter((d) => d.status === 'pending'), (d) => d.amount)
  }
  const reviewPlans = plans.filter((p) => pendingPaymentsFor(p.id).length)
  return {
    count: plans.length,
    toProviders: sum(running, (p) => monthlyEquivalent(p, priceNow(p).amount)),
    confirmed, pending, expected,
    reviewCount: sum(plans, (p) => pendingPaymentsFor(p.id).length),
    reviewPlans: reviewPlans.map((p) => p.planName),
    rarelyCount: plans.filter((p) => p.rarelyUsed).length,
  }
}

export function planActivity(planId) {
  const items = []
  const name = (memberId) => firstName(userById(memberById(memberId)?.userId))
  for (const p of db.payments.filter((x) => x.planId === planId)) {
    const who = name(p.payerMemberId)
    if (p.recordedBy !== userById(memberById(p.payerMemberId).userId).id) {
      items.push({ id: `${p.id}-owner`, ts: p.reviewedAt ?? p.submittedAt, tone: 'paid', text: `You marked ${who}'s due as Paid (recorded by owner)`, amount: p.amount })
      continue
    }
    items.push({ id: `${p.id}-sent`, ts: p.submittedAt, tone: 'pending', text: `${who} sent a transaction ID`, amount: p.amount })
    if (p.review === 'confirmed') items.push({ id: `${p.id}-ok`, ts: p.reviewedAt, tone: 'paid', text: `Confirmed ${who}'s payment`, amount: p.amount })
    if (p.review === 'rejected') items.push({ id: `${p.id}-no`, ts: p.reviewedAt, tone: 'due', text: `Rejected ${who}'s ID`, amount: p.amount })
    if (p.review === 'reversed') items.push({ id: `${p.id}-rev`, ts: p.reviewedAt, tone: 'due', text: `Reversed ${who}'s payment`, amount: p.amount })
  }
  for (const m of db.members.filter((x) => x.planId === planId)) {
    const who = firstName(userById(m.userId))
    if (m.leaveRequestedAt) items.push({ id: `${m.id}-leave`, ts: m.leaveRequestedAt, tone: 'due', text: `${who} asked to leave` })
    if (m.leftOn) items.push({ id: `${m.id}-left`, ts: `${m.leftOn}T18:00:00+06:00`, tone: 'due', text: `${who} left the plan` })
  }
  for (const a of db.audit.filter((x) => x.planId === planId && x.text)) {
    items.push({ id: a.id, ts: a.ts, tone: a.tone ?? 'info', text: a.text, amount: a.amount })
  }
  return items.sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 10)
}

export function planIous(planId) {
  const pairs = new Map()
  for (const p of db.payments.filter((x) => x.planId === planId && x.review === 'confirmed')) {
    for (const a of p.allocations) {
      const due = dueById(a.dueId)
      if (!due || due.memberId === p.payerMemberId) continue
      const debtor = memberById(due.memberId).userId
      const creditor = memberById(p.payerMemberId).userId
      const key = [debtor, creditor].sort().join('|')
      const sign = debtor < creditor ? 1 : -1
      pairs.set(key, (pairs.get(key) ?? 0) + sign * a.amount)
    }
  }
  const out = []
  for (const [key, value] of pairs) {
    if (value === 0) continue
    const [a, b] = key.split('|')
    const [debtor, creditor] = value > 0 ? [a, b] : [b, a]
    out.push({ debtorId: debtor, creditorId: creditor, debtor: firstName(userById(debtor)), creditor: firstName(userById(creditor)), amount: Math.abs(value) })
  }
  return out
}

/** One row per due on the plan: who paid me and when. */
export function planLedger(planId) {
  const rows = []
  for (const charge of chargesOf(planId)) {
    for (const due of duesOfCharge(charge.id)) {
      const member = memberById(due.memberId)
      const user = userById(member.userId)
      const payment = settlingPayment(due.id)
      rows.push({
        id: due.id, chargeId: charge.id, month: monthKey(charge.dueDate), monthLabel: fmtMonth(charge.dueDate), dueDate: charge.dueDate,
        memberId: member.id, name: user.name, firstName: firstName(user), isOwnerSeat: member.isOwnerSeat,
        amount: due.amount, status: due.status, method: payment?.method ?? null, tid: payment?.tid ?? null,
        paidOn: payment?.reviewedAt ? dhakaDate(payment.reviewedAt) : due.paidOn, recordedByOwner: due.recordedByOwner,
        coveredBy: payment && payment.payerMemberId !== member.id ? firstName(userById(memberById(payment.payerMemberId).userId)) : null,
      })
    }
  }
  return rows.sort((a, b) => (a.dueDate < b.dueDate ? 1 : a.dueDate > b.dueDate ? -1 : a.name.localeCompare(b.name)))
}

export function ownerChargeRows(planId) {
  return chargesOf(planId)
    .slice()
    .reverse()
    .map((c) => ({
      ...c,
      monthLabel: fmtMonth(c.dueDate),
      hasPayments: duesOfCharge(c.id).some((d) => paymentsForDue(d.id).some((p) => !memberById(p.payerMemberId).isOwnerSeat)),
    }))
}

export function memberDetail(memberId) {
  const member = memberById(memberId)
  const plan = planById(member.planId)
  const charge = currentCharge(plan.id)
  const view = memberView(member, charge)
  const rows = db.dues
    .filter((d) => d.memberId === memberId)
    .map((d) => {
      const c = chargeById(d.chargeId)
      const p = settlingPayment(d.id)
      return { id: d.id, dueDate: c.dueDate, monthLabel: fmtMonth(c.dueDate), amount: d.amount, status: d.status, method: p?.method ?? null, tid: p?.tid ?? null, paymentId: p?.id ?? null }
    })
    .sort((a, b) => (a.dueDate < b.dueDate ? 1 : -1))
    .slice(0, 5)
  return { ...view, planId: plan.id, planName: plan.planName, rows }
}

export function reviewData(planId) {
  const plan = planById(planId)
  const charge = currentCharge(planId)
  const all = duesOfCharge(charge?.id ?? '')
  const memberDues = all.filter((d) => !memberById(d.memberId).isOwnerSeat)
  const pending = pendingPaymentsFor(planId).map((p) => {
    const payer = memberById(p.payerMemberId)
    const user = userById(payer.userId)
    const covers = p.allocations.map((a) => {
      const due = dueById(a.dueId)
      const m = memberById(due.memberId)
      const c = chargeById(due.chargeId)
      return { dueId: due.id, name: firstName(userById(m.userId)), self: m.id === payer.id, amount: a.amount, monthLong: fmtMonth(c.dueDate) }
    })
    return {
      id: p.id, memberId: payer.id, name: user.name, firstName: firstName(user), email: user.email, avatarColor: user.avatarColor,
      amount: p.amount, method: p.method, tid: p.tid, submittedAt: p.submittedAt, leaveRequested: payer.status === 'leave_requested',
      covers, cycleLabel: covers.map((c) => c.monthLong).filter((v, i, arr) => arr.indexOf(v) === i).join(', '),
    }
  })
  const decided = all
    .filter((d) => ['paid', 'waived'].includes(d.status))
    .map((d) => {
      const m = memberById(d.memberId)
      const u = userById(m.userId)
      const p = settlingPayment(d.id)
      return {
        id: d.id, name: u.name, firstName: firstName(u), avatarColor: u.avatarColor, isOwnerSeat: m.isOwnerSeat, amount: d.amount,
        status: d.status, method: p?.method ?? null, tid: p?.tid ?? null, decidedOn: p?.reviewedAt ? dhakaDate(p.reviewedAt) : d.paidOn,
        paymentId: p?.id ?? null, waiverNote: d.waiverNote, recordedByOwner: d.recordedByOwner,
      }
    })
  return {
    plan: { id: plan.id, planName: plan.planName, serviceKey: plan.serviceKey, mode: plan.mode, nextRenewal: nextRenewal(plan) },
    cycleLabel: charge ? fmtMonth(charge.dueDate) : null,
    chargeDueDate: charge?.dueDate ?? null,
    waiting: { count: pending.length, total: sum(pending, (p) => p.amount) },
    confirmed: { amount: sum(memberDues.filter((d) => d.status === 'paid'), (d) => d.amount), expected: sum(memberDues, (d) => d.amount), members: memberDues.length },
    stillDue: memberDues.filter((d) => d.status === 'due').length,
    pending, decided,
  }
}

export function ownerPlanDetail(planId) {
  const plan = planById(planId)
  if (!plan) return null
  const summary = ownerPlanSummary(plan)
  const charge = currentCharge(planId)
  const left = db.members.filter((m) => m.planId === planId && m.status === 'left').map((m) => memberView(m, null))
  const chargeDues = charge ? duesOfCharge(charge.id) : []
  const category = categoryById(plan.categoryId)
  const invites = db.invites
    .filter((i) => i.planId === planId && i.invitedBy === plan.ownerId)
    .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
    .map((i) => ({
      ...i,
      customSharePaisa: i.customShare ?? null,
    }))
  return {
    ...summary,
    startDate: plan.startDate, renewal: plan.renewal, endDate: plan.endDate ?? null, split: plan.split,
    categoryId: plan.categoryId, categoryName: category?.name ?? '—',
    prices: [...plan.prices].sort((a, b) => (a.effectiveFrom < b.effectiveFrom ? 1 : -1)),
    leftMembers: left,
    confirmedSoFar: {
      paid: sum(chargeDues.filter((d) => d.status === 'paid'), (d) => d.amount),
      waived: sum(chargeDues.filter((d) => d.status === 'waived'), (d) => d.amount),
      pending: sum(chargeDues.filter((d) => d.status === 'pending'), (d) => d.amount),
      total: charge?.amount ?? 0,
    },
    cycleLabel: charge ? fmtMonth(charge.dueDate) : null,
    activity: planActivity(planId),
    ious: planIous(planId),
    invites,
    charges: ownerChargeRows(planId),
    transfer: db.transfers.find((t) => t.planId === planId && t.status === 'pending') ?? null,
  }
}

// ---------- member views ----------
export function memberPlanSummary(plan, userId) {
  const me = myMemberRow(plan.id, userId)
  const owner = userById(plan.ownerId)
  const myDues = db.dues
    .filter((d) => d.memberId === me.id)
    .map((d) => ({ ...d, charge: chargeById(d.chargeId) }))
    .sort((a, b) => (a.charge.dueDate < b.charge.dueDate ? 1 : -1))
  const latest = myDues[0] ?? null
  const openDues = myDues.filter((d) => d.status === 'due').map((d) => ({ id: d.id, amount: d.amount, dueDate: d.charge.dueDate, monthLabel: fmtMonth(d.charge.dueDate) }))
  const history = myDues.map((d) => {
    const p = settlingPayment(d.id)
    const rejected = paymentsForDue(d.id).find((x) => x.review === 'rejected')
    return {
      id: d.id, dueDate: d.charge.dueDate, monthLabel: fmtMonth(d.charge.dueDate), amount: d.amount, status: d.status,
      method: p?.method ?? null, tid: p?.tid ?? null, waiverNote: d.waiverNote,
      rejectionReason: d.status === 'due' && d.rejectionReason ? d.rejectionReason : null,
      wasRejected: Boolean(rejected),
    }
  })
  const others = membersOf(plan.id)
    .filter((m) => m.id !== me.id)
    .map((m) => {
      const u = userById(m.userId)
      return { id: m.id, name: u.name, firstName: firstName(u), avatarColor: u.avatarColor, isOwner: m.isOwnerSeat }
    })
  const meUser = userById(userId)
  const myStatus = latest?.status ?? 'due'
  const share = latest?.amount ?? myPortion(plan, userId, nextRenewal(plan) ?? MOCK_TODAY)
  const ious = planIous(plan.id).filter((i) => i.debtorId === userId || i.creditorId === userId)
  const pendingPayment = db.payments.find((p) => p.planId === plan.id && p.review === 'pending' && p.payerMemberId === me.id)
  return {
    id: plan.id, planName: plan.planName, serviceKey: plan.serviceKey, serviceName: plan.serviceName, cycle: plan.cycle,
    owner: { name: owner.name, firstName: firstName(owner), avatarColor: owner.avatarColor },
    myShare: share, myStatus, nextRenewal: nextRenewal(plan), method: plan.method, note: plan.note,
    price: priceNow(plan), seats: membersOf(plan.id).length,
    me: { memberId: me.id, name: meUser.name, firstName: firstName(meUser), avatarColor: meUser.avatarColor, leaveRequested: me.status === 'leave_requested', leaveRequestedAt: me.leaveRequestedAt },
    members: [
      ...others.filter((o) => o.isOwner),
      { id: me.id, name: meUser.name, firstName: 'You', avatarColor: meUser.avatarColor, isOwner: false, isYou: true, status: myStatus },
      ...others.filter((o) => !o.isOwner),
    ],
    openDues, history,
    totalSpent: sum(myDues.filter((d) => d.status === 'paid'), (d) => d.amount),
    earliestOpenDue: openDues.at(-1)?.dueDate ?? null,
    pendingAmount: sum(myDues.filter((d) => d.status === 'pending'), (d) => d.amount),
    pendingSince: pendingPayment?.submittedAt ?? null,
    lastRejection: myDues.find((d) => d.status === 'due' && d.rejectionReason)?.rejectionReason ?? null,
    ious: ious.map((i) => ({
      text: i.debtorId === userId ? `You owe ${i.creditor} ` : `${i.debtor} owes you `,
      amount: i.amount, youOwe: i.debtorId === userId,
    })),
  }
}

/** Dues of other members the payer may cover (creates an IOU). Names and amounts only. */
export function coverableDues(planId, userId) {
  const plan = planById(planId)
  if (plan.mode === 'reseller') return []
  const me = myMemberRow(planId, userId)
  return db.dues
    .filter((d) => d.planId === planId && d.memberId !== me.id && d.status === 'due')
    .map((d) => {
      const m = memberById(d.memberId)
      return { id: d.id, name: firstName(userById(m.userId)), amount: d.amount, monthLabel: fmtMonth(chargeById(d.chargeId).dueDate) }
    })
}

export function sharedTotals(userId) {
  const plans = joinedPlans(userId).map((p) => memberPlanSummary(p, userId))
  const key = monthKey(MOCK_TODAY)
  const rows = spendInMonth(userId, key).filter((r) => r.role === 'member')
  const dueList = plans.filter((p) => p.openDues.length)
  const pendingList = plans.filter((p) => p.pendingAmount > 0)
  return {
    shares: sum(rows, (r) => r.amount), planCount: plans.length,
    dueNow: sum(dueList, (p) => sum(p.openDues, (d) => d.amount)),
    dueNames: dueList.map((p) => p.planName), dueBy: dueList.map((p) => p.earliestOpenDue).sort()[0] ?? null,
    waiting: sum(pendingList, (p) => p.pendingAmount), waitingNames: pendingList.map((p) => p.planName),
    dueCount: dueList.length, pendingCount: pendingList.length,
    paidUpCount: plans.filter((p) => !p.openDues.length && !p.pendingAmount).length,
  }
}

// ---------- attention, notifications, profile ----------
export function needsAttention(userId) {
  const items = []
  for (const plan of ownedPlans(userId)) {
    const pending = pendingPaymentsFor(plan.id)
    if (pending.length) items.push({ id: `review-${plan.id}`, kind: 'review', planId: plan.id, planName: plan.planName, count: pending.length })
    for (const m of membersOf(plan.id).filter((x) => x.status === 'leave_requested')) {
      items.push({ id: `leave-${m.id}`, kind: 'leave', planId: plan.id, planName: plan.planName, memberId: m.id, name: firstName(userById(m.userId)) })
    }
  }
  const me = userById(userId)
  for (const inv of db.invites.filter((i) => i.email === me.email && i.status === 'pending')) {
    const plan = planById(inv.planId)
    items.push({ id: `invite-${inv.id}`, kind: 'invite', inviteId: inv.id, planName: plan.planName, from: firstName(userById(inv.invitedBy)) })
  }
  for (const t of db.transfers.filter((x) => x.toUserId === userId && x.status === 'pending')) {
    const plan = planById(t.planId)
    items.push({ id: `transfer-${t.id}`, kind: 'transfer', transferId: t.id, planName: plan.planName, from: firstName(userById(t.fromUserId)) })
  }
  return items
}

export function inviteView(invite) {
  const plan = planById(invite.planId)
  const members = membersOf(plan.id)
  const price = priceNow(plan)
  const shares = splitCharge(plan, [...members, { id: 'new', joinedOn: '0000-01-01', leftOn: null, isOwnerSeat: false }].map((m) => ({ ...m, joinedOn: '0000-01-01' })), price.amount, MOCK_TODAY)
  return {
    id: invite.id, token: invite.token, email: invite.email, status: invite.status, expiresOn: invite.expiresOn,
    expired: invite.expiresOn < MOCK_TODAY,
    planId: plan.id, planName: plan.planName, serviceKey: plan.serviceKey, seats: plan.seats,
    from: firstName(userById(invite.invitedBy)), share: shares.find((s) => s.memberId === 'new')?.amount ?? price.amount,
    cycle: plan.cycle,
  }
}

export function notificationGroup(kind) {
  if (kind.startsWith('payment')) return 'payments'
  if (['due_soon', 'renewal', 'trial_end', 'expiry'].includes(kind)) return 'reminders'
  if (['invite', 'invite_accepted', 'invite_declined', 'leave_request', 'leave_result', 'transfer', 'transfer_result', 'plan_deleted', 'price_change', 'amount_changed'].includes(kind)) return 'plans'
  return 'account'
}

export function notificationsFor(userId) {
  return db.notifications
    .filter((n) => n.userId === userId)
    .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
    .map((n) => ({ ...n, group: notificationGroup(n.kind), needsAction: Boolean(n.action) && !n.resolved }))
}

export function navCounts(userId) {
  // Match My Plans (`ownerPlanSummary.pendingCount`) and Shared (`sharedTotals.dueCount`) so badges track the same work as those screens.
  const reviews = sum(ownedPlans(userId), (p) => ownerPlanSummary(p).pendingCount)
  const dues = sharedTotals(userId).dueCount
  const unread = db.notifications.filter((n) => n.userId === userId && !n.readAt).length
  return { reviews, dues, unread }
}

export function profileCounts(userId) {
  return { owned: ownedPlans(userId).length, joined: joinedPlans(userId).length }
}

export { MOCK_TODAY, LEAD_DAYS, diffDays, fmtShort, monthStart }
