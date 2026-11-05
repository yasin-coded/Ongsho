import { useId, useState } from 'react'
import { CircleAlert, Eye, EyeOff, Lock } from 'lucide-react'
import { cx } from './Box'

export function Field({ label, help, error, children, className, id: givenId, hideLabel }) {
  const auto = useId()
  const id = givenId ?? auto
  const helpId = help ? `${id}-help` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined
  return (
    <div className={cx('field', className)}>
      {label && (
        <label htmlFor={id} className={cx('field__label', hideLabel && 'sr-only')}>
          {label}
        </label>
      )}
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })}
      {help && (
        <p id={helpId} className="field__help">
          {help}
        </p>
      )}
      {error && (
        <p id={errorId} className="field__error" role="alert">
          <CircleAlert aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  )
}

export function Input({ label, help, error, className, fieldClass, numeric, locked, hideLabel, ...rest }) {
  return (
    <Field label={label} help={help} error={error} className={fieldClass} id={rest.id} hideLabel={hideLabel}>
      {(a11y) =>
        locked ? (
          <div className="input-wrap">
            <input className={cx('input', className)} readOnly {...a11y} {...rest} />
            <Lock aria-label="Locked" className="input-wrap__icon size-4" />
          </div>
        ) : (
          <input className={cx('input', numeric && 'input--num', className)} {...a11y} {...rest} />
        )
      }
    </Field>
  )
}

export function PasswordInput({ label = 'Password', help, error, fieldClass, ...rest }) {
  const [shown, setShown] = useState(false)
  return (
    <Field label={label} help={help} error={error} className={fieldClass} id={rest.id}>
      {(a11y) => (
        <div className="input-wrap">
          <input className="input" type={shown ? 'text' : 'password'} {...a11y} {...rest} />
          <button type="button" className="input-wrap__btn" onClick={() => setShown((v) => !v)} aria-label={shown ? 'Hide password' : 'Show password'} aria-pressed={shown}>
            {shown ? <EyeOff aria-hidden="true" className="size-5" /> : <Eye aria-hidden="true" className="size-5" />}
          </button>
        </div>
      )}
    </Field>
  )
}

export function Select({ label, help, error, options, fieldClass, placeholder, ...rest }) {
  return (
    <Field label={label} help={help} error={error} className={fieldClass} id={rest.id}>
      {(a11y) => (
        <select className="input" {...a11y} {...rest}>
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  )
}

export function Textarea({ label, help, error, fieldClass, ...rest }) {
  return (
    <Field label={label} help={help} error={error} className={fieldClass} id={rest.id}>
      {(a11y) => <textarea className="input" {...a11y} {...rest} />}
    </Field>
  )
}

export function Switch({ checked, onChange, label, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} className="switch" onClick={() => onChange(!checked)} disabled={disabled} />
  )
}
