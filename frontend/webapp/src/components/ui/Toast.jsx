import { useCallback, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { ToastContext } from './toast-context'

const EDGE = { paid: '#2fd600', pending: '#fff200', due: '#ff1a1a', info: '#14b3f2', waived: '#19c8f0' }

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const seq = useRef(0)

  const dismiss = useCallback((id) => setItems((list) => list.filter((t) => t.id !== id)), [])
  const toast = useCallback(
    (message, tone = 'paid') => {
      seq.current += 1
      const id = seq.current
      setItems((list) => [...list.slice(-2), { id, message, tone }])
      setTimeout(() => dismiss(id), 5000)
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="toast">
            <span className="toast__edge" style={{ background: EDGE[t.tone] ?? EDGE.info }} aria-hidden="true" />
            <p className="flex-1 font-bold">{t.message}</p>
            <button type="button" className="grid size-8 flex-none place-items-center rounded-md" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <X aria-hidden="true" className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
