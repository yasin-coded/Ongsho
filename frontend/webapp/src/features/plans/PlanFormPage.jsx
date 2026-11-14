import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Check, Plus, X } from 'lucide-react'
import { createSubscription, getPlanForm, updateSubscription } from '@/api/plans'
import { getCategories, getServiceNames } from '@/api/catalog'
import { METHODS, METHOD_KEYS } from '@/lib/colors'
import { dayOfMonth, fmtShort, todayDhaka } from '@/lib/dates'
import { formatBDT, formatRate, formatUSD, parseTaka, splitExact, usdToPaisa } from '@/lib/money'
import {
  cycleFromForm,
  cycleLabel,
  firstBillDate,
  isPresetCycleUnit,
  nextDueDate,
  perCycleLabel,
  presetNextRenewalFromStart,
} from '@/mocks/schedule'
import { focusFirstInvalid } from '@/lib/formFocus'
import { validatePlanForm } from '@/lib/validation'
import { useAction } from '@/hooks/useAction'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Input, Select, Textarea } from '@/components/ui/Field'
import { LockedNote, RoleTag } from '@/components/ui/Pill'
import { ServiceLogo } from '@/components/ui/ServiceLogo'
import { NumberCircle, PlanFormSkeleton, Skeleton } from '@/components/ui/Misc'
import { shouldShowInitialSkeleton } from '@/lib/queryLoading'
import { Loadable } from '@/features/common/PlanBits'

function emptyPlanForm() {
  const startDate = todayDhaka()
  return {
    mode: 'owner',
    serviceName: '',
    planName: '',
    categoryId: '',
    price: '',
    currency: 'BDT',
    rate: '122',
    cycleUnit: 'month',
    cycleCount: '1',
    customUnit: 'month',
    startDate,
    trialEnd: '',
    renewal: 'auto',
    endDate: '',
    seats: '2',
    split: 'equal',
    method: 'bkash',
    note: '',
    invites: [],
    nextRenewalDate: presetNextRenewalFromStart(startDate, 'month'),
  }
}

