import { avatarColor, inkOn } from '@/lib/colors'
import { StatusDot } from './Pill'
import { cx } from './Box'

export function Avatar({ name, color, size = 'md', status, className, decorative = false }) {
  const fill = color ?? avatarColor({ name })
  const letter = (name ?? '?').trim().charAt(0).toUpperCase() || '?'
  return (
    <span
      className={cx('avatar', `avatar--${size}`, className)}
      style={{ background: fill, color: inkOn(fill) }}
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : name}
      aria-hidden={decorative || undefined}
    >
      {letter}
      {status && <StatusDot status={status} className="absolute -right-1 -bottom-1 !size-3.5 !border-2" />}
    </span>
  )
}

export function AvatarStack({ people, max = 4, size = 'sm', showStatus = false }) {
  const shown = people.slice(0, max)
  const extra = people.length - shown.length
  return (
    <span className="avatar-stack" role="list" aria-label={people.map((p) => p.name).join(', ')}>
      {shown.map((p) => (
        <span role="listitem" key={p.id ?? p.name}>
          <Avatar name={p.name} color={p.avatarColor} size={size} status={showStatus ? p.status : undefined} />
        </span>
      ))}
      {extra > 0 && <span className="avatar-stack__more">+{extra}</span>}
    </span>
  )
}

/** Owner views pass `status` to show a dot; member views never do, except on "You". */
export function MemberChip({ name, label, color, status }) {
  return (
    <span className="member-chip">
      <Avatar name={name} color={color} size="sm" decorative />
      <span>{label ?? name.split(' ')[0]}</span>
      {status && <StatusDot status={status} />}
    </span>
  )
}
