import { useEffect, useRef } from 'react'
import { NavLink, useLocation } from 'react-router'
import { X } from 'lucide-react'
import { CountBubble } from '@/components/ui/Misc'

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function MobileNavDrawer({ open, onClose, nav, counts }) {
  const panelRef = useRef(null)
  const { pathname } = useLocation()

  useEffect(() => {
    onClose()
  }, [pathname, onClose])

  useEffect(() => {
    if (!open) return undefined
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && panelRef.current) {
        const nodes = [...panelRef.current.querySelectorAll(FOCUSABLE)]
        if (!nodes.length) return
        const first = nodes[0]
        const last = nodes[nodes.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    const t = window.setTimeout(() => panelRef.current?.querySelector(FOCUSABLE)?.focus(), 0)
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener('keydown', onKey)
      window.clearTimeout(t)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="nav-drawer" role="presentation">
      <button type="button" className="nav-drawer__backdrop" aria-label="Close menu" onClick={onClose} />
      <div ref={panelRef} className="nav-drawer__panel" role="dialog" aria-modal="true" aria-label="Main menu">
        <div className="nav-drawer__head">
          <p className="font-[family-name:var(--font-display)] text-[1.1rem] font-bold uppercase">Menu</p>
          <button type="button" className="icon-btn nav-drawer__close" onClick={onClose} aria-label="Close menu">
            <X aria-hidden="true" className="size-5" />
          </button>
        </div>
        <nav aria-label="All destinations" className="nav-drawer__nav">
          {nav.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="nav-drawer__link" onClick={onClose}>
              <item.icon aria-hidden="true" />
              <span>{item.label}</span>
              {item.count && <CountBubble count={counts?.[item.count]} tone={item.tone} label={`${counts?.[item.count]} ${item.countLabel}`} />}
            </NavLink>
          ))}
        </nav>
        <p className="nav-drawer__foot">Payments happen outside Ongsho. Ongsho only keeps the record.</p>
      </div>
    </div>
  )
}
