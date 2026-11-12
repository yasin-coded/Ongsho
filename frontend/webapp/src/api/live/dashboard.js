import { apiRequest } from '../http'
import { paginatedBody } from '../adapters/common'
import { mapCalendarResponse } from '../adapters/calendar'
import { mapNotificationCounts, mapNotificationItem } from '../adapters/notifications'
import * as mock from '../mock/dashboard'

const FILTER_TO_API = { all: 'all', action: 'action', needs_action: 'action', payments: 'payments', plans: 'plans', reminders: 'reminders' }
const FILTER_FROM_API = { action: 'needs_action' }

export async function getDashboard() {
  return mock.getDashboard()
}

export async function getCalendar(key) {
  const data = await apiRequest('get', '/api/calendar/', { params: { month: key } })
  return mapCalendarResponse(data)
}

export async function getNavCounts() {
  const data = await apiRequest('get', '/api/me/nav-counts/')
  return {
    reviews: data.reviews ?? 0,
    dues: data.dues ?? 0,
    unread: data.unread ?? 0,
  }
}

export function snapshotNavCounts() {
  return null
}

export async function getNotifications({ filter = 'all', page = 1, size = 8 } = {}) {
  const apiFilter = FILTER_TO_API[filter] ?? filter
  const data = await apiRequest('get', '/api/notifications/', {
    params: { filter: apiFilter, page, page_size: size },
  })
  const body = paginatedBody(data)
  return {
    ...body,
    items: body.items.map(mapNotificationItem),
    counts: mapNotificationCounts(data.counts),
    unread: data.unread ?? 0,
  }
}

export async function markAllRead() {
  const data = await apiRequest('post', '/api/notifications/read-all/')
  return { updated: data.updated ?? 0 }
}

export async function markRead(id) {
  const data = await apiRequest('post', `/api/notifications/${Number(id)}/read/`)
  return {
    id: idStr(data.id),
    read: true,
  }
}
