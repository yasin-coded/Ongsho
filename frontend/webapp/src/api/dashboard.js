import { delegate } from './delegate'
import * as mock from './mock/dashboard'
import * as live from './live/dashboard'
import { isLive } from './modes'

export const getDashboard = delegate(live, mock, 'getDashboard')
export const getCalendar = delegate(live, mock, 'getCalendar')
export const getNavCounts = delegate(live, mock, 'getNavCounts')
export const getNotifications = delegate(live, mock, 'getNotifications')
export const markAllRead = delegate(live, mock, 'markAllRead')
export const markRead = delegate(live, mock, 'markRead')

export function snapshotNavCounts() {
  if (isLive('getNavCounts')) return live.snapshotNavCounts()
  return mock.snapshotNavCounts()
}
