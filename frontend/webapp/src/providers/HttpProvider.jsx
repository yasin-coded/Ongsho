import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { configureHttp } from '@/api/http'
import { clearAccessToken } from '@/auth/tokenStore'
import { useToast } from '@/components/ui/toast-context'

export function HttpProvider({ children }) {
  const queryClient = useQueryClient()
  const toast = useToast()

  useEffect(() => {
    configureHttp({
      onAuthFailure: () => {
        clearAccessToken()
        queryClient.clear()
        const returnTo = window.location.pathname + window.location.search
        try {
          sessionStorage.setItem('ongsho:return', returnTo)
          sessionStorage.setItem('ongsho:authMessage', 'Your session ended. Please sign in again.')
        } catch {
          /* ignore */
        }
        window.location.assign(`/login?next=${encodeURIComponent(returnTo)}`)
      },
      onToast429: (retryAfter) => {
        toast(
          retryAfter
            ? `Too many requests. Try again in ${retryAfter} seconds.`
            : 'Too many requests. Please wait a moment and try again.',
          'due',
        )
      },
      onToast5xx: () => {
        toast('Something went wrong on our side. Try again in a moment.', 'due')
      },
    })
  }, [queryClient, toast])

  return children
}
