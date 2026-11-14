import { db, ME, nextId } from '@/mocks/db'
import { coverableDues, firstName, joinedPlans, memberPlanSummary, membersOf, myMemberRow, planById, seatShareNow, sharedTotals, userById } from '@/mocks/selectors'
import { audit, generateMissingCharges, recalcUnlocked, resolveNotifications } from '@/mocks/engine'
import { MOCK_TODAY, mockNow } from '@/lib/dates'
import { ApiError, paginate, read, write } from '../client'

export function getMyShared({ filter = 'all', page = 1, size = 5 } = {}) {
  return read(
    () => {
      const all = joinedPlans(ME).map((p) => memberPlanSummary(p, ME))
      const counts = {
        all: all.length,
        due: all.filter((p) => p.openDues.length).length,
        pending: all.filter((p) => p.pendingAmount > 0).length,
        paid: all.filter((p) => !p.openDues.length && !p.pendingAmount).length,
      }
      const filtered = all.filter((p) =>
        filter === 'due' ? p.openDues.length : filter === 'pending' ? p.pendingAmount > 0 : filter === 'paid' ? !p.openDues.length && !p.pendingAmount : true,
      )
      return { ...paginate(filtered, page, size), counts, totals: sharedTotals(ME) }
    },
    { empty: (v) => ({ ...v, items: [], total: 0, counts: { all: 0, due: 0, pending: 0, paid: 0 }, totals: { ...v.totals, shares: 0, planCount: 0, dueNow: 0, waiting: 0, dueNames: [], waitingNames: [] } }) },
  )
}

export function getMySharedPlan(id) {
  return read(() => {
    const plan = planById(id)
    if (!plan || !myMemberRow(id, ME) || plan.ownerId === ME) return { notFound: true }
    return { ...memberPlanSummary(plan, ME), coverable: coverableDues(plan.id, ME), mode: plan.mode }
  })
}

export function requestLeave(planId) {
  return write(() => {
    const me = myMemberRow(planId, ME)
    if (!me) throw new ApiError('You are not in this plan.', { status: 404 })
    me.status = 'leave_requested'
    me.leaveRequestedAt = mockNow()
    const owner = firstName(userById(planById(planId).ownerId))
    return { message: `Leave requested. You stay in the plan until ${owner} approves.` }
  })
}

export function cancelLeaveRequest(planId) {
  return write(() => {
    const me = myMemberRow(planId, ME)
    me.status = 'active'
    me.leaveRequestedAt = null
    return { message: 'Leave request cancelled.' }
  })
}

export function downloadMyStatement(planId, { month }) {
  return write(() => {
    if (!myMemberRow(planId, ME)) throw new ApiError('You are not in this plan.', { status: 404 })
    return { number: `ONG-${month.replace('-', '')}-${planId.slice(-4).toUpperCase()}-${String(db.audit.length + 201).padStart(4, '0')}` }
  })
}

// ---------- plan join link ----------
function parseMockJoinToken(token) {
  const m = /^mock-(.+)$/.exec(token ?? '')
  return m ? m[1] : null
}

export function getPlanJoin(token) {
  return read(() => {
    const planId = parseMockJoinToken(token)
    const plan = planId ? planById(planId) : null
    if (!plan || !plan.shared) return { notFound: true }
    const members = membersOf(plan.id)
    const pending = db.invites.filter((i) => i.planId === plan.id && i.status === 'pending' && !i.replaces).length
    const planFull = members.length + pending >= plan.seats
    const me = db.users.find((u) => u.id === ME)
    const alreadyMember = me ? members.some((m) => m.userId === me.id && m.status !== 'left') : false
    const { perSeat } = seatShareNow(plan)
    const owner = userById(plan.ownerId)
    return {
      kind: 'plan',
      token,
      planId: plan.id,
      planName: plan.planName,
      serviceKey: plan.serviceKey,
      seats: plan.seats,
      seatsTaken: members.length,
      canJoin: !planFull && !alreadyMember,
      alreadyMember,
      planFull,
      from: firstName(owner),
      share: perSeat,
      cycle: plan.cycle,
      notFound: false,
    }
  })
}

export function acceptPlanJoin(token) {
  return write(() => {
    const planId = parseMockJoinToken(token)
    const plan = planId ? planById(planId) : null
    if (!plan) throw new ApiError('This invite does not exist.', { status: 404 })
    const members = membersOf(plan.id)
    const pending = db.invites.filter((i) => i.planId === plan.id && i.status === 'pending' && !i.replaces).length
    if (members.length + pending >= plan.seats) throw new ApiError('This plan is full.', { status: 409 })
    if (members.some((m) => m.userId === ME && m.status !== 'left')) {
      throw new ApiError('You are already in this plan.', { status: 409 })
    }
    db.members.push({
      id: nextId('m'),
      planId: plan.id,
      userId: ME,
      status: 'active',
      joinedOn: MOCK_TODAY,
      isOwnerSeat: false,
      customShare: null,
    })
    generateMissingCharges(plan.id)
    return { planId: plan.id, message: `You joined ${plan.planName}.` }
  })
}

