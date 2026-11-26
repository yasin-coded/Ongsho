import { lazy } from 'react'

export function lazyPage(importFn) {
  const Lazy = lazy(importFn)
  return function LazyRoute(props) {
    return <Lazy {...props} />
  }
}