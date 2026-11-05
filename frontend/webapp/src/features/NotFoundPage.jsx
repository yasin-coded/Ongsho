import { Link } from 'react-router'
import { Compass } from 'lucide-react'
import { EmptyState } from '@/components/ui/Misc'
import { LinkButton } from '@/components/ui/Button'
import { TopBar } from '@/components/layout/TopBar'

export function NotFoundPage({ inApp = false }) {
  const home = inApp ? '/app' : '/'
  const body = (
    <EmptyState icon={Compass} title="This page is not here" helper="The link is wrong, or the plan was archived and hidden.">
      <LinkButton to={home} variant="accept">
        {inApp ? 'Back to Home' : 'Back to Ongsho'}
      </LinkButton>
    </EmptyState>
  )
  if (!inApp) {
    return (
      <div className="grid min-h-dvh place-items-center px-4">
        <div className="w-full max-w-[32rem]">{body}</div>
      </div>
    )
  }
  return (
    <div className="stack">
      <TopBar title="Not found" subtitle="Nothing lives at this address." tools={false} />
      {body}
      <p className="text-center">
        <Link to="/app/plans" className="text-link">
          My Plans
        </Link>
      </p>
    </div>
  )
}
