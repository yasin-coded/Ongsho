import { Link } from 'react-router'

const cx = (...parts) => parts.filter(Boolean).join(' ')

export function Box({ as: Tag = 'section', variant, roomy, panel, className, children, ...rest }) {
  return (
    <Tag
      className={cx(
        'neo-box',
        roomy && 'neo-box--roomy',
        panel && 'neo-box--panel',
        variant === 'flat' && 'neo-box--flat',
        variant === 'highlight' && 'neo-box--highlight',
        variant === 'danger' && 'neo-box--danger',
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  )
}

export function LinkBox({ to, className, children, ...rest }) {
  return (
    <Link to={to} className={cx('neo-box', className)} {...rest}>
      {children}
    </Link>
  )
}

export function BoxHead({ title, as: H = 'h2', tag, action, sub, className }) {
  return (
    <div className={cx('mb-5 grid gap-1', className)}>
      <div className="row-between">
        <div className="box-head__title-row">
          <H className="t-card">{title}</H>
          {tag}
        </div>
        {action}
      </div>
      {sub && <p className="t-meta t-muted">{sub}</p>}
    </div>
  )
}

export function StatCard({ label, value, valueClass = '', helper, visual, children, tone, className }) {
  return (
    <Box
      className={cx('grid min-w-0 content-between gap-3', visual ? 'overflow-visible' : 'overflow-hidden', className)}
      aria-label={typeof label === 'string' ? label : undefined}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="grid min-w-0 flex-1 gap-2">
          <p className="t-label leading-snug">{label}</p>
          <p className={cx('t-big', valueClass)} style={tone ? { color: tone } : undefined}>
            {value}
          </p>
          {helper && <p className="t-meta leading-snug">{helper}</p>}
        </div>
        {visual && <div className="stat-card__visual">{visual}</div>}
      </div>
      {children}
    </Box>
  )
}

export { cx }
