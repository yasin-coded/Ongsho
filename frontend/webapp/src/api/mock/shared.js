import { db, ME, nextId } from '@/mocks/db'
import { coverableDues, firstName, joinedPlans, memberPlanSummary, myMemberRow, planById, sharedTotals, userById } from '@/mocks/selectors'
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
    return { ...memberPlanSummary(plan, ME), coverable: coverableDues(id, ME), mode: plan.mode }
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
