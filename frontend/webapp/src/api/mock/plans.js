import { db, ME, nextId } from '@/mocks/db'
import {
  ownedPlans, ownerPlanSummary, ownerPlanDetail, ownerTotals, planById, planLedger, reviewData, memberDetail,
  memberById, userById, firstName, membersOf, chargeById, duesOfCharge, paymentsForDue, nextRenewal,
} from '@/mocks/selectors'
import { audit, generateMissingCharges, recalcUnlocked, resolveNotifications } from '@/mocks/engine'
import { cycleFromForm, dueDatesBetween, nextDueDate } from '@/mocks/schedule'
import { MOCK_TODAY, addDays, mockNow, fmtShort, dayOfMonth } from '@/lib/dates'
import { formatBDT, splitExact, usdToPaisa } from '@/lib/money'
import { checkPassword } from '../accounts'
import { ApiError, paginate, read, write } from '../client'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const INVITE_DAYS = 7

function ownedOr404(id) {
  const plan = planById(id)
  if (!plan || plan.ownerId !== ME) throw new ApiError('Plan not found.', { status: 404 })
  return plan
}

// ---------- reads ----------
export function getSubscriptions({ search = '', filter = 'all', page = 1, size = 5 } = {}) {
  return read(
    () => {
      const all = ownedPlans(ME).map(ownerPlanSummary)
      const q = search.trim().toLowerCase()
      const matched = all.filter((p) => !q || p.planName.toLowerCase().includes(q) || p.serviceName.toLowerCase().includes(q))
      const counts = {
        all: matched.length,
        review: matched.filter((p) => p.pendingCount > 0).length,
        rarely: matched.filter((p) => p.rarelyUsed).length,
      }
      const filtered = matched.filter((p) => (filter === 'review' ? p.pendingCount > 0 : filter === 'rarely' ? p.rarelyUsed : true))
      return { ...paginate(filtered, page, size), counts, totals: ownerTotals(ME) }
    },
    { empty: (v) => ({ ...v, items: [], total: 0, pages: 1, counts: { all: 0, review: 0, rarely: 0 }, totals: { ...v.totals, count: 0, toProviders: 0, confirmed: 0, pending: 0, expected: 0, reviewCount: 0, reviewPlans: [] } }) },
  )
}

export function getSubscription(id) {
  return read(() => {
    const plan = planById(id)
    if (!plan || plan.ownerId !== ME) return { notFound: true }
    return ownerPlanDetail(id)
  })
}

export function getPlanForm(id) {
  return read(() => {
    const plan = ownedOr404(id)
    const price = plan.prices.at(-1)
    const invites = db.invites.filter((i) => i.planId === id && i.status === 'pending').map((i) => i.email)
    return { ...plan, priceNow: price, pendingInvites: invites, memberCount: membersOf(id).length }
  })
}

export function getReview(planId) {
  return read(() => {
    ownedOr404(planId)
    return reviewData(planId)
  }, { empty: (v) => ({ ...v, pending: [], waiting: { count: 0, total: 0 } }) })
}

export function getMember(memberId) {
  return read(() => {
    const m = memberById(memberId)
    ownedOr404(m.planId)
    return memberDetail(memberId)
  })
}

export function getLedger(planId, { member = 'all', month = 'all', status = 'all', page = 1, size = 8 } = {}) {
  return read(
    () => {
      ownedOr404(planId)
      const rows = planLedger(planId)
      const filtered = rows.filter(
        (r) => (member === 'all' || r.memberId === member) && (month === 'all' || r.month === month) && (status === 'all' || r.status === status),
      )
      const totals = {
        paid: filtered.filter((r) => r.status === 'paid').reduce((a, r) => a + r.amount, 0),
        pending: filtered.filter((r) => r.status === 'pending').reduce((a, r) => a + r.amount, 0),
        due: filtered.filter((r) => r.status === 'due').reduce((a, r) => a + r.amount, 0),
        all: filtered.reduce((a, r) => a + r.amount, 0),
      }
      const months = [...new Set(rows.map((r) => r.month))].map((m) => ({ key: m, label: rows.find((r) => r.month === m).monthLabel }))
      const people = [...new Map(rows.map((r) => [r.memberId, { id: r.memberId, name: r.firstName }])).values()]
      return { ...paginate(filtered, page, size), totals, months, people }
    },
    { empty: (v) => ({ ...v, items: [], total: 0, pages: 1 }) },
  )
}

