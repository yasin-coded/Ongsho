import { lookupServiceKey } from '@/lib/services'
import { toPaisa } from '@/lib/money'
import { idStr } from './common'

export function mapPublicInvite(data, token) {
  return {
    id: String(data.id),
    token,
    email: data.email,
    status: data.status,
    expiresOn: data.expires_on,
    expired: data.expired,
    planId: String(data.plan_id),
    planName: data.plan_name,
    serviceKey: lookupServiceKey(data.plan_name),
    seats: data.seats,
    from: data.from,
    share: data.share ? toPaisa(data.share) : 0,
    cycle: data.cycle,
    accountExists: data.account_exists,
    notFound: false,
  }
}
