import { forwardRef } from 'react'
import { Link } from 'react-router'
import { LoaderCircle } from 'lucide-react'
import { cx } from './Box'

const VARIANT = {
  'primary-orange': 'btn-primary-orange',
  accept: 'btn-accept',
  reject: 'btn-reject',
  'reject-outline': 'btn-reject-outline',
  waive: 'btn-waive',
  'solo-navy': 'btn-solo-navy',
  review: 'btn-review',
  request: 'btn-request',
  ghost: 'btn-ghost',
  logout: 'btn-logout',
  brand: 'btn-brand',
  yellow: 'btn-yellow',
  dark: 'btn-dark',
}

function classes({ variant = 'ghost', size = 'md', block, italic, className }) {
  return cx('neo-btn', VARIANT[variant], size === 'sm' && 'neo-btn--sm', size === 'lg' && 'neo-btn--lg', block && 'neo-btn--block', italic && 'neo-btn--italic', className)
}

export const Button = forwardRef(function Button({ variant, size, block, italic, icon: Icon, busy, className, children, type = 'button', disabled, ...rest }, ref) {
  return (
    <button ref={ref} type={type} className={classes({ variant, size, block, italic, className })} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy ? <LoaderCircle aria-hidden="true" className="animate-spin motion-reduce:animate-none" /> : Icon && <Icon aria-hidden="true" />}
      {children}
    </button>
  )
})

export function LinkButton({ to, variant, size, block, italic, icon: Icon, className, children, ...rest }) {
  return (
    <Link to={to} className={classes({ variant, size, block, italic, className })} {...rest}>
      {Icon && <Icon aria-hidden="true" />}
      {children}
    </Link>
  )
}