// ---------- create and edit ----------
function validatePlanForm(form, { editing = false } = {}) {
  const fields = {}
  if (!form.serviceName?.trim()) fields.serviceName = 'Pick or type a service name.'
  if (!form.planName?.trim()) fields.planName = 'Give the plan a name, for example "Netflix Premium".'
  if (!form.categoryId) fields.categoryId = 'Pick a category.'
  if (!editing) {
    if (!(form.price > 0)) fields.price = 'Enter the price you pay, more than 0.'
    if (form.currency === 'USD' && !(form.rate > 0)) fields.rate = 'Enter the rate you are paying, for example 122.'
    if (!form.startDate) fields.startDate = 'Pick the start date.'
  }
  if (form.cycleUnit === 'custom' && form.renewal !== 'fixed') {
    if (!form.nextRenewalDate) fields.nextRenewalDate = 'Pick the next renewal date.'
    else if ((form.trialEnd || form.startDate) && form.nextRenewalDate <= (form.trialEnd || form.startDate)) {
      fields.nextRenewalDate = 'Next renewal must be after the start date.'
    }
  }
  if (form.trialEnd && form.startDate && form.trialEnd < form.startDate) fields.trialEnd = 'The trial cannot end before the plan starts.'
  if (form.renewal === 'fixed' && !form.endDate) fields.endDate = 'Pick the date the plan ends.'
  if (form.renewal === 'fixed' && form.endDate && form.startDate && form.endDate <= form.startDate) fields.endDate = 'The end date must be after the start date.'
  if (!(form.seats >= 1)) fields.seats = form.mode === 'reseller' ? 'Enter how many buyers, 1 or more.' : 'Enter how many seats, 1 or more.'
  if (form.seats > 20) fields.seats = 'Up to 20 seats per plan.'
  const bad = (form.invites ?? []).find((e) => !EMAIL_RE.test(e))
  if (bad) fields.invites = `"${bad}" is not an email address.`
  if ((form.invites ?? []).length > form.seats - (form.mode === 'owner' ? 1 : 0) + (editing ? 0 : 0)) {
    fields.invites = 'There are more invites than free seats. Add seats or remove an email.'
  }
  if (Object.keys(fields).length) throw new ApiError('Some answers need a fix.', { fields })
}

const cycleOf = cycleFromForm

/** Align anchor day and skip dates so the next due on or after today is `nextRenewalDate`. */
function scheduleFromForm(form, existingSkip = []) {
  const firstBill = form.trialEnd || form.startDate
  let anchorDay = dayOfMonth(firstBill)
  const target = form.nextRenewalDate?.trim()
  if (!target) return { anchorDay, skipDates: [...existingSkip] }

  anchorDay = dayOfMonth(target)
  const added = []
  /** Omit fixed `endDate` here: `stopDate` would cut the series before `target`, so alignment can never succeed when target equals the form end date. */
  const probe = () => ({
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    cycle: cycleOf(form),
    skipDates: [...existingSkip, ...added],
    anchorDay,
    renewal: form.renewal,
    endDate: null,
    pausedOn: null,
    cancelledOn: null,
  })

  let next = nextDueDate(probe(), MOCK_TODAY)
  while (next && next < target) {
    added.push(next)
    next = nextDueDate(probe(), MOCK_TODAY)
  }
  if (next !== target) {
    throw new ApiError('Some answers need a fix.', {
      fields: { nextRenewalDate: 'That date does not match this billing cycle from the start date. Pick a valid renewal date or change the cycle.' },
    })
  }
  return { anchorDay, skipDates: [...existingSkip, ...added] }
}

