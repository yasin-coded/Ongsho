import { Link } from 'react-router'
import Wordmark from '@/assets/media/logo-monochrome.svg?react'
import { SVG_SIZES } from '@/lib/services'

export function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="grid min-h-dvh grid-rows-[auto_1fr]">
      <header className="border-b-[0.1875rem] border-black bg-[var(--color-brand)] px-6 py-4">
        <Link to="/" aria-label="Ongsho home" className="block w-fit rounded-md">
          <Wordmark className="media" style={{ width: `${SVG_SIZES.wordmark.w}px` }} aria-hidden="true" />
        </Link>
      </header>
      <main className="grid place-items-center px-4 py-12">
        <div className="w-full max-w-[28rem]">
          <section className="neo-box neo-box--roomy grid gap-6">
            <div className="grid gap-2">
              <h1 className="t-section">{title}</h1>
              {subtitle && <p>{subtitle}</p>}
            </div>
            {children}
          </section>
          {footer && <div className="mt-6 text-center">{footer}</div>}
        </div>
      </main>
    </div>
  )
}
