import { useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { focusFirstInvalid } from '@/lib/formFocus'
import {
  validateCategoryName,
  validateEmail,
  validateName,
  validatePassword,
  validatePasswordRepeat,
  validateRequiredPassword,
  validateServiceName,
} from '@/lib/validation'
import { useQuery } from '@tanstack/react-query'
import { Check, Lock, LogOut, Plus, X } from 'lucide-react'
import * as accounts from '@/api/accounts'
import { createCategory, createServiceName, deleteCategory, deleteServiceName, getCategories, getServiceNames } from '@/api/catalog'
import { useAuth } from '@/auth/auth-context'
import { useAction } from '@/hooks/useAction'
import { AVATAR_COLORS, categoryColor, inkOn } from '@/lib/colors'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead, cx } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { Input, PasswordInput, Switch } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Pill } from '@/components/ui/Pill'
import { SkeletonCard } from '@/components/ui/Misc'
import { Loadable } from '@/features/common/PlanBits'

function AvatarPicker({ me }) {
  const [color, setColor] = useState(me.avatarColor ?? AVATAR_COLORS[0])
  const save = useAction(() => accounts.updateMe({ avatarColor: color }), { toastMessage: 'Avatar saved. It is updated everywhere.' })
  return (
    <Box>
      <BoxHead title="Change avatar" sub="Pick a color for your letter circle." />
      <div role="radiogroup" aria-label="Avatar color" className="grid grid-cols-5 gap-3">
        {AVATAR_COLORS.map((c) => {
          const on = c === color
          return (
            <button
              key={c}
              type="button"
              role="radio"
              aria-checked={on}
              aria-label={`Color ${c}`}
              onClick={() => setColor(c)}
              className={cx('grid aspect-square w-full max-w-14 place-items-center justify-self-center rounded-full border-[0.1875rem] border-black', on && 'shadow-[0_0_0_0.25rem_#fff,0_0_0_0.45rem_#000]')}
              style={{ background: c, color: inkOn(c) }}
            >
              {on && <Check aria-hidden="true" className="size-6" />}
            </button>
          )
        })}
      </div>
      <div className="mt-5 row justify-end">
        <Button variant="accept" busy={save.busy} disabled={color === me.avatarColor} onClick={() => save.run()}>
          Save avatar
        </Button>
      </div>
    </Box>
  )
}

function ChangeEmailModal({ email, onClose }) {
  const [password, setPassword] = useState('')
  const [clientFields, setClientFields] = useState({})
  const act = useAction(() => accounts.changeEmail({ email, password }), { onSuccess: onClose, tone: 'pending', toastMessage: `We sent a link to ${email}. Open it to confirm.` })
  return (
    <Modal open onClose={onClose} title="Change your email?" subtitle={`To ${email}. Enter your current password to continue.`}>
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          const pw = validateRequiredPassword(password)
          if (pw) {
            setClientFields({ password: pw })
            focusFirstInvalid()
            return
          }
          setClientFields({})
          act.run()
        }}
      >
        <PasswordInput label="Current password" autoComplete="current-password" maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)} error={clientFields.password ?? act.fields.password ?? act.fields.email} />
        <div className="row justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="accept" busy={act.busy}>
            Send the link
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function AccountDetails({ me }) {
  const [name, setName] = useState(me.name)
  const [email, setEmail] = useState(me.email)
  const [confirming, setConfirming] = useState(false)
  const [clientFields, setClientFields] = useState({})
  const saveName = useAction(() => accounts.updateMe({ name }), { toastMessage: 'Name saved.' })
  const resend = useAction(accounts.resendEmailChange, { toastMessage: `Sent again to ${me.pendingEmail}.` })
  const cancel = useAction(accounts.cancelEmailChange, { toastMessage: 'Email change cancelled. Nothing changed.', tone: 'waived' })
  const emailChanged = email.trim() && email.trim().toLowerCase() !== me.email

  return (
    <Box>
      <BoxHead title="Account details" />
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          const fields = {}
          const nm = validateName(name)
          if (nm) fields.name = nm
          if (emailChanged) {
            const em = validateEmail(email)
            if (em) fields.email = em
          }
          if (Object.keys(fields).length) {
            setClientFields(fields)
            focusFirstInvalid()
            return
          }
          setClientFields({})
          if (name.trim() !== me.name) saveName.run()
          if (emailChanged) setConfirming(true)
        }}
      >
        <Input
          label="Name"
          autoComplete="name"
          maxLength={255}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => {
            const nm = validateName(name)
            setClientFields((p) => {
              const next = { ...p }
              if (nm) next.name = nm
              else delete next.name
              return next
            })
          }}
          error={clientFields.name ?? saveName.fields.name}
        />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          maxLength={254}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => {
            if (!emailChanged) return
            const em = validateEmail(email)
            setClientFields((p) => {
              const next = { ...p }
              if (em) next.email = em
              else delete next.email
              return next
            })
          }}
          error={clientFields.email ?? saveName.fields.email}
          help="Changing it asks for your current password."
        />
        {me.pendingEmail && (
          <div className="neo-box neo-box--flat grid gap-3 !bg-[#fff200] !p-4" role="status">
            <p className="font-bold">Waiting to verify {me.pendingEmail}</p>
            <p className="t-meta">Your dues and emails move to the new address once you confirm. Until then, nothing changes.</p>
            <div className="row gap-2">
              <Button size="sm" variant="ghost" busy={resend.busy} onClick={() => resend.run()}>
                Resend
              </Button>
              <Button size="sm" variant="ghost" busy={cancel.busy} onClick={() => cancel.run()}>
                Cancel
              </Button>
            </div>
          </div>
        )}
        <div className="row justify-end">
          <Button type="submit" variant="accept" busy={saveName.busy} disabled={name.trim() === me.name && !emailChanged}>
            Save
          </Button>
        </div>
      </form>
      {confirming && <ChangeEmailModal email={email.trim().toLowerCase()} onClose={() => setConfirming(false)} />}
    </Box>
  )
}

