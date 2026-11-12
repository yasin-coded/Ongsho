import { SERVICES } from '@/lib/services'
import { toPaisa } from '@/lib/money'
import { idStr } from './common'

function serviceKeyFromName(name) {
  const key = Object.entries(SERVICES).find(([, v]) => v.name.toLowerCase() === String(name ?? '').toLowerCase())?.[0]
  return key ?? null
}

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
    serviceKey: serviceKeyFromName(data.plan_name),
    seats: data.seats,
    from: data.from,
    share: data.share ? toPaisa(data.share) : 0,
    cycle: data.cycle,
    accountExists: data.account_exists,
    notFound: false,
  }
}
