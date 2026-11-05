import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { BarChart3, Bell, Check, CheckCheck, CreditCard, Mail, Menu, Plus, Users, X } from 'lucide-react'
import ChatPhone from '@/assets/media/main-chat.svg?react'
import FooterShape from '@/assets/media/footer.svg?react'
import Wordmark from '@/assets/media/logo-monochrome.svg?react'
import { SVG_SIZES } from '@/lib/services'
import { useAuth } from '@/auth/auth-context'
import { Avatar } from '@/components/ui/Avatar'
import { HeroStage } from './HeroStage'

function LandingHeader() {
  const { isAuthed, session } = useAuth()
  const [solid, setSolid] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const links = [
    { href: '#top', label: 'Home' },
    { href: '#how-it-works', label: 'How it works?' },
    { href: '#about', label: 'About' },
  ]

  return (
    <header className="l-header" data-solid={solid || open}>
      <div className="l-header__bar">
        <a href="#top" aria-label="Ongsho, back to top" className="w-fit rounded-md">
          <Wordmark className="media" style={{ width: `${SVG_SIZES.wordmark.w}px` }} aria-hidden="true" />
        </a>
        <nav aria-label="Page sections" className="l-header__links">
          {links.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>
        <div className="l-header__right">
          {isAuthed ? (
            <Link to="/app" className="neo-btn btn-dark neo-btn--sm">
              Dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="neo-btn btn-dark neo-btn--sm">
                Login
              </Link>
              <Link to="/register" className="neo-btn btn-accept neo-btn--sm">
                Get started
              </Link>
            </>
          )}
          {isAuthed && (
            <Link to="/app/profile" aria-label="Your profile" className="rounded-full">
              <Avatar name={session.user.name} color={session.user.avatarColor} size="md" decorative />
            </Link>
          )}
          <button type="button" className="icon-btn l-header__menu" aria-expanded={open} aria-controls="landing-menu" aria-label={open ? 'Close menu' : 'Open menu'} onClick={() => setOpen((v) => !v)}>
            {open ? <X aria-hidden="true" className="size-5" /> : <Menu aria-hidden="true" className="size-5" />}
          </button>
        </div>
      </div>
      {open && (
        <nav id="landing-menu" aria-label="Page sections" className="l-header__panel">
          {links.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)}>
              {l.label}
            </a>
          ))}
          {!isAuthed && (
            <>
              <Link to="/register" className="l-header__panel-cta" onClick={() => setOpen(false)}>
                Get started
              </Link>
              <Link to="/login" className="l-header__panel-cta l-header__panel-cta--ghost" onClick={() => setOpen(false)}>
                Login
              </Link>
            </>
          )}
        </nav>
      )}
    </header>
  )
}

const STEPS = [
  { title: 'Create a plan', icon: Plus, tile: '#ff00ff', body: 'Pick a service, set the price and seats, and choose Owner if you pay the provider, or Reseller if you only collect.' },
  { title: 'Invite by email', icon: Mail, tile: '#14b3f2', body: 'Everyone has their own account. New people get a sign-up page from the invite and land on their dashboard.' },
  {
    title: 'Pay and track',
    icon: Check,
    tile: '#2fd600',
    body: (
      <>
        Members enter a transaction ID, the owner confirms it, and the status moves from <strong className="text-[#d40000]">Due</strong> to{' '}
        <strong className="bg-[#fff200] px-1">Pending</strong> to <strong className="text-[#1d7a00]">Paid</strong>.
      </>
    ),
  },
]

const FEATURES = [
  { title: 'Shared plans with seats', icon: Users, tile: '#ff00ff', body: 'Set the price, split the seats, and see who is in. Owner mode takes a seat for you, Reseller mode only collects.' },
  { title: 'Dues with proof', icon: CreditCard, tile: '#e87400', body: 'Each seat has one status: Due, Pending, Paid or Waived. Members add a transaction ID instead of posting screenshots.' },
  { title: 'Owner reviews payments', icon: CheckCheck, tile: '#00ff00', body: 'Confirm or reject a transaction ID in one click. A rejected due simply goes back to Due.' },
  { title: 'Reminders that arrive', icon: Bell, tile: '#00ff8b', body: 'In-app notifications and emails for due dates, reviews, invites and leave requests, for owners, members and resellers.' },
  { title: 'Know where your money goes', icon: BarChart3, tile: '#ff9700', body: 'One dashboard for what you spend each month, split between plans you own and plans you joined, with a six-month forecast.' },
]

