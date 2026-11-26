import { Link } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { cancelHoverPrefetch, scheduleHoverPrefetch } from '@/lib/prefetchRoutes'

/** Link with debounced prefetch for plan, shared-plan, and review routes. */
export function PrefetchLink({ to, prefetchKind, prefetchId, onMouseEnter, onMouseLeave, onFocus, onBlur, ...rest }) {
  const queryClient = useQueryClient()
  const armed = Boolean(prefetchKind && prefetchId)

  const bindPrefetch = (handler, kind) => (e) => {
    if (armed) {
      if (kind === 'enter' || kind === 'focus') scheduleHoverPrefetch(queryClient, prefetchKind, prefetchId)
      else cancelHoverPrefetch()
    }
    handler?.(e)
  }

  return (
    <Link
      to={to}
      onMouseEnter={bindPrefetch(onMouseEnter, 'enter')}
      onMouseLeave={bindPrefetch(onMouseLeave, 'leave')}
      onFocus={bindPrefetch(onFocus, 'focus')}
      onBlur={bindPrefetch(onBlur, 'blur')}
      {...rest}
    />
  )
}