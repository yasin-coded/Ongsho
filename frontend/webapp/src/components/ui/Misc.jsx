import { useEffect, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, Copy, RotateCw, TriangleAlert } from 'lucide-react'
import { STATUS } from '@/lib/colors'
import { dayOfMonth, monthShortName } from '@/lib/dates'
import { Box, cx } from './Box'
import { Button } from './Button'

export function DashedDivider({ className }) {
  return <hr className={cx('dashed-line', className)} />
}

export function CountBubble({ count, tone = 'cream', label }) {
  if (!count) return null
  return (
    <span className={cx('bubble', tone === 'notify' ? 'bubble--notify' : 'bubble--cream')} aria-label={label ?? `${count}`}>
      {count > 99 ? '99+' : count}
    </span>
  )
}

export function FilterChip({ selected, count, alert, onClick, children }) {
  return (
    <button type="button" className="chip" aria-pressed={selected} onClick={onClick}>
      {children}
      {count !== undefined && <span className={cx('chip__count', alert && count > 0 && 'chip__count--alert')}>{count}</span>}
    </button>
  )
}

export function DateBadge({ date }) {
  return (
    <span className="date-badge" aria-hidden="true">
      <span className="date-badge__day">{dayOfMonth(date)}</span>
      <span className="date-badge__month">{monthShortName(date)}</span>
    </span>
  )
}

export function ProgressBar({ parts, total, label }) {
  const safe = Math.max(total, 1)
  return (
    <div className="progress" role="img" aria-label={label}>
      {parts
        .filter((p) => p.value > 0)
        .map((p) => (
          <span key={p.key} style={{ width: `${(p.value / safe) * 100}%`, background: p.fill }} />
        ))}
    </div>
  )
}

const STEPS = ['due', 'pending', 'paid']

/** 1 DUE, 2 PENDING, 3 PAID. Done steps and the current step are filled. */
export function Stepper({ current, labels = {} }) {
  const at = STEPS.indexOf(current === 'waived' ? 'paid' : current)
  return (
    <ol className="flex items-start" aria-label="Payment progress">
      {STEPS.map((step, i) => {
        const filled = i <= at
        return (
          <li key={step} className="flex flex-1 items-start last:flex-none" aria-current={i === at ? 'step' : undefined}>
            <div className="grid justify-items-center gap-2 text-center">
              <span
                className={cx('num-circle', i === at && 'scale-110 shadow-[var(--shadow-neo-sm)]')}
                style={{ background: filled ? STATUS[step].fill : '#fff', color: filled && step === 'due' ? '#000' : '#000' }}
              >
                {i < at ? <Check aria-hidden="true" className="size-5" /> : i + 1}
              </span>
              <span className="max-w-[9rem] text-[0.8rem] leading-tight font-bold uppercase">{labels[step] ?? STATUS[step].label}</span>
            </div>
            {i < STEPS.length - 1 && <span className={cx('mx-2 mt-5 h-[0.1875rem] min-w-6 flex-1', i < at ? 'bg-black' : 'bg-black/25')} aria-hidden="true" />}
          </li>
        )
      })}
    </ol>
  )
}

export function Pagination({ page, pages, onPage, label = 'Pages' }) {
  if (pages <= 1) return null
  return (
    <nav className="row justify-center" aria-label={label}>
      <button type="button" className="chip" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page">
        <ChevronLeft aria-hidden="true" className="size-4" /> Prev
      </button>
      {Array.from({ length: pages }, (_, i) => i + 1).map((n) => (
        <button key={n} type="button" className="chip min-w-11 justify-center" aria-pressed={n === page} aria-current={n === page ? 'page' : undefined} onClick={() => onPage(n)}>
          {n}
        </button>
      ))}
      <button type="button" className="chip" onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Next page">
        Next <ChevronRight aria-hidden="true" className="size-4" />
      </button>
    </nav>
  )
}

export function EmptyState({ icon: Icon, title, helper, children }) {
  return (
    <div className="grid justify-items-center gap-3 px-4 py-16 text-center">
      {Icon && <Icon aria-hidden="true" className="size-10 text-[#8a8a78]" />}
      <p className="font-[family-name:var(--font-display)] text-[clamp(1.5rem,1.2rem+1.5vw,2.25rem)] leading-none font-bold text-[#8a8a78] uppercase">{title}</p>
      {helper && <p className="t-meta t-measure">{helper}</p>}
      {children}
    </div>
  )
}

