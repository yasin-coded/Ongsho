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
        <code>{display ?? value}</code>
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