const cycleOf = cycleFromForm

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
  if (form.renewal !== 'fixed' && form.nextRenewalDate) return form.nextRenewalDate
  if (isPresetCycleUnit(form.cycleUnit) && form.startDate) {
    return presetNextRenewalFromStart(form.startDate, form.cycleUnit)
  }
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
  return nextDueDate(plan, todayDhaka()) ?? firstBillDate(plan)
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
  const displayName = form.planName?.trim() || form.serviceName?.trim() || 'Untitled plan'
  const logoName = form.serviceName?.trim() || displayName
  const cycle = cycleOf(form)
  const amount = chargePaisa(form)
  const seats = Math.max(1, Number(form.seats) || 1)
  const seatCountForSplit = form.mode === 'reseller' ? seats : form.mode === 'owner' && (seats > 1 || form.invites.length > 0) ? seats : 1
  const per = amount ? splitExact(amount, seatCountForSplit, 0)[0] : 0
  const next = (form.renewal === 'fixed' ? form.endDate : form.nextRenewalDate) || nextRenewalOf(form)
  const usd = form.currency === 'USD' && parseTaka(form.price) > 0 && parseTaka(form.rate) > 0
  return (
    <Box className="min-w-0">
      <BoxHead title="Live preview" />
      <div className="grid gap-4">
        <div className="row gap-3">
          <ServiceLogo key={`${catalog?.serviceKey ?? 'custom'}-${form.serviceName}`} serviceKey={catalog?.serviceKey} name={logoName} size="compact" />
          <div className="grid min-w-0 gap-1">
            <p className="t-sub truncate">{displayName}</p>
            <p className="t-meta">
              {cycleLabel(cycle)}
              {next ? (form.renewal === 'fixed' ? ` · ends ${fmtShort(next)}` : ` · renews ${fmtShort(next)}`) : ''}
              {` · ${seats} seat${seats === 1 ? '' : 's'}`}
            </p>
            <span className="w-fit max-w-full">
              <RoleTag role={form.mode === 'reseller' ? 'reseller' : seats > 1 || form.invites.length ? 'owner' : 'solo'} />
            </span>
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

function PlanForm({ initial, editing, planId }) {
  const navigate = useNavigate()
  const [form, setForm] = useState(() => {
    const nextRenewalDate =
      initial.renewal === 'fixed' && initial.endDate
        ? initial.endDate
        : initial.nextRenewalDate || nextRenewalOf(initial) || ''
    return {
      ...initial,
      nextRenewalDate,
      ...(initial.renewal === 'fixed' && initial.endDate ? { endDate: initial.endDate } : {}),
    }
  })
  const [email, setEmail] = useState('')
  const cats = useQuery({ queryKey: ['categories'], queryFn: getCategories })
  const names = useQuery({ queryKey: ['service-names'], queryFn: getServiceNames })
  const [clientFields, setClientFields] = useState({})
  const save = useAction(
    (payload) => (editing ? updateSubscription(planId, payload) : createSubscription(payload)),
    {
      onSuccess: (data) => navigate(`/app/plans/${data.id}`),
      toastMessage: editing ? 'Plan details saved.' : 'Plan created. Invites are on their way.',
    },
  )
  const planValidateOpts = { editing, minSeats: editing ? Number(form.seats) : 0 }
  const blurValidate = () => setClientFields(validatePlanForm(form, planValidateOpts))

  /** Functional updaters must return a partial patch; always merged so we never drop `invites` etc. */
  const set = (patch) =>
    setForm((f) => (typeof patch === 'function' ? { ...f, ...patch(f) } : { ...f, ...patch }))
  const amount = chargePaisa(form)
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
    const clientErrs = validatePlanForm(form, { editing, minSeats: editing ? Number(form.seats) : 0 })
    if (Object.keys(clientErrs).length) {
      setClientFields(clientErrs)
      focusFirstInvalid()
      return
    }
    setClientFields({})
    const payload = {
      ...form,
      price: Number(form.price),
      rate: Number(form.rate),
      cycleCount: Number(form.cycleCount),
      seats: Number(form.seats),
      trialEnd: form.trialEnd || null,
      endDate: form.renewal === 'fixed' ? form.endDate : null,
      ...(editing ? {} : { split: 'equal', customTotalOk: true }),
    }
    save.run(payload)
  }

  const f = { ...clientFields, ...save.fields }
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
              {shouldShowInitialSkeleton(names) ? (
                <div className="row flex-wrap gap-2" aria-busy="true">
                  <span className="sr-only">Loading</span>
                  {Array.from({ length: 6 }, (_, i) => (
                    <Skeleton key={i} className="h-11 w-[4.75rem] rounded-full" />
                  ))}
                </div>
              ) : (
              <div className="row flex-wrap gap-2">
                {serviceList.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="chip"
                    aria-pressed={form.serviceName === s.name}
                    onClick={() =>
                      set({
                        serviceName: s.name,
                        planName: s.name,
                        ...(s.categoryId ? { categoryId: String(s.categoryId) } : {}),
                      })
                    }
                  >
                    {s.name}
                  </button>
                ))}
              </div>
              )}
              {!form.serviceName.trim() && f.serviceName ? (
                <p className="field__error mt-2" role="alert">
                  {f.serviceName}
                </p>
              ) : null}
            </div>
            <Input label="Plan name" maxLength={255} value={form.planName} onChange={(e) => set({ planName: e.target.value })} onBlur={blurValidate} error={f.planName} placeholder='For example "Netflix Premium"' />
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
            <Input label={form.currency === 'USD' ? 'Price ($)' : 'Price (৳)'} inputMode="decimal" numeric value={form.price} onChange={(e) => set({ price: e.target.value })} onBlur={blurValidate} error={f.price} locked={editing} />
            <Select label="Currency" value={form.currency} disabled={editing} onChange={(e) => set({ currency: e.target.value })} options={[{ value: 'BDT', label: 'BDT' }, { value: 'USD', label: 'USD' }]} />
            <fieldset className="sm:col-span-2">
              <legend className="field__label mb-2">Billed</legend>
              <div className="row gap-2">
                {['week', 'month', 'year', 'custom'].map((u) => (
                  <button
                    key={u}
                    type="button"
                    className="chip"
                    aria-pressed={form.cycleUnit === u}
                    disabled={editing}
                    onClick={() =>
                      set((f) => {
                        const patch = { cycleUnit: u }
                        if (u !== 'custom' && f.renewal !== 'fixed' && f.startDate) {
                          patch.nextRenewalDate = presetNextRenewalFromStart(f.startDate, u)
                          patch.cycleCount = '1'
                        }
                        return patch
                      })
                    }
                  >
                    {u === 'week' ? 'Weekly' : u === 'month' ? 'Monthly' : u === 'year' ? 'Yearly' : 'Custom'}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="plan-date-pair sm:col-span-2">
              <Input
                label="Start date"
                type="date"
                value={form.startDate}
                onChange={(e) => {
                  const startDate = e.target.value
                  set((f) => {
                    const patch = { startDate }
                    if (f.renewal !== 'fixed' && isPresetCycleUnit(f.cycleUnit)) {
                      patch.nextRenewalDate = presetNextRenewalFromStart(startDate, f.cycleUnit)
                    }
                    return patch
                  })
                }}
                error={f.startDate}
                locked={editing}
              />
              {form.renewal === 'fixed' ? (
                <Input
                  label="End date"
                  type="date"
                  value={form.endDate ?? ''}
                  onChange={(e) => {
                    const v = e.target.value
                    set({ endDate: v, nextRenewalDate: v })
                  }}
                  error={f.endDate || f.nextRenewalDate}
                />
              ) : (
                <Input
                  label="Next renewal date"
                  type="date"
                  value={form.nextRenewalDate ?? ''}
                  onChange={(e) => {
                    const v = e.target.value
                    set((f) => {
                      const patch = { nextRenewalDate: v }
                      if (isPresetCycleUnit(f.cycleUnit)) {
                        const expected = presetNextRenewalFromStart(f.startDate, f.cycleUnit)
                        if (v && expected && v !== expected) patch.cycleUnit = 'custom'
                      }
                      return patch
                    })
                  }}
                  error={f.nextRenewalDate}
                />
              )}
              <p className="plan-date-pair__help field__help">
                {form.renewal === 'fixed'
                  ? 'When the last charge is due before the plan ends.'
                  : form.cycleUnit === 'custom'
                    ? 'Pick the start date and the next renewal date. The days between them are your billing cycle.'
                    : 'When the next charge is due.'}
              </p>
            </div>
            <Input label="Trial end date (optional)" type="date" value={form.trialEnd} onChange={(e) => set({ trialEnd: e.target.value })} error={f.trialEnd} locked={editing} />
            <Select
              label="Renewal"
              value={form.renewal}
              onChange={(e) => {
                const v = e.target.value
                if (v === 'fixed') {
                  set((f) => {
                    const end = f.endDate?.trim() || f.nextRenewalDate?.trim() || ''
                    return { ...f, renewal: v, endDate: end, nextRenewalDate: end }
                  })
                } else {
                  set((f) => {
                    const next = nextRenewalOf({ ...f, renewal: v, endDate: '' }) || ''
                    return { ...f, renewal: v, endDate: '', nextRenewalDate: next }
                  })
                }
              }}
              options={[{ value: 'auto', label: 'Auto-renews' }, { value: 'fixed', label: 'Fixed term' }]}
            />
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
            <p className="t-meta">Seat amounts are equal at first. After you create the plan, open it and use <strong>Seat split</strong> to switch to custom shares if you want.</p>
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

      <div className="stack min-w-0">
        <Preview form={form} names={serviceList} editing={editing} />
        <Box className="min-w-0">
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
        <PlanForm initial={emptyPlanForm()} editing={false} />
      </div>
    )
  }

  return (
    <div className="stack-lg">
      <TopBar breadcrumb={[{ label: 'My Plans', to: '/app/plans' }, { label: 'Edit plan' }]} title="Edit plan" subtitle="Mode stays locked. Price changes go on the plan page." />
      <Loadable query={query} skeleton={<PlanFormSkeleton />}>
        {(plan) => <PlanForm key={plan.id} initial={fromPlan(plan)} editing planId={plan.id} />}
      </Loadable>
    </div>
  )
}