export function Skeleton({ className, style }) {
  return <span className={cx('skeleton block', className)} style={style} aria-hidden="true" />
}

export function SkeletonCard({ lines = 3, tall }) {
  return (
    <Box className="grid gap-4" aria-busy="true" aria-live="polite" aria-label="Loading">
      <span className="sr-only">Loading</span>
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className={tall ? 'h-24 w-1/2' : 'h-12 w-1/2'} />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className="h-4" style={{ width: `${90 - i * 15}%` }} />
      ))}
    </Box>
  )
}

function SkeletonBusy({ className, children }) {
  return (
    <div className={cx('min-w-0', className)} aria-busy="true" aria-live="polite" aria-label="Loading">
      <span className="sr-only">Loading</span>
      {children}
    </div>
  )
}

function PlanFormStepSkeleton({ tall, pair }) {
  return (
    <Box className="grid gap-5">
      <div className="row gap-3">
        <Skeleton className="size-9 shrink-0 rounded-full" />
        <Skeleton className="h-6 w-[min(14rem,70%)]" />
      </div>
      {pair ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-[5.5rem]" />
          <Skeleton className="h-[5.5rem]" />
        </div>
      ) : (
        <div className="grid gap-4">
          {tall ? (
            <>
              <div className="row flex-wrap gap-2">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-11 w-24 rounded-full" />
                ))}
              </div>
              <Skeleton className="h-11" />
              <Skeleton className="h-11" />
              <Skeleton className="h-20" />
            </>
          ) : (
            <>
              <Skeleton className="h-11" />
              <Skeleton className="h-11" />
              <Skeleton className="h-16" />
            </>
          )}
        </div>
      )}
    </Box>
  )
}

/** Matches the create/edit plan form grid: six step cards + preview column. */
export function PlanFormSkeleton() {
  return (
    <SkeletonBusy className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(18rem,1fr)]">
      <div className="stack">
        <PlanFormStepSkeleton pair />
        <PlanFormStepSkeleton tall />
        <PlanFormStepSkeleton />
        <PlanFormStepSkeleton />
        <PlanFormStepSkeleton />
        <PlanFormStepSkeleton tall />
        <div className="row justify-end gap-3">
          <Skeleton className="h-11 w-24" />
          <Skeleton className="h-11 w-32" />
        </div>
      </div>
      <div className="stack min-w-0">
        <Box className="grid gap-4">
          <Skeleton className="h-5 w-2/5" />
          <div className="row gap-3">
            <Skeleton className="size-12 shrink-0 rounded-xl" />
            <div className="grid min-w-0 flex-1 gap-2">
              <Skeleton className="h-5 w-4/5" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-8 w-24 rounded-full" />
            </div>
          </div>
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-4" style={{ width: `${88 - i * 8}%` }} />
          ))}
        </Box>
        <Box className="grid gap-3">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-[92%]" />
          <Skeleton className="h-4 w-[85%]" />
        </Box>
      </div>
    </SkeletonBusy>
  )
}

/** Invite page body inside AuthLayout (highlight + fields). */
export function InvitePageSkeleton() {
  return (
    <SkeletonBusy className="grid gap-6">
      <div className="neo-box neo-box--flat neo-box--highlight row gap-4 !p-4">
        <Skeleton className="size-12 shrink-0 rounded-xl" />
        <div className="grid min-w-0 flex-1 gap-2">
          <Skeleton className="h-5 w-[min(12rem,80%)]" />
          <Skeleton className="h-4 w-full" />
        </div>
      </div>
      <div className="grid gap-5">
        <Skeleton className="h-11" />
        <Skeleton className="h-11" />
        <Skeleton className="h-11" />
        <Skeleton className="h-12 w-full" />
      </div>
    </SkeletonBusy>
  )
}

