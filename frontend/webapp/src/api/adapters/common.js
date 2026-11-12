import { toPaisa, fromPaisa } from '@/lib/money'

export function idStr(value) {
  if (value === null || value === undefined) return null
  return String(value)
}

export function idNum(value) {
  if (value === null || value === undefined || value === '') return null
  return Number(value)
}

export function moneyFromApi(decimalString) {
  if (decimalString === null || decimalString === undefined) return null
  return toPaisa(String(decimalString))
}

export function moneyToApi(paisaOrTaka) {
  if (paisaOrTaka === null || paisaOrTaka === undefined) return null
  if (typeof paisaOrTaka === 'number' && paisaOrTaka > 1000) {
    return fromPaisa(paisaOrTaka)
  }
  return fromPaisa(toPaisa(String(paisaOrTaka)))
}

/** UI rate is integer paisa-per-dollar; API wants a decimal string with 2 places. */
export function rateToApi(ratePaisa) {
  return fromPaisa(ratePaisa)
}

export function rateFromApi(rateString) {
  if (!rateString) return null
  return toPaisa(rateString)
}

export function paginatedBody(body) {
  const page = body.page ?? 1
  const pages = body.total_pages ?? body.pages ?? 1
  const total = body.count ?? body.total ?? 0
  const size = body.page_size ?? body.size ?? (body.results?.length || 0)
  return {
    items: body.results ?? body.items ?? [],
    page,
    pages,
    total,
    size,
    ...(body.counts ? { counts: body.counts } : {}),
    ...(body.totals ? { totals: body.totals } : {}),
    ...(body.unread !== undefined ? { unread: body.unread } : {}),
  }
}
