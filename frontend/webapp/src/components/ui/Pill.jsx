import { Lock } from 'lucide-react'
import { METHODS, PLAN_STATUS, STATUS, categoryColor, inkOn } from '@/lib/colors'
import { cx } from './Box'

export function Pill({ fill = '#fff', small, plain, strike, className, children, ...rest }) {
  return (
    <span
      className={cx('neo-pill', small && 'neo-pill--sm', plain && 'neo-pill--plain', strike && 'neo-pill--strike', className)}
      style={{ background: fill, color: inkOn(fill) }}
      {...rest}
    >
      {children}
    </span>
  )
}

export function StatusPill({ status, small, children }) {
  const s = STATUS[status] ?? STATUS.due
  return (
    <Pill fill={s.fill} small={small}>
      {children ?? s.label}
    </Pill>
  )
}

export function PlanStatusPill({ status, small }) {
  const s = PLAN_STATUS[status]
  if (!s) return null
  return (
    <Pill fill={s.fill} small={small} strike={s.strike}>
      {s.label}
    </Pill>
  )
}

/** The status pill on an owner plan row: "2 TO REVIEW", "ALL PAID", "TRIAL", "JUST ME"… */
export function OwnerPlanPill({ pill, small }) {
  const fills = { review: '#fff200', due: '#ff1a1a', allpaid: '#22c400', trial: '#d9ccff', solo: '#000c7c', empty: '#ffffff' }
  if (PLAN_STATUS[pill.key] && pill.key !== 'trial') return <PlanStatusPill status={pill.key} small={small} />
  return (
    <Pill fill={fills[pill.key] ?? '#fff'} small={small}>
      {pill.label}
    </Pill>
  )
}

export function MethodTag({ method, small = true }) {
  const m = METHODS[method] ?? METHODS.other
  return (
    <Pill fill={m.fill} small={small} plain className="font-bold">
      {m.label}
    </Pill>
  )
}

export function CategoryTag({ name, small = true }) {
  return (
    <Pill fill={categoryColor(name)} small={small}>
      {name}
    </Pill>
  )
}

const ROLE = {
  owner: { label: 'Owner', fill: '#ff00ff' },
  asOwner: { label: 'As owner', fill: '#ff00ff' },
  member: { label: 'Member', fill: '#00ff8b' },
  asMember: { label: 'As member', fill: '#00ff8b' },
  reseller: { label: 'Reseller', fill: '#ffffff' },
  solo: { label: 'Just me', fill: '#000c7c' },
  rarely: { label: 'Rarely used', fill: '#000c7c' },
  ownerTag: { label: 'Owner', fill: '#846ace' },
}

export function RoleTag({ role, small = true }) {
  const r = ROLE[role]
  return (
    <Pill fill={r.fill} small={small}>
      {r.label}
    </Pill>
  )
}

export function StatusDot({ status, className }) {
  const s = STATUS[status]
  if (!s) return null
  return <span className={cx('status-dot', className)} style={{ background: s.fill }} role="img" aria-label={s.label} title={s.label} />
}

export function LockedNote({ children = 'Cannot be changed after the plan is created' }) {
  return (
    <p className="row t-meta gap-2 font-bold">
      <Lock aria-hidden="true" className="size-4" />
      {children}
    </p>
  )
}
