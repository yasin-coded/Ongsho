import { memo } from 'react'
import { Donut, ForecastBars, Legend } from '@/components/ui/Charts'

export const HomeDonut = memo(function HomeDonut(props) {
  return <Donut {...props} />
})

export const HomeLegend = memo(function HomeLegend(props) {
  return <Legend {...props} />
})

export const HomeForecastBars = memo(function HomeForecastBars(props) {
  return <ForecastBars {...props} />
})