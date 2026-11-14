import { useEffect, useState } from 'react'

/** Subscribe to `window.matchMedia(query)`; SSR-safe default false. */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    const mq = window.matchMedia(query)
    const sync = () => setMatches(mq.matches)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [query])

  return matches
}

/** 360px-wide device column (22.5rem). */
export function useViewport360() {
  return useMediaQuery('(max-width: 22.499rem)')
}