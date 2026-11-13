import { idStr, moneyFromApi } from './common'
import { mapMySharedSummary } from './shared'
import { mapSubscriptionSummary, mapMemberRow } from './plan'

export function mapAttentionItem(item) {
  const base = {
    id: `${item.kind}-${item.plan_id}-${item.count ?? 0}`,
    kind: item.kind,
    planId: idStr(item.plan_id),
    planName: item.plan_name,
    count: item.count,
  }
  if (item.kind === 'leave') {
    return {
      ...base,
      id: `leave-${item.payload?.member_id}`,
      memberId: idStr(item.payload?.member_id),
      name: item.title?.replace(' wants to leave', '') ?? '',
    }
  }
  if (item.kind === 'invite') {
    const from = item.title?.replace(/^Invite from /, '') ?? ''
    return { ...base, id: `invite-${item.payload?.invite_id}`, inviteId: idStr(item.payload?.invite_id), from }
  }
  if (item.kind === 'transfer') {
    const from = item.title?.replace(/^Transfer from /, '') ?? ''
    return { ...base, id: `transfer-${item.payload?.transfer_id}`, transferId: idStr(item.payload?.transfer_id), from }
  }
  return base
}

export function composeDashboard(summary, forecast, ownedCards, joinedCards, meUserId) {
  const spendRows = (summary.spend?.rows ?? []).map((r) => ({
    ...r,
    plan_id: r.plan_id,
    amount: moneyFromApi(r.amount),
  }))
  const spend = {
    total: moneyFromApi(summary.spend?.total) ?? 0,
    owned: moneyFromApi(summary.spend?.owned) ?? 0,
    joined: moneyFromApi(summary.spend?.joined) ?? 0,
    rows: spendRows,
  }
  const dueItems = (summary.due_soon?.items ?? []).map((e) => ({
    ...e,
    plan_id: idStr(e.plan_id),
    amount: moneyFromApi(e.amount) ?? 0,
  }))
  const dueSoon = {
    count: summary.due_soon?.count ?? 0,
    total: moneyFromApi(summary.due_soon?.total) ?? 0,
    first: summary.due_soon?.first,
    items: dueItems,
  }
  const rarely = {
    plans: (summary.rarely?.plans ?? []).map((p) => ({ id: idStr(p.id), planName: p.plan_name ?? p.planName })),
    yearly: moneyFromApi(summary.rarely?.yearly) ?? 0,
  }
  const byCategory = (summary.by_category ?? []).map((c) => ({
    name: c.name,
    amount: moneyFromApi(c.amount) ?? 0,
  }))
  const forecastRows = mapForecastMonths(forecast ?? [])
  const next7 = (summary.next7 ?? []).map((e) => ({
    id: e.id ?? `${e.role}-${e.plan_id}-${e.date}`,
    date: e.date,
    plan_id: idStr(e.plan_id),
    planName: e.plan_name ?? e.planName,
    role: e.role,
    kind: e.kind,
    amount: moneyFromApi(e.amount) ?? 0,
    status: e.status,
  }))
  const owned = ownedCards.map((sub) => {
    const members = (sub.members ?? []).map((m) => mapMemberRow(m, meUserId))
    return mapSubscriptionSummary(sub, members, meUserId)
  })
  const joined = joinedCards.map((row) => mapMySharedSummary(row, meUserId))
  return {
    firstName: summary.first_name,
    spend,
    dueSoon,
    rarely,
    owned,
    joined,
    attention: (summary.attention ?? []).map(mapAttentionItem),
    next7,
    byCategory,
    forecast: forecastRows,
  }
}

export function mapForecastMonths(rows) {
  return rows.map((m) => ({
    key: m.key,
    label: m.label,
    year: m.year,
    total: moneyFromApi(m.total) ?? 0,
    kind: m.kind,
    yearlyPlans: m.yearly_plans ?? [],
  }))
}
