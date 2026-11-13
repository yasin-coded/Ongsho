import { ApiError } from '../errors'

const CODE_MESSAGES = {
  due_not_open: 'One of those dues is no longer open. Refresh and try again.',
  owner_cannot_submit: 'Use mark as paid for your own seat instead of submitting an ID.',
  reseller_own_dues_only: 'Paying for someone else is off in Reseller plans.',
  amount_mismatch: 'The amount does not match the dues you picked. Refresh and try again.',
  already_decided: 'This payment was already decided.',
  only_confirmed: 'Only a confirmed payment can be reversed.',
  cannot_reverse: 'This payment cannot be reversed.',
  already_paid: 'This due is no longer open.',
  use_reverse: 'Use reverse on the payment instead.',
  invalid_due_status: 'This due cannot be changed right now. Refresh and try again.',
}

export function mapPaymentFields(fields = {}) {
  const out = { ...fields }
  if (out.transaction_id) {
    out.tid = out.transaction_id
    delete out.transaction_id
  }
  if (out.due_ids) {
    out.dues = out.due_ids
    delete out.due_ids
  }
  return out
}

export function enrichPaymentError(err) {
  if (!(err instanceof ApiError)) return err
  let message = err.message
  if (err.code && CODE_MESSAGES[err.code]) message = CODE_MESSAGES[err.code]
  const fields = mapPaymentFields(err.fields)
  return new ApiError(message, { status: err.status, code: err.code, fields })
}