function PasswordCard() {
  const navigate = useNavigate()
  const { logout } = useAuth()
  const empty = { oldPassword: '', newPassword: '', repeat: '' }
  const [form, setForm] = useState(empty)
  const [clientFields, setClientFields] = useState({})
  const act = useAction(() => accounts.changePassword(form), {
    invalidate: ['me'],
    onSuccess: async (data) => {
      setForm(empty)
      if (data?.revoked) {
        try {
          sessionStorage.setItem('ongsho:authMessage', 'Password updated. Sign in with your new password.')
        } catch {
          /* ignore */
        }
        await logout()
        navigate('/login', { replace: true, state: { from: '/app/profile' } })
      }
    },
  })
  return (
    <Box>
      <BoxHead title="Password" />
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          const fields = {}
          if (!form.oldPassword) fields.oldPassword = 'Enter your current password.'
          const np = validatePassword(form.newPassword)
          if (np) fields.newPassword = np
          const rp = validatePasswordRepeat(form.newPassword, form.repeat)
          if (rp) fields.repeat = rp
          if (Object.keys(fields).length) {
            setClientFields(fields)
            focusFirstInvalid()
            return
          }
          setClientFields({})
          act.run()
        }}
      >
        <PasswordInput label="Old password" autoComplete="current-password" maxLength={128} value={form.oldPassword} onChange={(e) => setForm({ ...form, oldPassword: e.target.value })} error={clientFields.oldPassword ?? act.fields.oldPassword} />
        <PasswordInput label="New password" autoComplete="new-password" maxLength={128} value={form.newPassword} onChange={(e) => setForm({ ...form, newPassword: e.target.value })} error={clientFields.newPassword ?? act.fields.newPassword} help="At least 8 characters, with a letter." />
        <PasswordInput label="New password (again)" autoComplete="new-password" maxLength={128} value={form.repeat} onChange={(e) => setForm({ ...form, repeat: e.target.value })} error={clientFields.repeat ?? act.fields.repeat} />
        <div className="row justify-end">
          <Button type="submit" variant="accept" busy={act.busy} disabled={act.busy}>
            Save
          </Button>
        </div>
      </form>
    </Box>
  )
}

