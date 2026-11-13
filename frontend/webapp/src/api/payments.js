import { delegate } from './delegate'
import * as mock from './mock/payments'
import * as live from './live/payments'

import { isLive } from './modes'

export const normalizeTid = isLive('normalizeTid') ? live.normalizeTid : mock.normalizeTid

export const confirmPayment = delegate(live, mock, 'confirmPayment')
export const rejectPayment = delegate(live, mock, 'rejectPayment')
export const reversePayment = delegate(live, mock, 'reversePayment')
export const waivePayment = delegate(live, mock, 'waivePayment')
export const waiveDue = delegate(live, mock, 'waiveDue')
export const markDuePaid = delegate(live, mock, 'markDuePaid')
export const setDueBack = delegate(live, mock, 'setDueBack')
export const submitPayment = delegate(live, mock, 'submitPayment')
