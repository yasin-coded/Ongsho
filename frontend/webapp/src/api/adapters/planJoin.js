import { lookupServiceKey } from '@/lib/services'
import { toPaisa } from '@/lib/money'
import { idStr } from './common'

export function mapPlanJoin(data, token) {
  return {
    kind: 'plan',
    token,
    planId: idStr(data.plan_id),
    planName: data.plan_name,
    serviceKey: lookupServiceKey(data.plan_name),
    seats: data.seats,
    seatsTaken: data.seats_taken,
    canJoin: data.can_join,
    alreadyMember: data.already_member,
    planFull: data.plan_full,
    from: data.from,
    share: data.share ? toPaisa(data.share) : 0,
    cycle: data.cycle,
    notFound: false,
  }
}