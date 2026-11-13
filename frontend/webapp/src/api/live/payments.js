import { ApiError } from '../errors'
import { apiRequest } from '../http'
import { enrichPaymentError } from '../adapters/payments'
import { idStr } from '../adapters/common'
import { mapReview } from '../adapters/review'

export const normalizeTid = (tid) => String(tid ?? '').replace(/\s+/g, '').toUpperCase()

async function postAction(path, data) {
  try {
    return await apiRequest('post', path, { data })
  } catch (err) {
    throw enrichPaymentError(err)
  }
}

export async function submitPayment({ planId, dueIds, method, tid }) {
  try {
    const data = await apiRequest('post', '/api/payments/', {
      data: {
        plan_id: Number(planId),
        due_ids: dueIds.map((d) => Number(d)),
        method,
        transaction_id: normalizeTid(tid),
      },
    })
    return { message: data.message, paymentId: idStr(data.payment_id) }
  } catch (err) {
    throw enrichPaymentError(err)
  }
}

export async function confirmPayment(paymentId) {
  return postAction(`/api/payments/${Number(paymentId)}/confirm/`)
}

export async function rejectPayment(paymentId, { reason }) {
  const clean = (reason ?? '').trim()
  if (!clean) {
    throw new ApiError('Tell the member why.', { fields: { reason: 'Write a short reason. The member will see it.' } })
  }
  return postAction(`/api/payments/${Number(paymentId)}/reject/`, { reason: clean })
}

export async function reversePayment(paymentId) {
  return postAction(`/api/payments/${Number(paymentId)}/reverse/`)
}

export async function markDuePaid(dueId, { date, method, note }) {
  const fields = {}
  if (!date) fields.date = 'Pick the date you were paid.'
  if (Object.keys(fields).length) throw new ApiError('Check the fields.', { fields })
  return postAction(`/api/dues/${Number(dueId)}/mark-paid/`, {
    date,
    method,
    note: (note ?? '').trim(),
  })
}

export async function waiveDue(dueId, { note }) {
  const clean = (note ?? '').trim()
  if (!clean) throw new ApiError('Add a note.', { fields: { note: 'Add a short note, for example "Birthday month".' } })
  return postAction(`/api/dues/${Number(dueId)}/waive/`, { note: clean })
}

export async function setDueBack(dueId) {
  return postAction(`/api/dues/${Number(dueId)}/set-due/`)
}

async function findPaymentInReviews(paymentId) {
  const { results = [] } = await apiRequest('get', '/api/subscriptions/', { params: { page_size: 100 } })
  for (const sub of results) {
    try {
      const raw = await apiRequest('get', `/api/shared-plans/${sub.id}/review/`)
      const hit = mapReview(raw).pending.find((p) => String(p.id) === String(paymentId))
      if (hit) return hit
    } catch {
      /* skip solo / not shared */
    }
  }
  return null
}

export async function waivePayment(paymentId, { note }) {
  const clean = (note ?? '').trim()
  if (!clean) throw new ApiError('Add a note.', { fields: { note: 'Add a short note, for example "Birthday month".' } })
  const payment = await findPaymentInReviews(paymentId)
  if (!payment) throw new ApiError('Payment not found.', { status: 404 })
  let last
  for (const cover of payment.covers) {
    last = await waiveDue(cover.dueId, { note: clean })
  }
  return last ?? { message: 'Waived.' }
}