function FeatureCard({ index, title, icon: Icon, tile, children, titleInline }) {
  if (titleInline) {
    return (
      <article className="neo-box neo-box--roomy grid content-start gap-4 feature-card--title-inline">
        <div className="feature-card__head">
          <h3 className="t-card feature-card__title">{title}</h3>
          <span className="icon-tile" style={{ background: tile }} aria-hidden="true">
            <Icon />
          </span>
        </div>
        <p>{children}</p>
      </article>
    )
  }

  return (
    <article className="neo-box neo-box--roomy grid content-start gap-4">
      <div className="flex items-start justify-between gap-4">
        {index ? <span className="num-circle">{index}</span> : <span />}
        <span className="icon-tile" style={{ background: tile }} aria-hidden="true">
          <Icon />
        </span>
      </div>
      <h3 className="t-card">{title}</h3>
      <p>{children}</p>
    </article>
  )
}

export function LandingPage() {
  return (
    <div className="landing" id="top">
      <LandingHeader />
      <main>
        <HeroStage />

        <section className="l-section" aria-labelledby="ledger-title">
          <div className="chat-grid">
            <ChatPhone className="media chat-phone" role="img" aria-label="A group chat where friends argue about who paid for Netflix" />
            <div className="ledger-copy grid gap-6" lang="en">
              <h2 id="ledger-title" className="l-display l-ledger-title">
                The group chat is <span className="l-ledger-not">not</span> a ledger.
              </h2>
              <p className="l-lede">
                Screenshots, “I’ll send it tomorrow”, and nobody remembers who paid for November. <strong className="text-[#274f00]">Ongsho</strong> gives every person one clear status per plan.
              </p>
            </div>
          </div>
        </section>

        <section className="l-section l-section--features" id="how-it-works" aria-labelledby="how-title about-title">
          <h2 id="how-title" className="l-display l-section__title mb-10 text-[#274f00]">
            Three Plans. No Spreadsheet.
          </h2>
          <div className="feature-grid feature-grid--steps">
            {STEPS.map((s, i) => (
              <FeatureCard key={s.title} index={i + 1} title={s.title} icon={s.icon} tile={s.tile}>
                {s.body}
              </FeatureCard>
            ))}
          </div>

          <div className="l-features-block" id="about">
            <h2 id="about-title" className="l-display l-section__title mb-10 text-[#ff0000]">
              Built for people who split plans.
            </h2>
            <div className="feature-grid feature-grid--about">
              {FEATURES.map((f) => (
                <FeatureCard key={f.title} title={f.title} icon={f.icon} tile={f.tile} titleInline>
                  {f.body}
                </FeatureCard>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="l-footer">
        <div className="l-footer__fill" aria-hidden="true" />
        <FooterShape className="l-footer__art" aria-hidden="true" />
        <div className="l-footer__body">
          <Wordmark className="media l-footer__wordmark" role="img" aria-label="Ongsho" />
          <nav aria-label="Footer" className="l-footer__links">
            <a href="#top">Home</a>
            <a href="#how-it-works">How it works?</a>
            <a href="#about">About</a>
          </nav>
          <div className="l-footer__notes">
            <p className="font-bold">Payments happen outside Ongsho. Ongsho only keeps the record.</p>
            <p>2026 Ongsho. Built by Yasin Bin Ahsan.</p>
          </div>
          <p className="l-footer__close l-shadow">
            <span className="l-footer__close-lead">MANAGE ALL SUBSCRIPTIONS</span>
            <span className="l-footer__close-sub">IN ONE PLACE</span>
          </p>
        </div>
      </footer>
    </div>
  )
}
