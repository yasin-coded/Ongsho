import { useEffect, useRef, useState } from 'react'

/**
 * Wraps a react-query mutation so a second call is ignored until the first settles.
 * `isPending` only disables the button after a re-render, so a fast double-click would otherwise send twice.
 */
export function useSingleFlight(mutation) {
  const inFlight = useRef(false)
  return (vars) => {
    if (inFlight.current) return
    inFlight.current = true
    mutation.mutate(vars, {
      onSettled: () => {
        inFlight.current = false
      },
    })
  }
}

/** Whole-second countdown. Returns [secondsLeft, restart(seconds)]. */
export function useCountdown(initial = 0) {
  const [left, setLeft] = useState(initial)
  useEffect(() => {
    if (left <= 0) return undefined
    const t = setTimeout(() => setLeft((v) => v - 1), 1000)
    return () => clearTimeout(t)
  }, [left])
  return [left, setLeft]
}