export function createSubscription(form) {
  return write(() => {
    validatePlanForm(form)
    const id = nextId('p')
    const catalogItem = db.serviceNames.find((s) => s.name.toLowerCase() === form.serviceName.trim().toLowerCase())
    if (!catalogItem) {
      db.serviceNames.push({ id: nextId('s'), name: form.serviceName.trim(), serviceKey: null, categoryId: form.categoryId, ownerId: ME })
    }
    const pricePoint = form.currency === 'USD'
      ? { usdCents: Math.round(form.price * 100), rate: Math.round(form.rate * 100), effectiveFrom: form.startDate }
      : { amount: Math.round(form.price * 100), effectiveFrom: form.startDate }
    const shared = form.mode === 'reseller' || form.seats > 1 || (form.invites ?? []).length > 0
    const { anchorDay, skipDates } = scheduleFromForm(form)
    const plan = {
      id, ownerId: ME, serviceKey: catalogItem?.serviceKey ?? null, serviceName: form.serviceName.trim(), planName: form.planName.trim(),
      mode: form.mode, categoryId: form.categoryId, currency: form.currency, cycle: cycleOf(form), startDate: form.startDate,
      anchorDay, skipDates, trialEnd: form.trialEnd || null, renewal: form.renewal, endDate: form.renewal === 'fixed' ? form.endDate : null,
      status: form.trialEnd && form.trialEnd > MOCK_TODAY ? 'trial' : 'active', method: form.method, note: (form.note ?? '').trim(),
      rarelyUsed: false, seats: Number(form.seats), split: 'equal', shared, prices: [pricePoint], createdAt: mockNow(), createdOnDate: MOCK_TODAY,
    }
    db.plans.push(plan)
    if (shared && form.mode === 'owner') {
      db.members.push({
        id: nextId('m'), planId: id, userId: ME, joinedOn: MOCK_TODAY, status: 'active', leftOn: null, leaveRequestedAt: null,
        isOwnerSeat: true, prefMethod: form.method, customShare: undefined,
      })
    }
    for (const email of form.invites ?? []) {
      db.invites.push({
        id: nextId('inv'), planId: id, email, status: 'pending', invitedBy: ME, createdAt: mockNow(), expiresOn: addDays(MOCK_TODAY, INVITE_DAYS),
        acceptedBy: null, token: nextId('tok'), customShare: undefined,
      })
    }
    generateMissingCharges(plan)
    audit({ planId: id, action: 'plan_created', text: `You created ${plan.planName}` })
    return { id }
  })
}

export function updateSubscription(id, form) {
  return write(() => {
    const plan = ownedOr404(id)
    validatePlanForm({ ...form, mode: plan.mode }, { editing: true })
    const taken = membersOf(id).length
    if (Number(form.seats) < taken) throw new ApiError('Fewer seats than members.', { fields: { seats: `${taken} people are in this plan, so it needs at least ${taken} seats.` } })
    const { anchorDay, skipDates } = scheduleFromForm(form, plan.skipDates ?? [])
    Object.assign(plan, {
      planName: form.planName.trim(), serviceName: form.serviceName.trim(), categoryId: form.categoryId, method: form.method,
      note: (form.note ?? '').trim(), seats: Number(form.seats), renewal: form.renewal, endDate: form.renewal === 'fixed' ? form.endDate : null,
      anchorDay, skipDates,
      shared: plan.shared || plan.mode === 'reseller' || Number(form.seats) > 1,
    })
    audit({ planId: id, action: 'plan_edited', text: 'You edited the plan details' })
    recalcUnlocked(plan)
    return { id }
  })
}

// ---------- lifecycle ----------
export function pausePlan(id) {
  return write(() => {
    const plan = ownedOr404(id)
    plan.status = 'paused'
    plan.pausedOn = MOCK_TODAY
    db.charges = db.charges.filter((c) => !(c.planId === id && c.dueDate > MOCK_TODAY && duesOfCharge(c.id).every((d) => d.status === 'due' || memberById(d.memberId).isOwnerSeat)))
    db.dues = db.dues.filter((d) => db.charges.some((c) => c.id === d.chargeId))
    audit({ planId: id, action: 'paused', text: 'You paused the plan. No new charges until you resume.' })
  })
}

export function resumePlan(id) {
  return write(() => {
    const plan = ownedOr404(id)
    const missed = dueDatesBetween({ ...plan, pausedOn: null }, plan.pausedOn ?? MOCK_TODAY, MOCK_TODAY)
    plan.skipDates = [...(plan.skipDates ?? []), ...missed.filter((d) => d < MOCK_TODAY)]
    plan.status = 'active'
    plan.pausedOn = null
    generateMissingCharges(plan)
    audit({ planId: id, action: 'resumed', text: `You resumed the plan. Next renewal ${fmtShort(nextDueDate(plan, MOCK_TODAY) ?? MOCK_TODAY)}.` })
  })
}

