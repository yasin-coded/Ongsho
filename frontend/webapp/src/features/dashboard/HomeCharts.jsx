import { lazy, memo, Suspense } from 'react'
import { Skeleton } from '@/components/ui/Misc'

const loadCharts = () => import('@/components/ui/Charts')

const LazyDonut = lazy(() => loadCharts().then((m) => ({ default: m.Donut })))
const LazyLegend = lazy(() => loadCharts().then((m) => ({ default: m.Legend })))
const LazyForecastBars = lazy(() => loadCharts().then((m) => ({ default: m.ForecastBars })))

function ChartFallback({ tall }) {
  return <Skeleton className={tall ? 'h-24 w-full' : 'size-20 shrink-0 rounded-full'} aria-hidden="true" />
}

export const HomeDonut = memo(function HomeDonut(props) {
  return (
    <Suspense fallback={<ChartFallback />}>
      <LazyDonut {...props} />
    </Suspense>
  )
})

export const HomeLegend = memo(function HomeLegend(props) {
  return (
    <Suspense fallback={null}>
      <LazyLegend {...props} />
    </Suspense>
  )
})

export const HomeForecastBars = memo(function HomeForecastBars(props) {
  return (
    <Suspense fallback={<ChartFallback tall />}>
      <LazyForecastBars {...props} />
    </Suspense>
  )
})