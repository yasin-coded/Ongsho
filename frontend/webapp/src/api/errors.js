/** Maps backend field keys to form field names used in the UI. */
export const API_FIELD_TO_FORM = {
  new_password: 'newPassword',
  current_password: 'oldPassword',
  new_email: 'email',
  avatar_id: 'avatarColor',
  days_before: 'daysBefore',
  service_name: 'serviceName',
  plan_name: 'planName',
  category: 'categoryId',
  amount: 'price',
  exchange_rate: 'rate',
  start_date: 'startDate',
  trial_end_date: 'trialEnd',
  renewal_type: 'renewal',
  end_date: 'endDate',
  recommended_method: 'method',
  cycle_unit: 'cycleUnit',
  cycle_count: 'cycleCount',
  next_renewal_date: 'nextRenewalDate',
  plan_mode: 'mode',
  invite_emails: 'invites',
  split_type: 'split',
  transaction_id: 'tid',
  due_ids: 'dues',
  reason: 'reason',
  note: 'note',
  date: 'date',
  effective_from: 'effectiveFrom',
  password: 'password',
}

export class ApiError extends Error {
  constructor(message, { status = 400, fields = {}, code = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
    this.code = code
  }
}

function firstMessage(list) {
  if (!list?.length) return null
  const msg = list[0]
  return typeof msg === 'string' ? msg : String(msg)
}

function flattenFields(raw) {
  if (!raw || typeof raw !== 'object') return {}
  const out = {}
  for (const [key, value] of Object.entries(raw)) {
    const formKey = API_FIELD_TO_FORM[key] ?? key
    if (Array.isArray(value)) {
      const msg = firstMessage(value)
      if (msg) out[formKey] = msg
    } else if (typeof value === 'string') {
      out[formKey] = value
    } else if (value && typeof value === 'object') {
      const nested = flattenFields(value)
      for (const [k, v] of Object.entries(nested)) {
        out[k] = v
      }
    }
  }
  return out
}

export function normalizeApiError(err, { fallbackMessage = 'Something went wrong. Try again.' } = {}) {
  if (err instanceof ApiError) return err
  const status = err?.response?.status ?? err?.status ?? 0
  const data = err?.response?.data

  if (data?.error) {
    const { code, message, fields } = data.error
    return new ApiError(message || fallbackMessage, {
      status,
      code: code ?? null,
      fields: flattenFields(fields),
    })
  }

  if (status === 0 || err?.code === 'ERR_NETWORK') {
    return new ApiError('Could not reach Ongsho. Check your connection and try again.', { status: 0 })
  }

  const message = typeof data === 'string' ? data : data?.detail ?? fallbackMessage
  return new ApiError(message, { status })
}