export function cancelPlan(id) {
  return write(() => {
    const plan = ownedOr404(id)
    const until = nextRenewal(plan) ?? MOCK_TODAY
    plan.status = 'cancelled'
    plan.cancelledOn = until
    audit({ planId: id, action: 'cancelled', text: `You cancelled the plan. It ends on ${fmtShort(until)}, the end of the paid period.` })
  })
}

export function renewPlan(id, { endDate }) {
  return write(() => {
    const plan = ownedOr404(id)
    if (!endDate || endDate <= MOCK_TODAY) throw new ApiError('Pick a new end date after today.', { fields: { endDate: 'Pick a new end date after today.' } })
    plan.endDate = endDate
    plan.status = 'active'
    generateMissingCharges(plan)
    audit({ planId: id, action: 'renewed', text: `You renewed the plan until ${fmtShort(endDate)}` })
  })
}

export function setRarelyUsed(id, value) {
  return write(() => {
    const plan = ownedOr404(id)
    plan.rarelyUsed = Boolean(value)
  })
}

/** Equal: clear custom shares. Custom: set each active member’s `customShare` (paisa); amounts must sum to the current charge price. */
export function updatePlanSplit(planId, { split, shares = {} }) {
  return write(() => {
    const plan = ownedOr404(planId)
    const fields = {}
    if (plan.mode === 'reseller') throw new ApiError('Reseller plans use one price per buyer; there is no shared split.', { status: 400 })
    if (!plan.shared) throw new ApiError('This plan is solo. Add seats or members to set a split.', { status: 400 })
    if (split !== 'equal' && split !== 'custom') throw new ApiError('Pick Equal or Custom.', { fields: { split: 'Pick Equal or Custom.' } })
    const active = membersOf(planId).filter((m) => m.status === 'active')
    if (!active.length) throw new ApiError('No active members on this plan.', { status: 400 })
    const price = plan.prices.at(-1)
    const chargeAmount = plan.currency === 'USD' ? usdToPaisa(price.usdCents, price.rate) : price.amount

    if (split === 'equal') {
      plan.split = 'equal'
      for (const m of active) {
        delete m.customShare
      }
      for (const inv of db.invites.filter((i) => i.planId === planId && i.status === 'pending')) {
        delete inv.customShare
      }
      recalcUnlocked(plan)
      audit({ planId, action: 'split_equal', text: 'Seat split set to equal shares' })
      return
    }

    let total = 0
    for (const m of active) {
      const raw = shares[m.id]
      const paisa = typeof raw === 'number' && Number.isFinite(raw) ? Math.round(raw) : Math.round(Number(String(raw ?? '').replace(/,/g, '')) * 100)
      if (!(paisa > 0)) fields[m.id] = 'Enter an amount greater than 0.'
      else total += paisa
    }
    if (total !== chargeAmount) {
      fields._total = `Amounts must add up to ${formatBDT(chargeAmount)} (current plan price).`
    }
    if (Object.keys(fields).length) throw new ApiError('Fix the seat amounts.', { fields })

    plan.split = 'custom'
    for (const m of active) {
      const raw = shares[m.id]
      m.customShare = typeof raw === 'number' && Number.isFinite(raw) ? Math.round(raw) : Math.round(Number(String(raw ?? '').replace(/,/g, '')) * 100)
    }
    for (const inv of db.invites.filter((i) => i.planId === planId && i.status === 'pending')) {
      delete inv.customShare
    }
    recalcUnlocked(plan)
    audit({ planId, action: 'split_custom', text: 'Custom seat shares updated' })
  })
}

export function deletePlan(id, { password }) {
  return write(() => {
    const plan = ownedOr404(id)
    checkPassword(password)
    const confirmed = db.payments.some((p) => p.planId === id && p.review === 'confirmed' && !memberById(p.payerMemberId)?.isOwnerSeat)
    if (confirmed) {
      plan.archivedOn = MOCK_TODAY
      audit({ planId: id, action: 'archived' })
      return { archived: true }
    }
    const keep = (list) => list.filter((x) => x.planId !== id)
    db.plans = db.plans.filter((p) => p.id !== id)
    db.members = keep(db.members)
    db.charges = keep(db.charges)
    db.dues = keep(db.dues)
    db.payments = keep(db.payments)
    db.invites = keep(db.invites)
    audit({ action: 'erased', entity: id })
    return { archived: false }
  })
}

