import { Check, Plus, X } from 'lucide-react'
import { AVATAR_COLORS, CHART, METHODS, STATUS } from '@/lib/colors'
import { MOCK_TODAY } from '@/lib/dates'
import { Box, BoxHead, StatCard } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Avatar, AvatarStack, MemberChip } from '@/components/ui/Avatar'
import { CategoryTag, MethodTag, OwnerPlanPill, Pill, PlanStatusPill, RoleTag, StatusDot, StatusPill } from '@/components/ui/Pill'
import { Input, PasswordInput, Select, Switch, Textarea } from '@/components/ui/Field'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { CopyField, CountBubble, DateBadge, EmptyState, FilterChip, NumberCircle, Pagination, ProgressBar, Skeleton, SkeletonCard, Stepper } from '@/components/ui/Misc'
import { Donut, ForecastBars, Legend } from '@/components/ui/Charts'

const people = [
  { id: '1', name: 'Yasin', avatarColor: AVATAR_COLORS[0], status: 'paid' },
  { id: '2', name: 'Safa', avatarColor: AVATAR_COLORS[1], status: 'pending' },
  { id: '3', name: 'Araf', avatarColor: AVATAR_COLORS[2], status: 'due' },
]

export function KitPage() {
  return (
    <div className="content stack-lg">
      <header className="grid gap-2">
        <h1 className="t-page">UI kit</h1>
        <p className="t-measure">Hidden catalogue. Not linked from the app. Every control lives here once so pages can copy the look.</p>
      </header>

      <Box>
        <BoxHead title="Type" />
        <div className="grid gap-3">
          <p className="t-page">Page title</p>
          <p className="t-section">Section</p>
          <p className="t-card">Card title</p>
          <p className="t-sub">Subhead</p>
          <p className="t-big">৳1,200</p>
          <p className="t-mid">৳300</p>
          <p className="t-meta">Meta line with ৳ Taka check: ৳1100.00</p>
        </div>
      </Box>

      <Box>
        <BoxHead title="Buttons" />
        <div className="row">
          <Button variant="primary-orange" icon={Plus} italic>
            Add plan
          </Button>
          <Button variant="accept" icon={Check}>
            Accept
          </Button>
          <Button variant="reject" icon={X}>
            Reject
          </Button>
          <Button variant="reject-outline">Request leave</Button>
          <Button variant="waive">Waive</Button>
          <Button variant="solo-navy">Set to Due</Button>
          <Button variant="review">Review</Button>
          <Button variant="request">Open request</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="logout">Log out</Button>
          <Button variant="brand">Brand</Button>
          <Button variant="yellow">Today</Button>
          <Button variant="dark">Login</Button>
          <Button busy>Saving</Button>
        </div>
      </Box>

      <Box>
        <BoxHead title="Pills and people" />
        <div className="row">
          {Object.keys(STATUS).map((s) => (
            <StatusPill key={s} status={s} />
          ))}
          {['active', 'trial', 'paused', 'cancelled', 'expired'].map((s) => (
            <PlanStatusPill key={s} status={s} />
          ))}
          <OwnerPlanPill pill={{ key: 'review', label: '2 to review' }} />
          <RoleTag role="owner" />
          <RoleTag role="member" />
          <RoleTag role="reseller" />
          <RoleTag role="rarely" />
          <MethodTag method="bkash" />
          <MethodTag method="nagad" />
          <CategoryTag name="Streaming" />
          <Pill fill="#fff200">Custom</Pill>
        </div>
        <div className="row mt-4">
          <Avatar name="Yasin Bin Ahsan" size="lg" />
          <AvatarStack people={people} showStatus />
          <MemberChip name="Safa Rahman" label="Safa" color={AVATAR_COLORS[1]} status="pending" />
          <StatusDot status="due" />
          <CountBubble count={2} />
          <CountBubble count={12} tone="notify" />
          <DateBadge date={MOCK_TODAY} />
          <NumberCircle>1</NumberCircle>
        </div>
        <div className="row mt-4">
          <ServiceLogo serviceKey="netflix" name="Netflix" size="row" />
          <ServiceLogo serviceKey="canva" name="Canva" size="row" />
          <ServiceLogo serviceKey={null} name="Coursera Plus" size="compact" />
        </div>
      </Box>

      <Box>
        <BoxHead title="Filters, progress, stepper" />
        <div className="row mb-4">
          <FilterChip selected count={6}>
            All
          </FilterChip>
          <FilterChip count={2} alert>
            Needs Review
          </FilterChip>
          <FilterChip>Paid up</FilterChip>
        </div>
        <ProgressBar total={120000} label="demo" parts={[{ key: 'p', value: 90000, fill: STATUS.paid.fill }, { key: 'n', value: 30000, fill: STATUS.pending.fill }]} />
        <div className="mt-6">
          <Stepper current="pending" />
        </div>
        <div className="mt-6">
          <Pagination page={2} pages={4} onPage={() => {}} />
        </div>
      </Box>

      <div className="stat-grid">
        <StatCard label="You spent this month" value="৳3,590" helper="owned plus joined">
          <Legend items={[{ name: 'Owned', value: 291000, fill: CHART.owned }, { name: 'Joined', value: 68000, fill: CHART.joined }]} />
        </StatCard>
        <Box>
          <Donut size={8} label="demo" data={[{ name: 'A', value: 2, fill: CHART.owned }, { name: 'B', value: 1, fill: CHART.joined }]} />
        </Box>
        <Box>
          <ForecastBars
            height={10}
            data={[
              { key: 'n', label: 'Nov', total: 359000, kind: 'this' },
              { key: 'd', label: 'Dec', total: 210000, kind: 'regular' },
              { key: 'j', label: 'Jan', total: 560000, kind: 'yearly' },
            ]}
            colors={{ this: CHART.thisMonth, regular: CHART.regular, yearly: CHART.yearly }}
          />
        </Box>
      </div>

      <Box>
        <BoxHead title="Fields" />
        <div className="grid gap-5 md:grid-cols-2">
          <Input label="Email" defaultValue="yasin@example.com" />
          <Input label="Broken" error="Enter an email address like name@example.com." />
          <PasswordInput />
          <Select label="Method" defaultValue="bkash" options={Object.entries(METHODS).map(([value, m]) => ({ value, label: m.label }))} />
          <Textarea label="Note" rows={2} defaultValue="Pay by the 4th, please." />
          <div className="row-between">
            <span className="t-label">Email reminders</span>
            <Switch checked label="Email reminders" onChange={() => {}} />
          </div>
          <CopyField label="Transaction ID" value="8K2L9QX4" />
        </div>
      </Box>

      <Box>
        <BoxHead title="Empty, skeleton" />
        <EmptyState title="Inbox empty" helper="New invites show up here." />
        <Skeleton className="mt-4 h-8 w-1/2" />
        <SkeletonCard />
      </Box>
    </div>
  )
}
