import { SERVICES, SVG_SIZES } from '@/lib/services'
import { CUSTOM_PALETTE, hashIndex, inkOn } from '@/lib/colors'

const SIZES = { row: 4, compact: 3.5, large: 5.5, small: 2.75 }

/**
 * The supplied logo files carry their own border and shadow, so nothing is added around them.
 * They scale uniformly into a rem slot on the dashboard.
 */
export function ServiceLogo({ serviceKey, name, size = 'row' }) {
  const service = SERVICES[serviceKey]
  const widthRem = SIZES[size] ?? size
  const heightRem = (widthRem * SVG_SIZES.logo.h) / SVG_SIZES.logo.w
  if (service?.Logo) {
    const { Logo } = service
    return <Logo className="media flex-none" style={{ width: `${widthRem}rem`, height: `${heightRem}rem` }} role="img" aria-label={name ?? service.name} />
  }
  const fill = service?.color ?? CUSTOM_PALETTE[hashIndex(name ?? '?', CUSTOM_PALETTE.length)]
  const circle = widthRem * (161.64 / 175.13)
  return (
    <span className="relative inline-block flex-none" style={{ width: `${widthRem}rem`, height: `${heightRem}rem` }} role="img" aria-label={name}>
      <span className="absolute rounded-full bg-black" style={{ width: `${circle}rem`, height: `${circle}rem`, left: `${widthRem * (13 / 175.13)}rem`, top: `${widthRem * (6 / 175.13)}rem` }} aria-hidden="true" />
      <span
        className="absolute grid place-items-center rounded-full border-[0.1875rem] border-black font-[family-name:var(--font-display)] font-bold"
        style={{ width: `${circle}rem`, height: `${circle}rem`, left: 0, top: 0, background: fill, color: inkOn(fill), fontSize: `${widthRem * 0.42}rem` }}
        aria-hidden="true"
      >
        {(name ?? '?').charAt(0).toUpperCase()}
      </span>
    </span>
  )
}
