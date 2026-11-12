import { idStr, moneyFromApi } from './common'

export function mapCalendarEvent(e) {
  return {
    id: idStr(e.id ?? `${e.plan_id}-${e.date}`),
    date: e.date,
    planId: idStr(e.plan_id),
    planName: e.plan_name,
    serviceName: e.service_name,
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