export function addPriceChange(id, { amount, usd, rate, effectiveFrom }) {
  return write(() => {
    const plan = ownedOr404(id)
    const fields = {}
    if (!effectiveFrom) fields.effectiveFrom = 'Pick the date the new price starts.'
    else if (effectiveFrom < MOCK_TODAY) fields.effectiveFrom = 'Pick today or a later date. Old charges keep the old price.'
    if (plan.currency === 'USD') {
      if (!(usd > 0)) fields.usd = 'Enter the new dollar price.'
      if (!(rate > 0)) fields.rate = 'Enter the rate.'
    } else if (!(amount > 0)) fields.amount = 'Enter the new price.'
    if (Object.keys(fields).length) throw new ApiError('Check the price change.', { fields })
    const point = plan.currency === 'USD'
      ? { usdCents: Math.round(usd * 100), rate: Math.round(rate * 100), effectiveFrom }
      : { amount: Math.round(amount * 100), effectiveFrom }
    plan.prices = [...plan.prices.filter((p) => p.effectiveFrom !== effectiveFrom), point]
    for (const charge of db.charges.filter((c) => c.planId === id && c.dueDate >= effectiveFrom && c.dueDate > MOCK_TODAY)) {
      charge.amount = plan.currency === 'USD' ? usdToPaisa(point.usdCents, point.rate) : point.amount
      if (plan.currency === 'USD') Object.assign(charge, { usdCents: point.usdCents, rate: point.rate })
    }
    recalcUnlocked(plan)
    audit({ planId: id, action: 'price_change', text: `Price changes from ${fmtShort(effectiveFrom)}`, amount: plan.currency === 'USD' ? usdToPaisa(point.usdCents, point.rate) : point.amount })
  })
}

export function correctRate(chargeId, { rate }) {
  return write(() => {
    const charge = chargeById(chargeId)
    const plan = ownedOr404(charge.planId)
    if (plan.currency !== 'USD') throw new ApiError('Only dollar plans have a rate.')
    const started = duesOfCharge(chargeId).some((d) => paymentsForDue(d.id).some((p) => !memberById(p.payerMemberId).isOwnerSeat))
    if (started) throw new ApiError('A member already sent a payment for this charge, so the rate is locked.', { status: 409 })
    if (!(rate > 0)) throw new ApiError('Enter the rate.', { fields: { rate: 'Enter the rate you were charged, for example 123.40.' } })
    const before = charge.rate
    charge.rate = Math.round(rate * 100)
    charge.amount = usdToPaisa(charge.usdCents, charge.rate)
    if (plan.shared) {
      const due = duesOfCharge(chargeId).sort((a, b) => Number(memberById(b.memberId).isOwnerSeat) - Number(memberById(a.memberId).isOwnerSeat))
      const shares = splitExact(charge.amount, due.length, 0)
      due.forEach((d, i) => { d.amount = shares[i] })
    }
    audit({ planId: plan.id, action: 'rate_change', old: before, new: charge.rate, text: `You corrected the rate for ${fmtShort(charge.dueDate)} to ৳${rate}` })
  })
}

// ---------- members, invites, transfer ----------
export function createInvite(planId, { email }) {
  return write(() => {
    const plan = ownedOr404(planId)
    const clean = (email ?? '').trim().toLowerCase()
    if (!EMAIL_RE.test(clean)) throw new ApiError('Enter an email address like name@example.com.', { fields: { email: 'Enter an email address like name@example.com.' } })
    const taken = membersOf(planId).filter((m) => !m.isOwnerSeat || plan.mode === 'owner').length
    const pending = db.invites.filter((i) => i.planId === planId && i.status === 'pending').length
    const free = plan.seats - taken - pending
    if (free <= 0) throw new ApiError('All seats are taken or already invited.', { fields: { email: 'All seats are taken or already invited. Add a seat in Edit first.' } })
    if (membersOf(planId).some((m) => userById(m.userId).email === clean)) throw new ApiError('Already a member.', { fields: { email: 'This person is already in the plan.' } })
    if (db.invites.some((i) => i.planId === planId && i.status === 'pending' && i.email === clean)) throw new ApiError('Already invited.', { fields: { email: 'There is already a waiting invite for this email.' } })
    const invite = { id: nextId('inv'), planId, email: clean, status: 'pending', invitedBy: ME, createdAt: mockNow(), expiresOn: addDays(MOCK_TODAY, INVITE_DAYS), acceptedBy: null, token: nextId('tok') }
    db.invites.push(invite)
    if (!plan.shared) plan.shared = true
    audit({ planId, action: 'invite', text: `You invited ${clean}` })
    return invite
  })
}

