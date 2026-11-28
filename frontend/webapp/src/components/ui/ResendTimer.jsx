import { cx } from './Box'

function formatCountdown(seconds) {
  if (seconds <= 60) return String(seconds)
  const m = Math.floor(seconds / 60)
  return `${m}:${String(seconds % 60).padStart(2, '0')}`
}

/** Big tabular countdown shown above a disabled resend button. Renders nothing at zero. */
export function ResendTimer({ seconds, className }) {
  if (seconds <= 0) return null
  return (
    <p role="timer" aria-live="off" aria-label={`Resend available in ${seconds} seconds`} className={cx('row items-baseline justify-center gap-2', className)}>
      <span className="t-meta">You can resend in</span>
      <span className="t-countdown">{formatCountdown(seconds)}</span>
      <span className="t-meta">{seconds > 60 ? 'minutes' : seconds === 1 ? 'second' : 'seconds'}</span>
    </p>
  )
}
