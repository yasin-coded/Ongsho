import { cx } from '@/components/ui/Box'

export function BootSplash({ leaving, onGone }) {
  return (
    <div
      className={cx('boot-splash', leaving && 'boot-splash--leave')}
      role="status"
      aria-busy={!leaving}
      aria-live="polite"
      aria-label={leaving ? undefined : 'Loading Ongsho'}
      onTransitionEnd={(e) => {
        if (leaving && e.target === e.currentTarget && e.propertyName === 'opacity') onGone?.()
      }}
    >
      <div className="boot-splash__spinner" aria-hidden="true" />
    </div>
  )
}
