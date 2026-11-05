import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Check, Plus, X } from 'lucide-react'
import { createSubscription, getPlanForm, updateSubscription } from '@/api/plans'
import { getCategories, getServiceNames } from '@/api/catalog'
import { METHODS, METHOD_KEYS } from '@/lib/colors'
import { MOCK_TODAY, dayOfMonth, fmtShort } from '@/lib/dates'
import { formatBDT, formatRate, formatUSD, parseTaka, splitExact, usdToPaisa } from '@/lib/money'
import { cycleLabel, firstBillDate, nextDueDate, perCycleLabel } from '@/mocks/schedule'
import { useAction } from '@/hooks/useAction'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Field'
import { LockedNote, RoleTag } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { NumberCircle, SkeletonCard } from '@/components/ui/Misc'
import { Loadable } from '@/features/common/PlanBits'

const EMPTY = {
  mode: 'owner',
  serviceName: '',
  planName: '',
  categoryId: '',
  price: '',
  currency: 'BDT',
  rate: '122',
  cycleUnit: 'month',
  cycleCount: '2',
  customUnit: 'month',
  startDate: MOCK_TODAY,
  trialEnd: '',
  renewal: 'auto',
  endDate: '',
  seats: '2',
  split: 'equal',
  method: 'bkash',
  note: '',
  invites: [],
}

function cycleOf(form) {
  if (form.cycleUnit === 'custom') return { unit: form.customUnit || 'month', count: Number(form.cycleCount) || 1 }
  return { unit: form.cycleUnit, count: 1 }
}

function chargePaisa(form) {
  const price = parseTaka(form.price)
  if (!(price > 0)) return 0
  if (form.currency === 'USD') {
    const rate = parseTaka(form.rate)
    if (!(rate > 0)) return 0
    return usdToPaisa(price, rate)
  }
  return price
}

function nextRenewalOf(form) {
  if (!form.startDate) return null
  const plan = {
    startDate: form.startDate,
    trialEnd: form.trialEnd || null,
    cycle: cycleOf(form),
    skipDates: [],
    pausedOn: null,
    cancelledOn: null,
    renewal: form.renewal,
    endDate: form.endDate || null,
    anchorDay: dayOfMonth(form.trialEnd || form.startDate),
  }
  return nextDueDate(plan, MOCK_TODAY) ?? firstBillDate(plan)
}

function Card({ n, title, children }) {
  return (
    <Box>
      <div className="mb-5 row gap-3">
        <NumberCircle>{n}</NumberCircle>
        <h2 className="t-card">{title}</h2>
      </div>
      {children}
    </Box>
  )
}

function Preview({ form, names, editing }) {
  const catalog = names.find((s) => s.name.toLowerCase() === form.serviceName.trim().toLowerCase())
  const cycle = cycleOf(form)
  const amount = chargePaisa(form)
  const seats = Math.max(1, Number(form.seats) || 1)
  const ownerTakes = form.mode === 'owner' && (seats > 1 || form.invites.length > 0)
  const per = amount ? splitExact(amount, form.mode === 'reseller' ? seats : Math.max(ownerTakes ? membersCount(form) : 1, 1), 0)[0] : 0
  const next = nextRenewalOf(form)
  const usd = form.currency === 'USD' && parseTaka(form.price) > 0 && parseTaka(form.rate) > 0
  return (
    <Box className="lg:sticky lg:top-6">
      <BoxHead title="Live preview" />
      <div className="grid gap-4">
        <div className="row gap-3">
          <ServiceLogo serviceKey={catalog?.serviceKey} name={form.serviceName || form.planName || 'Plan'} size="compact" />
          <div className="grid min-w-0 gap-1">
            <p className="t-sub truncate">{form.planName || 'Untitled plan'}</p>
            <RoleTag role={form.mode === 'reseller' ? 'reseller' : seats > 1 || form.invites.length ? 'owner' : 'solo'} />
            <p className="t-meta">
              {cycleLabel(cycle)}
              {next ? ` · renews ${fmtShort(next)}` : ''}
              {` · ${seats} seat${seats === 1 ? '' : 's'}`}
            </p>
          </div>
        </div>
        <dl className="dashed-rows">
          <div className="row-between py-2.5">
            <dt className="t-label">Price</dt>
            <dd className="t-num text-right">
              {usd ? `${formatUSD(parseTaka(form.price))} × ${formatRate(parseTaka(form.rate))} = ${formatBDT(amount)}` : amount ? formatBDT(amount) : '—'}
            </dd>
          </div>
          <div className="row-between py-2.5">
            <dt className="t-label">Each seat</dt>
            <dd className="t-num">{amount ? formatBDT(per, { trim: true }) : '—'}</dd>
          </div>
          {form.mode === 'owner' ? (
            <div className="row-between py-2.5">
              <dt className="t-label">Your seat</dt>
              <dd>starts as Paid</dd>
            </div>
          ) : (
            <div className="row-between py-2.5">
              <dt className="t-label">You take no seat</dt>
              <dd>Reseller</dd>
            </div>
          )}
          <div className="row-between py-2.5">
            <dt className="t-label">Members pay</dt>
            <dd className="t-num">{amount ? `${formatBDT(per, { trim: true })} ${perCycleLabel(cycle)}` : '—'}</dd>
          </div>
          <div className="row-between py-2.5">
            <dt className="t-label">Recommended method</dt>
            <dd>{METHODS[form.method]?.label}</dd>
          </div>
        </dl>
        {!editing && <p className="t-meta">Nothing is charged until the first due date.</p>}
      </div>
    </Box>
  )
}

