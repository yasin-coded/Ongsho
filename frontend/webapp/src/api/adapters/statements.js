import { ApiError } from '../errors'

const STATEMENT_CODE_MESSAGES = {
  nothing_to_report: 'Nothing to report for that month.',
}

export function enrichStatementError(err) {
  if (!(err instanceof ApiError)) return err
  let message = err.message
  if (err.code && STATEMENT_CODE_MESSAGES[err.code]) {
    message = STATEMENT_CODE_MESSAGES[err.code]
  }
  const fields = { ...err.fields }
  return new ApiError(message, { status: err.status, code: err.code, fields })
}