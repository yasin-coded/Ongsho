import { ApiError } from '../errors'
import { idStr } from './common'
import { avatarColorFromId } from './me'

const TRANSFER_CODE_MESSAGES = {
  transfer_not_allowed: 'Reseller plans cannot change owner.',
  transfer_exists: 'A transfer is already waiting. Cancel it or wait for a response.',
  transfer_closed: 'This transfer is no longer open.',
  owner_changed: 'The plan owner changed. Refresh and try again.',
  not_a_member: 'You are no longer a member of this plan.',
}

export function mapOwnerTransfer(row) {
  if (!row) return null
  return {
    id: idStr(row.id),
    status: row.status,
    toUserId: row.to?.id != null ? idStr(row.to.id) : undefined,
    createdAt: row.created_at ?? null,
  }
}

export function mapIncomingTransfer(row) {
  if (!row) return null
  const from = row.from ?? {}
  return {
    id: idStr(row.id),
    createdAt: row.created_at ?? null,
    from: {
      name: from.name,
      firstName: from.first_name,
      avatarColor: avatarColorFromId(from.avatar_id),
    },
  }
}

export function enrichTransferError(err) {
  if (!(err instanceof ApiError)) return err
  let message = err.message
  if (err.code && TRANSFER_CODE_MESSAGES[err.code]) {
    message = TRANSFER_CODE_MESSAGES[err.code]
  }
  const fields = { ...err.fields }
  if (fields.member_id) {
    fields.memberId = fields.member_id
    delete fields.member_id
  }
  return new ApiError(message, { status: err.status, code: err.code, fields })
}