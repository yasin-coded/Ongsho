import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { snapshotNavCounts } from '@/api/dashboard'
import { useToast } from '@/components/ui/toast-context'

/**
 * Runs a mock API write, refreshes every query (counts in the sidebar included),
 * toasts the server's message, and keeps per-field errors for the form.
 */
export function useAction(fn, { onSuccess, tone = 'paid', toastMessage } = {}) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [fields, setFields] = useState({})
  const mutation = useMutation({
    mutationFn: fn,
    onMutate: () => setFields({}),
    onSuccess: async (data, vars) => {
      // Push counts into the cache synchronously so the shell updates even if invalidate/refetch is delayed or skipped (e.g. query still flagged invalidated).
      queryClient.setQueryData(['nav-counts'], snapshotNavCounts())
      await queryClient.invalidateQueries({ refetchType: 'all' })
      const message = typeof toastMessage === 'function' ? toastMessage(data, vars) : toastMessage ?? data?.message
      if (message) toast(message, tone)
      onSuccess?.(data, vars)
    },
    onError: (error) => {
      if (error?.fields && Object.keys(error.fields).length) setFields(error.fields)
      else toast(error?.message ?? 'Something went wrong. Try again.', 'due')
    },
  })
  return { ...mutation, run: mutation.mutate, fields, setFields, busy: mutation.isPending }
}