export function signupAndJoinPlan(token, { email, name, password }) {
  return write(() => {
    const planId = parseMockJoinToken(token)
    const plan = planId ? planById(planId) : null
    if (!plan) throw new ApiError('This invite does not exist.', { status: 404 })
  if (db.users.some((u) => u.email === email)) throw new ApiError('An account already exists. Log in to join.', { status: 409 })
    const user = { id: nextId('u'), name: name.trim(), email, avatarColor: null }
    db.users.push(user)
    db.members.push({
      id: nextId('m'),
      planId: plan.id,
      userId: user.id,
      status: 'active',
      joinedOn: MOCK_TODAY,
      isOwnerSeat: false,
      customShare: null,
    })
    generateMissingCharges(plan.id)
    return { access: 'mock-access', user: { id: user.id, name: user.name, email: user.email }, planId: plan.id }
  })
}

// ---------- invites ----------
function joinPlan(invite, userId) {
  const plan = planById(invite.planId)
  if (invite.status !== 'pending') throw new ApiError('This invite was already used or cancelled.', { status: 409 })
  if (invite.expiresOn < MOCK_TODAY) throw new ApiError('This invite has expired. Ask the owner for a new one.', { status: 410 })
  invite.status = 'accepted'
  invite.acceptedBy = userId
  if (invite.replaces) {
    const old = db.members.find((m) => m.id === invite.replaces)
    if (old && old.status !== 'left') Object.assign(old, { status: 'left', leftOn: MOCK_TODAY, leaveRequestedAt: null })
  }
  db.members.push({
    id: nextId('m'), planId: plan.id, userId, joinedOn: MOCK_TODAY, status: 'active', leftOn: null, leaveRequestedAt: null,
    isOwnerSeat: false, prefMethod: plan.method, customShare: invite.customShare,
  })
  generateMissingCharges(plan)
  recalcUnlocked(plan)
  return plan
}

export function acceptInvite(ref) {
  return write(() => {
    const inviteId = typeof ref === 'object' ? ref.id : ref
    const invite = db.invites.find((i) => i.id === inviteId)
    const me = userById(ME)
    if (!invite || invite.email !== me.email) throw new ApiError('This invite is for a different email.', { status: 403 })
    const plan = joinPlan(invite, ME)
    resolveNotifications((a) => a.type === 'invite' && a.inviteId === inviteId, 'joined')
    return { message: `You joined ${plan.planName}. It is now under Shared Plans.`, planId: plan.id }
  })
}

export function declineInvite(inviteId) {
  return write(() => {
    const invite = db.invites.find((i) => i.id === inviteId)
    invite.status = 'declined'
    resolveNotifications((a) => a.type === 'invite' && a.inviteId === inviteId, 'declined')
    return { message: 'Invite declined. The owner is told.' }
  })
}

/** Public invite page: a new person signs up with the invited email, which counts as proof of that email. */
export function acceptInviteAsNewUser(token, { name, password }) {
  return write(() => {
    const invite = db.invites.find((i) => i.token === token)
    if (!invite) throw new ApiError('This invite does not exist.', { status: 404 })
    const fields = {}
    if (!name?.trim()) fields.name = 'Enter your name.'
    if (!password || password.length < 8) fields.password = 'Use at least 8 characters.'
    if (Object.keys(fields).length) throw new ApiError('Check the highlighted fields.', { fields })
    const user = { id: nextId('u'), name: name.trim(), email: invite.email, avatarColor: null }
    db.users.push(user)
    joinPlan(invite, user.id)
    return { planId: invite.planId }
  })
}

// ---------- ownership transfer (receiving side) ----------
export function acceptTransfer(transferId) {
  return write(() => {
    const t = db.transfers.find((x) => x.id === transferId)
    if (!t || t.toUserId !== ME || t.status !== 'pending') throw new ApiError('This request is no longer open.', { status: 409 })
    const plan = planById(t.planId)
    const members = db.members.filter((m) => m.planId === plan.id && m.status !== 'left')
    for (const m of members) m.isOwnerSeat = m.userId === ME
    plan.ownerId = ME
    t.status = 'accepted'
    recalcUnlocked(plan)
    resolveNotifications((a) => a.type === 'transfer' && a.transferId === transferId, 'accepted')
    audit({ planId: plan.id, action: 'transfer_accepted', text: `You became the owner. ${firstName(userById(t.fromUserId))} is now a member.` })
    return { message: `You now own ${plan.planName}. It moved to My Plans with all its history.`, planId: plan.id }
  })
}

export function declineTransfer(transferId) {
  return write(() => {
    const t = db.transfers.find((x) => x.id === transferId)
    t.status = 'declined'
    resolveNotifications((a) => a.type === 'transfer' && a.transferId === transferId, 'declined')
    return { message: 'Transfer declined. Nothing changed.' }
  })
}
