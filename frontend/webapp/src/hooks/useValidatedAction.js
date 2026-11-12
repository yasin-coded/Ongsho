import { useCallback, useState } from 'react'
import { focusFirstInvalid, formLevelMessage } from '@/lib/formFocus'
import { useAction } from './useAction'

/**
 * Client validation before useAction runs. `validate()` returns field errors (empty object = ok).
 */
export function useValidatedAction(fn, options = {}) {
  const { validate, knownFieldKeys = [], onValidated, ...actionOpts } = options
  const action = useAction(fn, actionOpts)
  const [clientFields, setClientFields] = useState({})

  const fields = { ...clientFields, ...action.fields }
  const formAlert = formLevelMessage(action.fields, knownFieldKeys)

  const run = useCallback(
    (...args) => {
      if (validate) {
        const errs = validate(...args)
        if (errs && Object.keys(errs).length) {
          setClientFields(errs)
          requestAnimationFrame(() => focusFirstInvalid())
          return
        }
      }
      setClientFields({})
      onValidated?.(...args)
      action.run(...args)
    },
    [validate, action, onValidated],
  )

  const runAsync = useCallback(
    async (...args) => {
      if (validate) {
        const errs = validate(...args)
        if (errs && Object.keys(errs).length) {
          setClientFields(errs)
          requestAnimationFrame(() => focusFirstInvalid())
          throw new Error('validation')
        }
      }
      setClientFields({})
      onValidated?.(...args)
      return action.mutateAsync(...args)
    },
    [validate, action, onValidated],
  )

  return { ...action, run, runAsync, fields, formAlert, setClientFields }
}
