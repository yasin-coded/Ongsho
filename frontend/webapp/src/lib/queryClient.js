import { QueryClient, keepPreviousData } from '@tanstack/react-query'
import { keys } from '@/api/keys'

const paginatedPlaceholder = keepPreviousData

export function createQueryClient({ liveApi }) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: liveApi,
        refetchOnReconnect: liveApi,
        retry: (count, err) => (err?.status === 0 || !err?.status) && count < 1,
      },
    },
  })

  client.setQueryDefaults(['categories'], { staleTime: 5 * 60_000 })
  client.setQueryDefaults(['service-names'], { staleTime: 5 * 60_000 })

  client.setQueryDefaults(keys.navCounts, {
    staleTime: 30_000,
    refetchOnWindowFocus: liveApi,
    refetchInterval: liveApi ? 60_000 : false,
    refetchIntervalInBackground: false,
  })

  client.setQueryDefaults(['notifications'], {
    staleTime: 30_000,
    refetchOnWindowFocus: liveApi,
    refetchInterval: liveApi ? 60_000 : false,
    refetchIntervalInBackground: false,
    placeholderData: paginatedPlaceholder,
  })

  client.setQueryDefaults(['subscriptions'], {
    staleTime: 30_000,
    placeholderData: paginatedPlaceholder,
  })
  client.setQueryDefaults(['subscription'], { staleTime: 30_000 })
  client.setQueryDefaults(['plan'], { staleTime: 30_000 })
  client.setQueryDefaults(['shared-plan'], { staleTime: 30_000 })
  client.setQueryDefaults(['my-shared'], {
    staleTime: 30_000,
    placeholderData: paginatedPlaceholder,
  })
  client.setQueryDefaults(['review'], { staleTime: 30_000 })

  client.setQueryDefaults(keys.dashboard, { staleTime: 60_000 })
  client.setQueryDefaults(['calendar'], { staleTime: 60_000, placeholderData: paginatedPlaceholder })

  client.setQueryDefaults(keys.me, { staleTime: 60_000 })

  return client
}