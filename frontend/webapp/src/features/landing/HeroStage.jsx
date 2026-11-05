import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import Hero from '@/assets/media/hero.svg?react'
import { SERVICES, SVG_SIZES } from '@/lib/services'
import { TIME_ZONE } from '@/lib/dates'

const ROW = [
  { key: 'spotify', caption: 'SPOTIFY' },
  { key: 'youtube', caption: 'YOUTUBE' },
  { key: 'apple_music', caption: 'APPLE MUSIC' },
  { key: 'netflix', caption: 'NETFLIX' },
  { key: 'claude', caption: 'CLAUDE' },
  { key: 'chatgpt', caption: 'CHATGPT' },
]

/** Positions in hero.svg's own viewBox units (0 0 1440 760). */
const ISLAND = { timeX: 712, timeY: 206.55, dotX: 803, dotR: 6.5 }
const ORIGIN = { x: 720, y: 672, r: 9, stubFrom: 632 }
/** Narrow hero is zoomed, so the desktop stub (40 units) shrinks to a sliver. */
const NARROW_QUERY = '(max-width: 30rem)'
const NARROW_ORIGIN_Y = 736
/** Top of the main circle inside each logo file (175.13 × 168.13). */
const LOGO_TOP = { x: 81.32, y: 0.5 }

const clockFmt = new Intl.DateTimeFormat('en-US', { timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true })

function useDhakaClock() {
  const [now, setNow] = useState(() => clockFmt.format(new Date()))
  useEffect(() => {
    const id = setInterval(() => setNow(clockFmt.format(new Date())), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

export function HeroStage() {
  const time = useDhakaClock()
  const stageRef = useRef(null)
  const frameRef = useRef(null)
  const logoRefs = useRef([])
  const [lines, setLines] = useState({ w: 0, h: 0, paths: [] })
  const [hubViewY, setHubViewY] = useState(ORIGIN.y)

  useLayoutEffect(() => {
    const stage = stageRef.current
    const frame = frameRef.current
    if (!stage || !frame) return undefined

    const measure = () => {
      const s = stage.getBoundingClientRect()
      const f = frame.getBoundingClientRect()
      const scale = f.width / SVG_SIZES.hero.w
      const yHub = window.matchMedia(NARROW_QUERY).matches ? NARROW_ORIGIN_Y : ORIGIN.y
      const x0 = f.left - s.left + ORIGIN.x * scale
      const y0 = f.top - s.top + yHub * scale
      setHubViewY((prev) => (prev === yHub ? prev : yHub))
      const logos = []
      logoRefs.current.forEach((el, i) => {
        if (!el || !ROW[i]) return
        const r = el.getBoundingClientRect()
        const fig = el.closest('figure')
        const figR = fig?.getBoundingClientRect() ?? r
        const k = r.width / SVG_SIZES.logo.w
        const left = r.left - s.left
        logos.push({
          key: ROW[i].key,
          color: SERVICES[ROW[i].key].color,
          x: left + LOGO_TOP.x * k,
          top: r.top - s.top + LOGO_TOP.y * k,
          bottom: figR.bottom - s.top,
          left,
          right: r.right - s.left,
          midX: left + r.width / 2,
        })
      })
      // A line from the hub to a wrapped logo runs through the icon above it,
      // and the dash phase in that short gap is often the empty half. Start
      // the lower segment at the bottom of the icon it would pass through.
      const paths = logos.map((logo) => {
        const above = logos
          .filter(
            (other) =>
              other !== logo &&
              other.bottom <= logo.top + 1 &&
              logo.midX >= other.left &&
              logo.midX <= other.right,
          )
          .sort((a, b) => b.bottom - a.bottom)[0]
        if (!above) return { key: logo.key, color: logo.color, d: `M ${x0} ${y0} Q ${logo.x} ${y0} ${logo.x} ${logo.top}` }
        return { key: logo.key, color: logo.color, d: `M ${logo.x} ${above.bottom} L ${logo.x} ${logo.top}` }
      })
      setLines({ w: s.width, h: s.height, paths })
    }

    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(stage)
    ro.observe(frame)
    window.addEventListener('resize', measure)
    const narrow = window.matchMedia(NARROW_QUERY)
    narrow.addEventListener('change', measure)
    document.fonts?.ready.then(measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
      narrow.removeEventListener('change', measure)
    }
  }, [])

  return (
    <div className="stage" ref={stageRef}>
      <svg className="stage__lines" width={lines.w} height={lines.h} aria-hidden="true">
        {lines.paths.map((p) => (
          <path key={p.key} d={p.d} stroke={p.color} />
        ))}
      </svg>

      <section className="bleed hero" aria-label="Ongsho">
        <div className="bleed__frame" ref={frameRef}>
          <Hero className="media bleed__art" role="img" aria-label="A phone showing the Ongsho monogram" />
          <svg className="hero__overlay" viewBox={`0 0 ${SVG_SIZES.hero.w} ${SVG_SIZES.hero.h}`} aria-hidden="true">
            <text
              x={ISLAND.timeX}
              y={ISLAND.timeY}
              textAnchor="middle"
              dominantBaseline="central"
              fill="#fdfbcf"
              fontFamily="Bahnschrift, system-ui, sans-serif"
              fontWeight="700"
              fontSize="15"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {time}
            </text>
            <circle className="blink" cx={ISLAND.dotX} cy={ISLAND.timeY} r={ISLAND.dotR} fill="#a2ff00" />
            <line x1={ORIGIN.x} y1={ORIGIN.stubFrom} x2={ORIGIN.x} y2={hubViewY} stroke="#274f00" strokeWidth="4" strokeDasharray="9 9" strokeLinecap="round" />
            <circle cx={ORIGIN.x} cy={hubViewY} r={ORIGIN.r} fill="#274f00" />
          </svg>
          <span className="sr-only">Live time, Dhaka</span>
        </div>
      </section>

      <div className="logo-row">
        {ROW.map((item, i) => {
          const { Logo, name } = SERVICES[item.key]
          return (
            <figure key={item.key} className="logo-row__item">
              <span ref={(el) => (logoRefs.current[i] = el)} className="block">
                <Logo className="media block" role="img" aria-label={name} />
              </span>
              <figcaption>{item.caption}</figcaption>
            </figure>
          )
        })}
      </div>
      <p className="so-much">
        <span className="so-much__amp">&amp;</span>
        <span className="so-much__more">SO MUCHHHHHHH MORE</span>
      </p>
    </div>
  )
}