/** One catalog panel (categories or service names). */
export function CatalogPanelSkeleton() {
  return (
    <SkeletonBusy>
    <div className="catalog-panel" aria-hidden="true">
      <Skeleton className="h-6 w-36" />
      <div className="catalog-panel__body">
        <section className="grid gap-2">
          <Skeleton className="h-4 w-16" />
          <div className="catalog-built-in__wrap" style={{ maxHeight: '9rem' }}>
            <div className="row flex-wrap gap-2">
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} className="h-8 w-[4.5rem] rounded-full" />
              ))}
            </div>
          </div>
        </section>
        <section className="grid gap-2">
          <Skeleton className="h-4 w-12" />
          <div className="row flex-wrap gap-2">
            <Skeleton className="h-8 w-20 rounded-full" />
            <Skeleton className="h-8 w-24 rounded-full" />
          </div>
        </section>
      </div>
      <div className="catalog-panel__add row flex-wrap gap-3">
        <Skeleton className="h-11 min-w-[min(14rem,100%)] flex-1" />
        <Skeleton className="h-11 w-24" />
      </div>
    </div>
    </SkeletonBusy>
  )
}

function ReviewWaitingCardSkeleton() {
  return (
    <Box className="review-card-skeleton grid gap-5">
      <div className="flex flex-wrap items-start gap-4">
        <Skeleton className="size-11 shrink-0 rounded-full" />
        <div className="grid min-w-0 flex-1 gap-2">
          <Skeleton className="h-5 w-2/5" />
          <Skeleton className="h-4 w-full" />
        </div>
        <Skeleton className="h-8 w-24" />
      </div>
      <dl className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="grid gap-1">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-20 rounded-full" />
          </div>
        ))}
      </dl>
      <Skeleton className="copy-field-skeleton h-[3.25rem] w-full" />
      <div className="review-card__actions row justify-end gap-2">
        <Skeleton className="h-11 w-20" />
        <Skeleton className="h-11 w-20" />
        <Skeleton className="h-11 w-24" />
      </div>
    </Box>
  )
}

/** Review payments page layout: stats, waiting card(s), helper column. */
export function ReviewPaymentsSkeleton() {
  return (
    <SkeletonBusy className="stack-lg">
      <div className="grid gap-2">
        <Skeleton className="h-4 w-1/2 max-w-xs" />
        <div className="row flex-wrap items-start gap-4">
          <Skeleton className="size-14 shrink-0 rounded-xl" />
          <div className="grid min-w-0 flex-1 gap-2">
            <Skeleton className="h-8 w-[min(16rem,90%)]" />
            <Skeleton className="h-4 w-full" />
          </div>
        </div>
      </div>
      <div className="stat-grid">
        {Array.from({ length: 3 }, (_, i) => (
          <Box key={i} className="grid gap-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-10 w-1/2" />
            <Skeleton className="h-4 w-full" />
          </Box>
        ))}
      </div>
      <Skeleton className="h-8 w-56" />
      <div className="two-col">
        <div className="stack">
          <ReviewWaitingCardSkeleton />
        </div>
        <Box variant="highlight" className="grid gap-4">
          <Skeleton className="h-6 w-3/5" />
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="row gap-3">
              <Skeleton className="size-4 shrink-0 rounded-full" />
              <Skeleton className="h-4 flex-1" style={{ width: `${95 - i * 5}%` }} />
            </div>
          ))}
        </Box>
      </div>
      <Box className="grid gap-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-16 w-full" />
      </Box>
    </SkeletonBusy>
  )
}

export function ErrorBox({ error, onRetry, title = 'This did not load' }) {
  return (
    <Box variant="danger" className="grid justify-items-start gap-3" role="alert">
      <p className="row t-sub">
        <TriangleAlert aria-hidden="true" className="size-6" /> {title}
      </p>
      <p className="t-measure">{error?.message ?? 'Something went wrong.'}</p>
      {onRetry && (
        <Button variant="ghost" size="sm" icon={RotateCw} onClick={onRetry}>
          Retry
        </Button>
      )}
    </Box>
  )
}

export function CopyField({ value, label, display }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return undefined
    const t = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(t)
  }, [copied])
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      // Clipboard can be blocked; the value stays selectable on screen.
    }
    setCopied(true)
  }
  return (
    <div className="grid gap-1.5">
      {label && <p className="t-label">{label}</p>}
      <div className="copy-field">
        <code title={value}>{display ?? value}</code>
        <Button size="sm" variant={copied ? 'accept' : 'ghost'} icon={copied ? Check : Copy} onClick={copy} aria-label={copied ? 'Copied' : `Copy ${label ?? 'value'}`}>
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
    </div>
  )
}

export function NumberCircle({ children }) {
  return <span className="num-circle">{children}</span>
}

export function OutsideNote({ className }) {
  return <p className={cx('t-meta font-bold', className)}>Payments happen outside Ongsho. Ongsho only keeps the record.</p>
}
