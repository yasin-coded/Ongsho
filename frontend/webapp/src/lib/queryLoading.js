/** Show layout skeleton only on first load, not while stale data refetches. */
export function shouldShowInitialSkeleton(query) {
  return Boolean(query?.isPending && query?.data === undefined)
}
