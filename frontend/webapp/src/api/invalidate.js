import { keys } from './keys'

/** Query keys to refetch after writes (scoped invalidation). */
export const scopes = {
  me: [{ queryKey: keys.me }],
  reminders: [{ queryKey: keys.reminderSettings }],
  catalog: [{ queryKey: keys.categories }, { queryKey: keys.serviceNames }],
  plans: [{ queryKey: ['subscriptions'] }, { queryKey: ['subscription'] }, { queryKey: ['plan-form'] }],
  calendar: [{ queryKey: ['calendar'] }],
  nav: [{ queryKey: keys.navCounts }],
  notifications: [{ queryKey: ['notifications'] }],
  shared: [{ queryKey: ['my-shared'] }, { queryKey: ['shared-plan'] }],
  dashboard: [{ queryKey: keys.dashboard }],
}

export async function invalidateScopes(queryClient, list = []) {
  const seen = new Set()
  const tasks = []
  for (const name of list) {
    for (const q of scopes[name] ?? []) {
      const id = JSON.stringify(q.queryKey)
      if (seen.has(id)) continue
      seen.add(id)
      tasks.push(queryClient.invalidateQueries({ ...q, refetchType: 'all' }))
    }
  }
  await Promise.all(tasks)
}

export function bumpNavUnread(queryClient, delta) {
  queryClient.setQueryData(keys.navCounts, (prev) => {
    if (!prev) return prev
    return { ...prev, unread: Math.max(0, (prev.unread ?? 0) + delta) }
  })
}