export function cancelInvite(inviteId) {
  return write(() => {
    const invite = db.invites.find((i) => i.id === inviteId)
    ownedOr404(invite.planId)
    if (invite.status !== 'pending') throw new ApiError('Only a waiting invite can be cancelled.')
    invite.status = 'cancelled'
    audit({ planId: invite.planId, action: 'invite_cancelled', text: `You cancelled the invite for ${invite.email}` })
  })
}

export function decideLeave(memberId, { approve, leaveDate = MOCK_TODAY, unpaid = 'keep' }) {
  return write(() => {
    const member = memberById(memberId)
    const plan = ownedOr404(member.planId)
    const who = firstName(userById(member.userId))
    if (!approve) {
      member.status = 'active'
      member.leaveRequestedAt = null
      resolveNotifications((a) => a.type === 'leave' && a.memberId === memberId, 'declined')
      audit({ planId: plan.id, action: 'leave_declined', text: `You asked ${who} to stay` })
      return
    }
    if (member.isOwnerSeat) throw new ApiError('The owner cannot leave their own plan. Transfer it first.')
    member.status = 'left'
    member.leftOn = leaveDate
    member.leaveRequestedAt = null
    const openDues = db.dues.filter((d) => d.memberId === memberId && d.status === 'due' && chargeById(d.chargeId).periodStart < leaveDate)
    if (unpaid === 'waive') for (const d of openDues) Object.assign(d, { status: 'waived', waiverNote: `Waived when ${who} left.` })
    db.dues = db.dues.filter((d) => !(d.memberId === memberId && d.status === 'due' && chargeById(d.chargeId).periodStart >= leaveDate))
    recalcUnlocked(plan)
    resolveNotifications((a) => a.type === 'leave' && a.memberId === memberId, 'approved')
    audit({ planId: plan.id, action: 'member_left', tone: 'due', text: `${who} left on ${fmtShort(leaveDate)}${unpaid === 'waive' && openDues.length ? ', earlier dues waived' : ''}` })
  })
}

export function replaceMember(memberId, { email }) {
  return write(() => {
    const member = memberById(memberId)
    const plan = ownedOr404(member.planId)
    const clean = (email ?? '').trim().toLowerCase()
    if (!EMAIL_RE.test(clean)) throw new ApiError('Enter an email address like name@example.com.', { fields: { email: 'Enter an email address like name@example.com.' } })
    db.invites.push({ id: nextId('inv'), planId: plan.id, email: clean, status: 'pending', invitedBy: ME, createdAt: mockNow(), expiresOn: addDays(MOCK_TODAY, INVITE_DAYS), acceptedBy: null, token: nextId('tok'), replaces: memberId })
    audit({ planId: plan.id, action: 'replace', text: `You invited ${clean} to take ${firstName(userById(member.userId))}'s seat` })
  })
}

export function startTransfer(planId, { memberId, password }) {
  return write(() => {
    const plan = ownedOr404(planId)
    if (plan.mode === 'reseller') throw new ApiError('Reseller plans cannot change owner.', { status: 409 })
    if (!memberId) throw new ApiError('Pick a member.', { fields: { memberId: 'Pick the member who will become the owner.' } })
    checkPassword(password)
    const member = memberById(memberId)
    db.transfers = db.transfers.filter((t) => !(t.planId === planId && t.status === 'pending'))
    db.transfers.push({ id: nextId('tr'), planId, fromUserId: ME, toUserId: member.userId, status: 'pending', createdAt: mockNow() })
    audit({ planId, action: 'transfer_started', text: `You asked ${firstName(userById(member.userId))} to take over the plan` })
  })
}

export function cancelTransfer(transferId) {
  return write(() => {
    const t = db.transfers.find((x) => x.id === transferId)
    ownedOr404(t.planId)
    t.status = 'cancelled'
    audit({ planId: t.planId, action: 'transfer_cancelled', text: 'You cancelled the ownership transfer' })
  })
}

export function downloadOwnerStatement(planId, { month }) {
  return write(() => {
    ownedOr404(planId)
    return { number: `ONG-${month.replace('-', '')}-${planId.slice(-4).toUpperCase()}-${String(db.audit.length + 101).padStart(4, '0')}` }
  })
}