function RemindersCard() {
  const query = useQuery({ queryKey: ['reminders'], queryFn: accounts.getReminderSettings })
  const save = useAction(accounts.updateReminderSettings, { toastMessage: 'Reminder settings saved.' })
  const OPTIONS = [7, 3, 1, 0]
  return (
    <Box>
      <BoxHead title="Reminders" sub="When we remind you about a due or a renewal." />
      <Loadable query={query} skeleton={<SkeletonCard lines={2} />}>
        {(s) => (
          <div className="grid gap-5">
            <fieldset>
              <legend className="field__label mb-2">Days before</legend>
              <div className="row gap-2">
                {OPTIONS.map((d) => {
                  const on = s.daysBefore.includes(d)
                  return (
                    <button
                      key={d}
                      type="button"
                      className="chip"
                      aria-pressed={on}
                      onClick={() => save.run({ daysBefore: on ? s.daysBefore.filter((x) => x !== d) : [...s.daysBefore, d].sort((a, b) => b - a) })}
                    >
                      {d === 0 ? 'On the day' : `${d} day${d === 1 ? '' : 's'} before`}
                    </button>
                  )
                })}
              </div>
            </fieldset>
            <div className="row-between">
              <span id="email-reminders" className="t-label">
                Also send reminders by email
              </span>
              <Switch checked={s.email} label="Also send reminders by email" onChange={(v) => save.run({ email: v })} />
            </div>
          </div>
        )}
      </Loadable>
    </Box>
  )
}

