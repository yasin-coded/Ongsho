import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { isLive } from '@/api/modes'
import { keys } from '@/api/keys'

/** How often to pull fresh nav counts / notifications while the tab is open (live API only). */
export const LIVE_SYNC_MS = 45_000

/** Extra React Query options for endpoints backed by the Django API. */
export function liveQueryOptions(apiName, { interval = LIVE_SYNC_MS } = {}) {
  if (!isLive(apiName)) return {}
  return {
    refetchInterval: interval,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  }
}

/**
 * Keeps sidebar badges and the visible page in sync with the server without a full reload.
 */
export function useAppLiveSync(pathname) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!isLive('getNavCounts')) return

    const refresh = () => {
      if (document.visibilityState !== 'visible') return

      queryClient.invalidateQueries({ queryKey: keys.navCounts, refetchType: 'active' })
      queryClient.invalidateQueries({ queryKey: ['notifications'], refetchType: 'active' })

      const home = pathname === '/app' || pathname === '/app/'
      if (home) {
        queryClient.invalidateQueries({ queryKey: keys.dashboard, refetchType: 'active' })
      }
      if (pathname.startsWith('/app/plans')) {
        queryClient.invalidateQueries({ queryKey: ['subscriptions'], refetchType: 'active' })
        queryClient.invalidateQueries({ queryKey: ['plan'], refetchType: 'active' })
        queryClient.invalidateQueries({ queryKey: ['subscription'], refetchType: 'active' })
        queryClient.invalidateQueries({ queryKey: ['review'], refetchType: 'active' })
      }
      if (pathname.startsWith('/app/shared')) {
        queryClient.invalidateQueries({ queryKey: ['my-shared'], refetchType: 'active' })
        queryClient.invalidateQueries({ queryKey: ['shared-plan'], refetchType: 'active' })
      }
      if (pathname.startsWith('/app/calendar')) {
        queryClient.invalidateQueries({ queryKey: ['calendar'], refetchType: 'active' })
      }
    }

    const id = window.setInterval(refresh, LIVE_SYNC_MS)
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [pathname, queryClient])
}
