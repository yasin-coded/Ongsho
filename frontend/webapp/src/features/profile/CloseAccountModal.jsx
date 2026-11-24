import { useState } from 'react'
import { useNavigate } from 'react-router'
import { DoorClosed } from 'lucide-react'
import * as accounts from '@/api/accounts'
import { useAuth } from '@/auth/auth-context'
import { validateRequiredPassword } from '@/lib/validation'
import { useValidatedAction } from '@/hooks/useValidatedAction'
import { Button } from '@/components/ui/Button'
import { PasswordInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'

export function CloseAccountModal({ open, onClose }) {
  const navigate = useNavigate()
  const { endSession } = useAuth()
  const [password, setPassword] = useState('')

  const act = useValidatedAction(() => accounts.closeAccount({ password }), {
    validate: () => {
      const pw = validateRequiredPassword(password)
      return pw ? { password: pw } : {}
    },
    knownFieldKeys: ['password'],
    optimisticNav: false,
    tone: 'pending',
    toastMessage: 'Your account is closed. You can sign up again with the same email any time — it will be a new account.',
    onSuccess: () => {
      setPassword('')
      endSession()
      onClose()
      navigate('/login?reason=account-closed', { replace: true })
    },
  })

  const handleClose = () => {
    if (act.busy) return
    setPassword('')
    act.setClientFields({})
    onClose()
  }

  if (!open) return null

  return (
    <Modal
      open
      onClose={handleClose}
      title="Close your account?"
      subtitle="This only applies to your login. Payment records on shared plans stay on file."
      wide
    >
      <form
        className="grid gap-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          act.run()
        }}
      >
        <ul className="grid gap-2 t-meta list-disc pl-5">
          <li>Your name and email on this account are anonymised; you are signed out everywhere.</li>
          <li>You can register again with the same email later, but that creates a separate account.</li>
          <li>Plans, memberships, and payment history from this account do not move to a new registration.</li>
        </ul>
        <PasswordInput
          label="Current password"
          autoComplete="current-password"
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => {
            const pw = password ? validateRequiredPassword(password) : null
            act.setClientFields((p) => {
              const next = { ...p }
              if (pw) next.password = pw
              else delete next.password
              return next
            })
          }}
          error={act.fields.password}
        />
        {act.formAlert && (
          <p role="alert" className="field__error">
            {act.formAlert}
          </p>
        )}
        <div className="modal__footer row justify-end gap-2">
          <Button type="button" variant="ghost" disabled={act.busy} onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" variant="reject" icon={DoorClosed} busy={act.busy} disabled={act.busy}>
            Close account
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function AccountCloseSection() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <section className="neo-box neo-box--danger grid gap-4 p-5" aria-labelledby="account-close-heading">
        <div className="grid gap-2">
          <h2 id="account-close-heading" className="t-sub">
            Close account
          </h2>
          <p className="t-meta">
            Closing anonymises this login and signs you out. Shared-plan payment records and audit history stay tied to
            this account ID — they are not erased and do not transfer if you register again.
          </p>
          <p className="t-meta">
            You may need to archive or transfer plans you own, leave active memberships, or finish a pending ownership
            transfer before closure succeeds.
          </p>
        </div>
        <div>
          <Button
            type="button"
            variant="reject"
            icon={DoorClosed}
            onClick={() => setOpen(true)}
          >
            Close account…
          </Button>
        </div>
      </section>
      <CloseAccountModal open={open} onClose={() => setOpen(false)} />
    </>
  )
}