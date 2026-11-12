import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { invalidateScopes } from '@/api/invalidate'
import { keys } from '@/api/keys'
import { getNavCounts, snapshotNavCounts } from '@/api/dashboard'
import { useToast } from '@/components/ui/toast-context'

const DEFAULT_SCOPES = ['nav', 'plans', 'calendar', 'notifications', 'me', 'catalog']

/**
 * Runs an API write, invalidates affected queries, optional optimistic nav counts,
 * toasts the server message, and keeps per-field errors for the form.
 */
export function useAction(
  fn,
  {
    onSuccess,
    tone = 'paid',
    toastMessage,
    invalidate = DEFAULT_SCOPES,
    optimisticNav = 'snapshot',
  } = {},
) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [fields, setFields] = useState({})
  const mutation = useMutation({
    mutationFn: fn,
    onMutate: () => setFields({}),
    onSuccess: async (data, vars) => {
      if (optimisticNav === 'snapshot') {
        const snap = snapshotNavCounts()
        if (snap) queryClient.setQueryData(keys.navCounts, snap)
      } else if (optimisticNav === 'decrement-unread') {
        queryClient.setQueryData(keys.navCounts, (prev) => {
          if (!prev) return prev
          return { ...prev, unread: Math.max(0, (prev.unread ?? 1) - 1) }
        })
      }
      await invalidateScopes(queryClient, invalidate)
      if (optimisticNav === 'refetch-nav') {
        try {
          const fresh = await getNavCounts()
          queryClient.setQueryData(keys.navCounts, fresh)
        } catch {
          /* invalidation will refetch */
        }
      }
      const message = typeof toastMessage === 'function' ? toastMessage(data, vars) : toastMessage ?? data?.message
      if (message) toast(message, tone)
      onSuccess?.(data, vars)
    },
    onError: (error) => {
      if (error?.status === 0) {
        toast(error.message ?? 'Could not reach Ongsho. Check your connection and try again.', 'due')
      }
      if (error?.fields && Object.keys(error.fields).length) setFields(error.fields)
      else if (error?.status !== 0) toast(error?.message ?? 'Something went wrong. Try again.', 'due')
    },
  })
  return { ...mutation, run: mutation.mutate, fields, setFields, busy: mutation.isPending }
}
