let refreshPromise = null

/** Run one shared refresh; concurrent callers await the same promise. */
export function onceRefresh(run) {
  if (!refreshPromise) {
    refreshPromise = run().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

export function peekRefreshPromise() {
  return refreshPromise
}

export function resetRefreshQueue() {
  refreshPromise = null
}
