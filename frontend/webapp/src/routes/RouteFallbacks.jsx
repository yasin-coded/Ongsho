import {
  InvitePageSkeleton,
  PlanFormSkeleton,
  ReviewPaymentsSkeleton,
  Skeleton,
  SkeletonCard,
} from '@/components/ui/Misc'

export function LandingFallback() {
  return (
    <div className="stack-lg p-8 pt-12" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      <Skeleton className="mx-auto h-10 w-40" />
      <SkeletonCard lines={5} tall />
      <div className="card-grid">
        <SkeletonCard lines={4} />
        <SkeletonCard lines={4} />
      </div>
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