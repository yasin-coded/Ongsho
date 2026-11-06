import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import { cx } from './Box'

/**
 * Native <dialog> opened with showModal(): focus is trapped, Esc closes,
 * and focus returns to the opener on close.
 */
export function Modal({ open, onClose, title, subtitle, wide, children, footer }) {
  const ref = useRef(null)
  const bodyRef = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  useEffect(() => {
    if (!open) return
    const body = bodyRef.current
    if (!body) return
    const scrollEl = body.querySelector('.modal__form-scroll') ?? body

    const syncOverflow = () => {
      scrollEl.classList.toggle('modal__scroll--overflow', scrollEl.scrollHeight > scrollEl.clientHeight + 1)
    }

    let scrollTimer
    const onScroll = () => {
      scrollEl.classList.add('modal__scroll--active')
      clearTimeout(scrollTimer)
      scrollTimer = window.setTimeout(() => scrollEl.classList.remove('modal__scroll--active'), 700)
    }

    syncOverflow()
    const ro = new ResizeObserver(syncOverflow)
    ro.observe(scrollEl)
    const inner = scrollEl.firstElementChild
    if (inner instanceof Element) ro.observe(inner)
    scrollEl.addEventListener('scroll', onScroll, { passive: true })

    return () => {
      ro.disconnect()
      scrollEl.removeEventListener('scroll', onScroll)
      clearTimeout(scrollTimer)
      scrollEl.classList.remove('modal__scroll--overflow', 'modal__scroll--active')
    }
  }, [open, children])

  return (
    <dialog
      ref={ref}
      className={cx('modal', wide && 'modal--wide')}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
    >
      {open && (
        <div className="modal__inner">
          <div className="modal__head">
            <div className="grid gap-1">
              <h2 id={titleId} className="t-card">
                {title}
              </h2>
              {subtitle && <p className="t-meta">{subtitle}</p>}
            </div>
            <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
              <X aria-hidden="true" className="size-5" />
            </button>
          </div>
          <div ref={bodyRef} className="modal__body modal__scroll">
            {children}
          </div>
          {footer && <div className="modal__footer row justify-end">{footer}</div>}
        </div>
      )}
    </dialog>
  )
}
