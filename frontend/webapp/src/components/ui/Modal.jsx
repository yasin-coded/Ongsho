import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import { cx } from './Box'

/**
 * Native <dialog> opened with showModal(): focus is trapped, Esc closes,
 * and focus returns to the opener on close.
 */
export function Modal({ open, onClose, title, subtitle, wide, children, footer }) {
  const ref = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

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
          <div className="modal__body">{children}</div>
          {footer && <div className="modal__footer row justify-end">{footer}</div>}
        </div>
      )}
    </dialog>
  )
}
