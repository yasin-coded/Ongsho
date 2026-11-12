import { NavLink, Outlet, useLocation } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CalendarDays, House, Layers, UserRound, Users } from 'lucide-react'
import Wordmark from '@/assets/media/logo-monochrome.svg?react'
import { SVG_SIZES } from '@/lib/services'
import { getNavCounts, snapshotNavCounts } from '@/api/dashboard'
import { CountBubble, OutsideNote } from '@/components/ui/Misc'
import { useEffect } from 'react'

const NAV = [
  { to: '/app', label: 'Home', short: 'Home', icon: House, end: true },
  { to: '/app/plans', label: 'My Plans', short: 'My Plans', icon: Layers, count: 'reviews', countLabel: 'payments to review' },
  { to: '/app/shared', label: 'Shared Plans', short: 'Shared', icon: Users, count: 'dues', countLabel: 'open dues' },
  { to: '/app/calendar', label: 'Calendar', short: 'Calendar', icon: CalendarDays },
  { to: '/app/notifications', label: 'Notifications', short: 'Alerts', icon: Bell, count: 'unread', countLabel: 'unread', tone: 'notify' },
  { to: '/app/profile', label: 'Profile', short: 'Profile', icon: UserRound, desktopOnly: true },
]

export function AppShell() {
  const queryClient = useQueryClient()
  const { data: counts } = useQuery({
    queryKey: ['nav-counts'],
    queryFn: getNavCounts,
    refetchOnMount: 'always',
  })
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  useEffect(() => {
    const snap = snapshotNavCounts()
    if (snap) queryClient.setQueryData(['nav-counts'], snap)
  }, [pathname, queryClient])

  return (
    <div className="shell">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-white focus:p-3 focus:font-bold">
        Skip to content
      </a>
      <aside className="sidebar">
        <NavLink to="/" className="sidebar__brand" aria-label="Ongsho home">
          <Wordmark className="media" style={{ width: `${SVG_SIZES.wordmark.w}px` }} aria-hidden="true" />
        </NavLink>
        <nav aria-label="Main" className="sidebar__nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="sidebar__link">
              <item.icon aria-hidden="true" />
              <span>{item.label}</span>
              {item.count && <CountBubble count={counts?.[item.count]} tone={item.tone} label={`${counts?.[item.count]} ${item.countLabel}`} />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__foot">Payments happen outside Ongsho. Ongsho only keeps the record.</div>
      </aside>

      <div className="shell__main">
        <main id="main" className="content">
          <div key={pathname} className="content-route">
            <Outlet />
          </div>
          <OutsideNote className="mobile-foot border-t-[0.125rem] border-dashed border-[var(--color-dash)] pt-4 text-center" />
        </main>
      </div>

      <nav aria-label="Main" className="bottombar">
        {NAV.filter((n) => !n.desktopOnly).map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className="bottombar__link">
            <item.icon aria-hidden="true" />
            <span>{item.short}</span>
            {item.count && <CountBubble count={counts?.[item.count]} tone={item.tone} label={`${counts?.[item.count]} ${item.countLabel}`} />}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
