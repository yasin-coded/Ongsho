import {
  InvitePageSkeleton,
  PlanFormSkeleton,
  ReviewPaymentsSkeleton,
  SkeletonCard,
} from '@/components/ui/Misc'

export function LandingFallback() {
  return (
    <div className="grid min-h-[60vh] place-items-center p-8" aria-busy="true">
      <SkeletonCard lines={5} tall />
    </div>
  )
}

export function AppHomeFallback() {
  return (
    <div className="stack-lg" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      <div className="stat-grid">
        <SkeletonCard tall />
        <SkeletonCard tall />
        <SkeletonCard tall />
      </div>
      <div className="dash-home__cols grid gap-6">
        <div className="stack">
          <SkeletonCard lines={4} />
          <SkeletonCard lines={3} />
        </div>
        <div className="dash-home__aside stack">
          <SkeletonCard tall />
          <SkeletonCard lines={4} />
        </div>
      </div>
      <SkeletonCard lines={6} />
    </div>
  )
}

export function ListPageFallback() {
  return (
    <div className="stack" aria-busy="true">
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard lines={4} />
    </div>
  )
}

export function DetailPageFallback() {
  return <SkeletonCard lines={6} />
}

export { PlanFormSkeleton, ReviewPaymentsSkeleton, InvitePageSkeleton }