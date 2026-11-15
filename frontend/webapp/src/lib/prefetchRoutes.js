import { keys } from '@/api/keys'
import { getMySharedPlan } from '@/api/shared'
import * as plansApi from '@/api/plans'

function saveDataMode() {
  return Boolean(typeof navigator !== 'undefined' && navigator.connection?.saveData)
}

let hoverTimer

export function cancelHoverPrefetch() {
  if (hoverTimer) {
    clearTimeout(hoverTimer)
    hoverTimer = null
  }
}

export function prefetchOwnerPlan(queryClient, id) {
  if (!id || saveDataMode()) return
  queryClient.prefetchQuery({
    queryKey: keys.subscription(id),
    queryFn: () => plansApi.getSubscription(id),
    staleTime: 30_000,
  })
}

export function prefetchSharedPlan(queryClient, id) {
  if (!id || saveDataMode()) return
  queryClient.prefetchQuery({
    queryKey: keys.sharedPlan(id),
    queryFn: () => getMySharedPlan(id),
    staleTime: 30_000,
  })
}

export function prefetchReview(queryClient, id) {
  if (!id || saveDataMode()) return
  queryClient.prefetchQuery({
    queryKey: ['review', id],
    queryFn: () => plansApi.getReview(id),
    staleTime: 30_000,
  })
}

/** Debounced prefetch for plan / shared / review links (pointer + keyboard focus). */
export function scheduleHoverPrefetch(queryClient, kind, id) {
  if (!id || saveDataMode()) return
  cancelHoverPrefetch()
  hoverTimer = setTimeout(() => {
    if (kind === 'owner') prefetchOwnerPlan(queryClient, id)
    else if (kind === 'shared') prefetchSharedPlan(queryClient, id)
    else if (kind === 'review') prefetchReview(queryClient, id)
    hoverTimer = null
  }, 120)
}