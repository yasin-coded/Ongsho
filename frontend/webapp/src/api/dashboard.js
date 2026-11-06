import { db, ME } from '@/mocks/db'
import {
  dueInSevenDays, eventsBetween, firstName, forecast, joinedPlans, memberPlanSummary, monthSpend, navCounts, needsAttention,
  nextSevenDays, notificationsFor, ownedPlans, ownerPlanSummary, rarelyUsed, spendByCategory, userById,
} from '@/mocks/selectors'
import { mockNow, monthEnd } from '@/lib/dates'
import { paginate, read, write } from './client'

export function getDashboard() {
  return read(
    () => ({
      firstName: firstName(userById(ME)),
      spend: monthSpend(ME),
      dueSoon: dueInSevenDays(ME),
      rarely: rarelyUsed(ME),
      owned: ownedPlans(ME).map(ownerPlanSummary),
      joined: joinedPlans(ME).map((p) => memberPlanSummary(p, ME)),
      attention: needsAttention(ME),
      next7: nextSevenDays(ME),
      byCategory: spendByCategory(ME),
      forecast: forecast(ME, 6),
    }),
    {
      empty: (v) => ({
        ...v, spend: { total: 0, owned: 0, joined: 0, rows: [] }, dueSoon: { count: 0, total: 0, first: null, items: [] },
        rarely: { plans: [], yearly: 0 }, owned: [], joined: [], attention: [], next7: [], byCategory: [], forecast: [],
      }),
    },
  )
}

/** `key` is 'YYYY-MM'. */
export function getCalendar(key) {
  const from = `${key}-01`
  return read(() => ({ events: eventsBetween(ME, from, monthEnd(from)), next7: nextSevenDays(ME) }), { empty: { events: [], next7: [] } })
}

export function getNavCounts() {
  return read(() => navCounts(ME))
}

/** Sync counts from the in-memory mock DB (no latency). Use after writes so the sidebar updates immediately. */
export function snapshotNavCounts() {
  return structuredClone(navCounts(ME))
}

export function getNotifications({ filter = 'all', page = 1, size = 8 } = {}) {
  return read(
    () => {
      const all = notificationsFor(ME)
      const counts = {
        all: all.length,
        action: all.filter((n) => n.needsAction).length,
        payments: all.filter((n) => n.group === 'payments').length,
        plans: all.filter((n) => n.group === 'plans').length,
        reminders: all.filter((n) => n.group === 'reminders').length,
      }
      const filtered = all.filter((n) => (filter === 'all' ? true : filter === 'action' ? n.needsAction : n.group === filter))
      return { ...paginate(filtered, page, size), counts, unread: all.filter((n) => !n.readAt).length }
    },
    { empty: { items: [], page: 1, pages: 1, total: 0, size: 8, counts: { all: 0, action: 0, payments: 0, plans: 0, reminders: 0 }, unread: 0 } },
  )
}

export function markAllRead() {
  return write(() => {
    for (const n of db.notifications) if (n.userId === ME && !n.readAt) n.readAt = mockNow()
  })
}

export function markRead(id) {
  return write(() => {
    const n = db.notifications.find((x) => x.id === id)
    if (n && !n.readAt) n.readAt = mockNow()
  })
}

export { paginate }
