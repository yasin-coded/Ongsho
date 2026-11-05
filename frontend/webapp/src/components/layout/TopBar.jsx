import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { getMe } from '@/api/accounts'
import { Avatar } from '@/components/ui/Avatar'
import { LinkButton } from '@/components/ui/Button'

export function TopBar({ title, subtitle, tools = true, actions, breadcrumb, lead }) {
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe })
  const navigate = useNavigate()
  const [q, setQ] = useState('')

  return (
    <header>
      {breadcrumb && (
        <nav aria-label="Breadcrumb" className="breadcrumb">
          {breadcrumb.map((b, i) => (
            <span key={b.label} className="contents">
              {i > 0 && <span aria-hidden="true">/</span>}
              {b.to ? <Link to={b.to}>{b.label}</Link> : <span aria-current="page">{b.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="topbar">
        <div className="topbar__lead">
          {lead}
          <div className="topbar__titles">
            <h1 className="t-page truncate">{title}</h1>
            {subtitle && <p className="t-measure line-clamp-2 md:line-clamp-1">{subtitle}</p>}
          </div>
        </div>
        <div className="topbar__tools">
          {tools && (
            <form
              role="search"
              className="search"
              onSubmit={(e) => {
                e.preventDefault()
                navigate(`/app/plans?q=${encodeURIComponent(q.trim())}`)
              }}
            >
              <Search aria-hidden="true" />
              <label htmlFor="top-search" className="sr-only">
                Search plans
              </label>
              <input id="top-search" type="search" placeholder="Search plans" value={q} onChange={(e) => setQ(e.target.value)} />
            </form>
          )}
          {tools && (
            <LinkButton to="/app/plans/new" variant="primary-orange" icon={Plus} italic className="topbar__add" aria-label="Add plan">
              <span className="topbar__add-label">Add plan</span>
            </LinkButton>
          )}
          {actions}
          <Link to="/app/profile" aria-label="Your profile" className="topbar__profile rounded-full">
            {me ? <Avatar name={me.name} color={me.avatarColor} size="md" decorative /> : <span className="avatar avatar--md bg-white" />}
          </Link>
        </div>
      </div>
    </header>
  )
}
