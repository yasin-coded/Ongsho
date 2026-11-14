// All money is integer paisa. Never pass floats in here.

const grouped = new Intl.NumberFormat('en-US')

const DECIMAL_STRING_RE = /^-?(?:\d+|\d*\.\d+)$/

/** Parse an API decimal string (e.g. "733.78", "125.0000") into integer paisa. Rejects scientific notation. */
export function toPaisa(decimalString) {
  const raw = String(decimalString ?? '').trim()
  if (!raw || !DECIMAL_STRING_RE.test(raw) || /[eE]/.test(raw)) {
    throw new RangeError(`Invalid money string: ${raw}`)
  }
  const num = Number(raw)
  if (!Number.isFinite(num)) throw new RangeError(`Invalid money string: ${raw}`)
  return Math.round(num * 100)
}

/** Format integer paisa as an API decimal string with two places. */
export function fromPaisa(paisa) {
  const value = Math.trunc(Number(paisa) || 0)
  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)
  const whole = Math.floor(abs / 100)
  const rest = abs % 100
  return `${sign}${whole}.${String(rest).padStart(2, '0')}`
}

/**
 * ৳1,200.00 by default.
 * `trim`: whole amounts drop .00 (big stat numbers, compact rows).
 * `compact`: ৳2.4k style for chart labels.
 */
export function formatBDT(paisa, { trim = false, compact = false } = {}) {
  const value = Math.round(Number(paisa) || 0)
  const sign = value < 0 ? '−' : ''
  const abs = Math.abs(value)
  const taka = Math.floor(abs / 100)
  const rest = abs % 100

  if (compact && taka >= 1000) {
    const k = taka / 1000
    const text = k >= 100 ? Math.round(k).toString() : (Math.round(k * 10) / 10).toString()
    return `${sign}৳${text}k`
  }
  if ((trim || compact) && rest === 0) return `${sign}৳${grouped.format(taka)}`
  return `${sign}৳${grouped.format(taka)}.${String(rest).padStart(2, '0')}`
}

export function formatUSD(cents) {
  const abs = Math.abs(Math.round(cents))
  return `$${grouped.format(Math.floor(abs / 100))}.${String(abs % 100).padStart(2, '0')}`
}

/** Rate is stored as paisa per dollar (৳122 → 12200). */
export function formatRate(ratePaisa) {
  const taka = ratePaisa / 100
  return `৳${Number.isInteger(taka) ? taka : taka.toFixed(2)}`
}

export function usdToPaisa(cents, ratePaisa) {
  return Math.round((cents * ratePaisa) / 100)
}

/** Equal split with leftover paisa on `leftoverIndex` so the total is exact. */
export function splitExact(total, seats, leftoverIndex = 0) {
  if (seats <= 0) return []
  const base = Math.floor(total / seats)
  const shares = Array.from({ length: seats }, () => base)
  shares[leftoverIndex] += total - base * seats
  return shares
}

/** Parse a typed taka amount ("1,200.5") into paisa, or null when invalid. */
export function parseTaka(text) {
  const clean = String(text ?? '').replace(/[,\s৳]/g, '')
  if (!/^\d+(\.\d{0,2})?$/.test(clean)) return null
  const [whole, frac = ''] = clean.split('.')
  return Number(whole) * 100 + Number(frac.padEnd(2, '0'))
}

export function sum(list, pick = (x) => x) {
  return list.reduce((acc, item) => acc + pick(item), 0)
}
