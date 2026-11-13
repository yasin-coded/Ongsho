import { lookupServiceKey } from '@/lib/services'
import { idStr, moneyFromApi } from './common'

export function mapCalendarEvent(e) {
  const serviceName = typeof e.service_name === 'string' ? e.service_name : e.service_name?.name
  return {
    id: idStr(e.id ?? `${e.plan_id}-${e.date}`),
    date: e.date,
    planId: idStr(e.plan_id),
    planName: e.plan_name,
    serviceName,
    serviceKey: lookupServiceKey(serviceName ?? e.plan_name ?? ''),
    role: e.role ?? null,
    status: e.status ?? null,
    amount: typeof e.amount === 'string' ? moneyFromApi(e.amount) ?? 0 : e.amount,
    kind: e.kind,
  }
}

export function mapCalendarResponse(data) {
  return {
    events: (data.events ?? []).map(mapCalendarEvent),
    next7: (data.next7 ?? []).map(mapCalendarEvent),
  }
}
