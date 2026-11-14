/** Invites that still hold a seat (matches backend _seat_usage for non-replacement invites). */
export function inviteReservesSeat(invite) {
  return invite?.status === 'pending' || invite?.status === 'expired'
}

export function pendingInvitesReservingSeats(invites = []) {
  return invites.filter(inviteReservesSeat)
}

export function freeSeats(plan) {
  const reserved = pendingInvitesReservingSeats(plan.invites).length
  return plan.seatsCap - plan.seatsTaken - reserved
}

export function canSendInvite(plan) {
  return freeSeats(plan) > 0 && ['active', 'trial', 'paused'].includes(plan.status)
}