function BuiltInList({ items, colorize }) {
  const [expanded, setExpanded] = useState(false)
  const listRef = useRef(null)
  const [fullHeight, setFullHeight] = useState(null)
  const [truncated, setTruncated] = useState(false)

  useLayoutEffect(() => {
    const el = listRef.current
    if (!el) return
    const measure = () => {
      const natural = el.scrollHeight
      setFullHeight(natural)
      if (!expanded) {
        const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
        setTruncated(natural > 9 * rootPx + 2)
      }
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [items, expanded])

  if (!items.length) return <p className="t-meta">None.</p>

  return (
    <div className={cx('catalog-built-in', expanded && 'catalog-built-in--expanded')}>
      <div
        className={cx('catalog-built-in__wrap', expanded && 'catalog-built-in__wrap--expanded')}
        style={fullHeight != null ? { '--built-in-height': `${fullHeight}px` } : undefined}
      >
        <div ref={listRef} className="catalog-built-in__list row gap-2">
          {items.map((i) => (
            <Pill key={i.id} small fill={colorize ? categoryColor(i.name) : '#ffffff'}>
              {i.name}
            </Pill>
          ))}
        </div>
        {!expanded && truncated && <div className="catalog-built-in__fade" aria-hidden="true" />}
      </div>
      {(truncated || expanded) && (
        <button type="button" className="catalog-built-in__toggle text-link t-meta w-fit font-bold" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'See less' : 'See all'}
        </button>
      )}
    </div>
  )
}

function CatalogGroup({ title, items, onAdd, onDelete, addLabel, fieldError, busy, colorize, validateAdd }) {
  const [text, setText] = useState('')
  const [clientError, setClientError] = useState(null)
  const builtIn = items.filter((i) => i.preset)
  const mine = items.filter((i) => !i.preset)
  return (
    <div className="catalog-panel">
      <h3 className="catalog-panel__title t-sub">{title}</h3>
      <div className="catalog-panel__body">
        <section className="grid gap-2">
          <p className="t-label">Built in</p>
          <BuiltInList items={builtIn} colorize={colorize} />
        </section>
        <section className="grid gap-2">
          <p className="row t-label gap-2">
            Yours
            <span className="row t-meta gap-1 font-normal">
              <Lock aria-hidden="true" className="size-3.5" /> Only you can see these
            </span>
          </p>
          {mine.length ? (
            <div className="row gap-2">
              {mine.map((i) => (
                <span key={i.id} className="neo-pill neo-pill--sm gap-1.5 !pr-1.5" style={{ background: colorize ? categoryColor(i.name) : '#fff', color: colorize ? inkOn(categoryColor(i.name)) : '#000' }}>
                  {i.name}
                  <button type="button" className="grid size-6 place-items-center rounded-full border-2 border-black bg-white text-black" aria-label={`Delete ${i.name}`} onClick={() => onDelete(i)}>
                    <X aria-hidden="true" className="size-3.5" />
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="t-meta">None yet.</p>
          )}
        </section>
      </div>
      <form
        className="catalog-panel__add flex flex-wrap items-start gap-3"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          const err = validateAdd(text)
          if (err) {
            setClientError(err)
            focusFirstInvalid()
            return
          }
          setClientError(null)
          onAdd(text, () => setText(''))
        }}
      >
        <Input
          label={addLabel}
          hideLabel
          maxLength={colorize ? 40 : 255}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => setClientError(validateAdd(text))}
          placeholder={addLabel}
          fieldClass="flex-[1_1_14rem]"
          error={clientError ?? fieldError}
        />
        <Button type="submit" variant="accept" icon={Plus} busy={busy}>
          Add
        </Button>
      </form>
    </div>
  )
}

function CatalogCard() {
  const cats = useQuery({ queryKey: ['categories'], queryFn: getCategories })
  const names = useQuery({ queryKey: ['service-names'], queryFn: getServiceNames })
  const [confirm, setConfirm] = useState(null)
  const addCat = useAction(createCategory, { toastMessage: (c) => `Added “${c.name}”.` })
  const addName = useAction(createServiceName, { toastMessage: (s) => `Added “${s.name}”.` })
  const remove = useAction((item) => (item.type === 'category' ? deleteCategory(item.id) : deleteServiceName(item.id)), {
    toastMessage: (r, item) => (r?.moved ? `Deleted. ${r.moved} plan${r.moved === 1 ? '' : 's'} moved to Utilities.` : `Deleted “${item.name}”.`),
    tone: 'waived',
    onSuccess: () => setConfirm(null),
  })

  return (
    <Box roomy>
      <BoxHead title="Categories and service names" sub="Built-in ones are for everyone. Yours are private." />
      <div className="grid gap-10 lg:grid-cols-2">
        <Loadable query={cats} skeleton={<SkeletonCard />}>
          {(list) => (
            <CatalogGroup
              title="Categories"
              colorize
              items={list}
              addLabel="Add a category"
              fieldError={addCat.fields.name}
              busy={addCat.busy}
              validateAdd={validateCategoryName}
              onAdd={(name, done) => addCat.run({ name }, { onSuccess: done })}
              onDelete={(i) => setConfirm({ ...i, type: 'category' })}
            />
          )}
        </Loadable>
        <Loadable query={names} skeleton={<SkeletonCard />}>
          {(list) => (
            <CatalogGroup
              title="Service names"
              items={list}
              addLabel="Add a service name"
              fieldError={addName.fields.service}
              busy={addName.busy}
              validateAdd={validateServiceName}
              onAdd={(name, done) => addName.run({ name }, { onSuccess: done })}
              onDelete={(i) => setConfirm({ ...i, type: 'service' })}
            />
          )}
        </Loadable>
      </div>
      {confirm && (
        <Modal
          open
          onClose={() => setConfirm(null)}
          title={`Delete “${confirm.name}”?`}
          footer={
            <>
              <Button variant="ghost" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="reject" busy={remove.busy} onClick={() => remove.run(confirm)}>
                Delete
              </Button>
            </>
          }
        >
          <p>
            {confirm.type === 'category' && confirm.inUse
              ? 'Some of your plans use this category. They move to Utilities, and you can change that in each plan.'
              : 'It is removed from your list. Plans that already use it keep their name.'}
          </p>
        </Modal>
      )}
    </Box>
  )
}

export function ProfilePage() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const query = useQuery({ queryKey: ['me'], queryFn: accounts.getMe })
  const [leaving, setLeaving] = useState(false)

  return (
    <div className="stack-lg">
      <TopBar
        title="Profile"
        subtitle="Everything here is about you!"
        tools={false}
        actions={
          <Button
            variant="logout"
            icon={LogOut}
            busy={leaving}
            onClick={async () => {
              setLeaving(true)
              await logout()
              navigate('/login', { replace: true })
            }}
          >
            LOG OUT
          </Button>
        }
      />
      <Loadable
        query={query}
        skeleton={
          <div className="two-col">
            <SkeletonCard tall />
            <SkeletonCard lines={5} />
          </div>
        }
      >
        {(me) => (
          <>
            <div className="grid items-start gap-6 lg:grid-cols-2 lg:gap-8">
              <div className="stack">
                <Box roomy className="grid justify-items-center gap-4 text-center">
                  <Avatar name={me.name} color={me.avatarColor} size="lg" />
                  <div className="grid gap-1">
                    <p className="t-section">{me.name}</p>
                    <p className="t-meta break-all">{me.email}</p>
                  </div>
                  <div className="profile-summary__tags">
                    <Pill small fill="#ff00ff">
                      {me.owned} owned
                    </Pill>
                    <Pill small fill="#00ff8b">
                      {me.joined} joined
                    </Pill>
                  </div>
                </Box>
                <AvatarPicker key={me.avatarColor} me={me} />
                <RemindersCard />
              </div>
              <div className="stack">
                <AccountDetails key={`${me.name}|${me.email}|${me.pendingEmail}`} me={me} />
                <PasswordCard />
              </div>
            </div>
            <CatalogCard />
          </>
        )}
      </Loadable>
    </div>
  )
}
