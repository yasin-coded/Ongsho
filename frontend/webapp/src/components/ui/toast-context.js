import { createContext, useContext } from 'react'

export const ToastContext = createContext(() => {})

/** `toast(message, tone)` where tone is 'paid' | 'pending' | 'due' | 'info'. */
export function useToast() {
  return useContext(ToastContext)
}