function membersCount(form) {
  return (form.mode === 'owner' ? 1 : 0) + form.invites.length
}

function PlanForm({ initial, editing, planId }) {
  const navigate = useNavigate()
  const [form, setForm] = useState(initial)
  const [email, setEmail] = useState('')
  const [shares, setShares] = useState({})
  const cats = useQuery({ queryKey: ['categories'], queryFn: getCategories })
  const names = useQuery({ queryKey: ['service-names'], queryFn: getServiceNames })
  const save = useAction(
    (payload) => (editing ? updateSubscription(planId, payload) : createSubscription(payload)),
    {
      onSuccess: (data) => navigate(`/app/plans/${data.id}`),
      toastMessage: editing ? 'Plan details saved.' : 'Plan created. Invites are on their way.',
    },
  )

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const amount = chargePaisa(form)
  const people = useMemo(() => {
    const list = []
    if (form.mode === 'owner') list.push({ key: 'owner', label: 'You (owner seat)' })
    form.invites.forEach((e) => list.push({ key: e, label: e }))
    return list
  }, [form.mode, form.invites])
  const customTotal = people.reduce((a, p) => a + (parseTaka(shares[p.key]) ?? 0), 0)
  const customOk = form.split !== 'custom' || (amount > 0 && customTotal === amount)
  const next = nextRenewalOf(form)

  useEffect(() => {
    const first = document.querySelector('[aria-invalid="true"]')
    first?.focus()
  }, [save.fields])

  const addInvite = () => {
    const clean = email.trim().toLowerCase()
    if (!clean || form.invites.includes(clean)) return
    set({ invites: [...form.invites, clean] })
    setEmail('')
  }

  const submit = () => {
    const payload = {
      ...form,
      price: Number(form.price),
      rate: Number(form.rate),
      cycleCount: Number(form.cycleCount),
      seats: Number(form.seats),
      trialEnd: form.trialEnd || null,
      endDate: form.renewal === 'fixed' ? form.endDate : null,
      customShares: Object.fromEntries(people.map((p) => [p.key, parseTaka(shares[p.key]) ?? 0])),
      customTotalOk: customOk,
    }
    save.run(payload)
  }

  const f = save.fields
  const serviceList = names.data ?? []

  return (
    <form
      className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(18rem,1fr)]"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <div className="stack">
        <Card n={1} title="How do you pay for it?">
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { value: 'owner', title: 'Owner', body: 'You pay the provider. You take one seat, and you can hand the plan to another member later.' },
              { value: 'reseller', title: 'Reseller', body: 'You only collect from others. You take no seat, and ownership cannot be transferred.' },
            ].map((o) => (
              <label key={o.value} className="radio-card">
                <input type="radio" name="mode" value={o.value} checked={form.mode === o.value} disabled={editing} onChange={() => set({ mode: o.value })} />
                <span className="t-sub">{o.title}</span>
                <span className="t-meta">{o.body}</span>
              </label>
            ))}
          </div>
          <div className="mt-4">
            <LockedNote>You cannot change this after the plan is created.</LockedNote>
          </div>
        </Card>

        <Card n={2} title="What is the plan for?">
          <div className="grid gap-5">
            <div>
              <p className="field__label mb-2">Service name</p>
              <div className="row gap-2">
                {serviceList.map((s) => (
                  <button key={s.id} type="button" className="chip" aria-pressed={form.serviceName === s.name} onClick={() => set({ serviceName: s.name, planName: form.planName || `${s.name}` })}>
                    {s.name}
                  </button>
                ))}
              </div>
              <Input className="mt-3" label="Service name" hideLabel value={form.serviceName} onChange={(e) => set({ serviceName: e.target.value })} error={f.serviceName} placeholder="Or type a name" />
            </div>
            <Input label="Plan name" value={form.planName} onChange={(e) => set({ planName: e.target.value })} error={f.planName} placeholder='For example "Netflix Premium"' />
            <Select
              label="Category"
              value={form.categoryId}
              placeholder="Pick a category"
              onChange={(e) => set({ categoryId: e.target.value })}
              options={(cats.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
              error={f.categoryId}
              help="You can add your own in Profile."
            />
          </div>
        </Card>

        <Card n={3} title="What does it cost?">
          <div className="grid gap-5 sm:grid-cols-2">
            <Input label={form.currency === 'USD' ? 'Price ($)' : 'Price (৳)'} inputMode="decimal" numeric value={form.price} onChange={(e) => set({ price: e.target.value })} error={f.price} locked={editing} />
            <Select label="Currency" value={form.currency} disabled={editing} onChange={(e) => set({ currency: e.target.value })} options={[{ value: 'BDT', label: 'BDT' }, { value: 'USD', label: 'USD' }]} />
            <fieldset className="sm:col-span-2">
              <legend className="field__label mb-2">Billed</legend>
              <div className="row gap-2">
                {['week', 'month', 'year', 'custom'].map((u) => (
                  <button key={u} type="button" className="chip" aria-pressed={form.cycleUnit === u} disabled={editing} onClick={() => set({ cycleUnit: u })}>
                    {u === 'week' ? 'Weekly' : u === 'month' ? 'Monthly' : u === 'year' ? 'Yearly' : 'Custom'}
                  </button>
                ))}
              </div>
              {form.cycleUnit === 'custom' && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Input label="Every" inputMode="numeric" value={form.cycleCount} onChange={(e) => set({ cycleCount: e.target.value })} error={f.cycleCount} locked={editing} />
                  <Select label="Unit" value={form.customUnit} disabled={editing} onChange={(e) => set({ customUnit: e.target.value })} options={[{ value: 'day', label: 'Days' }, { value: 'week', label: 'Weeks' }, { value: 'month', label: 'Months' }]} />
                </div>
              )}
            </fieldset>
            <Input label="Start date" type="date" value={form.startDate} onChange={(e) => set({ startDate: e.target.value })} error={f.startDate} locked={editing} />
            <Input label="Next renewal date" type="date" value={next ?? ''} locked help="Computed from the start date, trial, and billing cycle." />
            <Input label="Trial end date (optional)" type="date" value={form.trialEnd} onChange={(e) => set({ trialEnd: e.target.value })} error={f.trialEnd} locked={editing} />
            <Select label="Renewal" value={form.renewal} onChange={(e) => set({ renewal: e.target.value })} options={[{ value: 'auto', label: 'Auto-renews' }, { value: 'fixed', label: 'Fixed term' }]} />
            {form.renewal === 'fixed' && <Input label="End date" type="date" value={form.endDate} onChange={(e) => set({ endDate: e.target.value })} error={f.endDate} />}
            {form.currency === 'USD' && (
              <Input
                label="Exchange rate to ৳"
                inputMode="decimal"
                numeric
                value={form.rate}
                onChange={(e) => set({ rate: e.target.value })}
                error={f.rate}
                locked={editing}
                help="Only shown when the plan is not in BDT. ৳122 for $1."
              />
            )}
          </div>
          {form.currency === 'USD' && parseTaka(form.price) > 0 && parseTaka(form.rate) > 0 && (
            <p className="mt-4 t-num font-bold">
              {formatUSD(parseTaka(form.price))} × {formatRate(parseTaka(form.rate))} = {formatBDT(amount)}
            </p>
          )}
        </Card>

        <Card n={4} title={form.mode === 'reseller' ? 'How many buyers?' : 'How many seats?'}>
          <div className="grid gap-5">
            <Input
              label={form.mode === 'reseller' ? 'Buyers' : 'Seats'}
              inputMode="numeric"
              value={form.seats}
              onChange={(e) => set({ seats: e.target.value })}
              error={f.seats}
              help={form.mode === 'reseller' ? 'You take no seat.' : 'Includes your own seat, because you are the Owner.'}
            />
            {!editing && (
              <fieldset>
                <legend className="field__label mb-2">Split</legend>
                <div className="row gap-2">
                  <button type="button" className="chip" aria-pressed={form.split === 'equal'} onClick={() => set({ split: 'equal' })}>
                    Equal
                  </button>
                  <button type="button" className="chip" aria-pressed={form.split === 'custom'} onClick={() => set({ split: 'custom' })}>
                    Custom
                  </button>
                </div>
                {form.split === 'custom' && (
                  <div className="mt-4 grid gap-3">
                    {people.map((p) => (
                      <Input key={p.key} label={p.label} inputMode="decimal" numeric value={shares[p.key] ?? ''} onChange={(e) => setShares({ ...shares, [p.key]: e.target.value })} />
                    ))}
                    {!people.length && <p className="t-meta">Add invites first, then set each amount.</p>}
                    <p className={customOk ? 't-meta font-bold' : 'field__error'}>
                      Running total {formatBDT(customTotal)} of {formatBDT(amount)}
                      {customOk ? '' : ` · off by ${formatBDT(Math.abs(amount - customTotal))}`}
                    </p>
                    {f.split && <p className="field__error">{f.split}</p>}
                  </div>
                )}
              </fieldset>
            )}
          </div>
        </Card>

        <Card n={5} title="How should members pay you?">
          <div className="grid gap-5">
            <Select label="Recommended payment method" value={form.method} onChange={(e) => set({ method: e.target.value })} options={METHOD_KEYS.map((k) => ({ value: k, label: METHODS[k].label }))} help="A suggestion only. Each member picks their own method when they send an ID." />
            <Textarea label="Note for members (optional)" rows={2} value={form.note} onChange={(e) => set({ note: e.target.value })} placeholder="Pay by the 4th" />
          </div>
        </Card>

        <Card n={6} title="Who is joining?">
          <div className="grid gap-4">
            <div className="flex flex-wrap items-end gap-3">
              <Input label="Invite by email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={f.invites} fieldClass="flex-[1_1_14rem]" onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addInvite())} />
              <Button type="button" variant="primary-orange" icon={Plus} onClick={addInvite}>
                Add
              </Button>
            </div>
            {form.invites.length > 0 && (
              <div className="row gap-2">
                {form.invites.map((e) => (
                  <span key={e} className="neo-pill neo-pill--sm gap-1.5 !pr-1.5">
                    {e}
                    <button type="button" className="grid size-6 place-items-center rounded-full border-2 border-black bg-white" aria-label={`Remove ${e}`} onClick={() => set({ invites: form.invites.filter((x) => x !== e) })}>
                      <X aria-hidden="true" className="size-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p className="t-meta">Everyone needs an Ongsho account. People who do not have one get a sign-up page from the invite.</p>
          </div>
        </Card>

        <div className="row justify-end">
          <Link to={editing ? `/app/plans/${planId}` : '/app/plans'} className="neo-btn btn-ghost">
            Cancel
          </Link>
          <Button type="submit" variant="accept" icon={Check} busy={save.busy}>
            {editing ? 'Save changes' : 'Create plan'}
          </Button>
        </div>
      </div>

      <div className="stack">
        <Preview form={form} names={serviceList} editing={editing} />
        <Box variant="highlight">
          <BoxHead title="What happens next" />
          <ol className="grid gap-3">
            <li>1. Each invited person gets an email.</li>
            <li>2. When they join, their seat starts as Due.</li>
            <li>3. They pay you outside Ongsho, then send the transaction ID to confirm.</li>
          </ol>
        </Box>
      </div>
    </form>
  )
}

function fromPlan(plan) {
  const price = plan.priceNow
  const takaOrUsd = plan.currency === 'USD' ? String((price.usdCents ?? 0) / 100) : String((price.amount ?? 0) / 100)
  const custom = !['week', 'month', 'year'].includes(plan.cycle.unit) || plan.cycle.count !== 1
  return {
    mode: plan.mode,
    serviceName: plan.serviceName,
    planName: plan.planName,
    categoryId: plan.categoryId,
    price: takaOrUsd,
    currency: plan.currency,
    rate: price.rate ? String(price.rate / 100) : '122',
    cycleUnit: custom ? 'custom' : plan.cycle.unit,
    cycleCount: String(plan.cycle.count),
    customUnit: plan.cycle.unit,
    startDate: plan.startDate,
    trialEnd: plan.trialEnd ?? '',
    renewal: plan.renewal,
    endDate: plan.endDate ?? '',
    seats: String(plan.seats),
    split: plan.split,
    method: plan.method,
    note: plan.note ?? '',
    invites: plan.pendingInvites ?? [],
  }
}

export function PlanFormPage() {
  const { id } = useParams()
  const editing = Boolean(id)
  const query = useQuery({ queryKey: ['plan-form', id], queryFn: () => getPlanForm(id), enabled: editing })

  if (!editing) {
    return (
      <div className="stack-lg">
        <TopBar breadcrumb={[{ label: 'My Plans', to: '/app/plans' }, { label: 'New plan' }]} title="Create a plan" subtitle="Set it up once, then invite people by email." />
        <PlanForm initial={EMPTY} editing={false} />
      </div>
    )
  }

  return (
    <div className="stack-lg">
      <TopBar breadcrumb={[{ label: 'My Plans', to: '/app/plans' }, { label: 'Edit plan' }]} title="Edit plan" subtitle="Mode stays locked. Price changes go on the plan page." />
      <Loadable query={query} skeleton={<SkeletonCard lines={8} />}>
        {(plan) => <PlanForm key={plan.id} initial={fromPlan(plan)} editing planId={plan.id} />}
      </Loadable>
    </div>
  )
}
