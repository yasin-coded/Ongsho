// Calendar dates are 'YYYY-MM-DD' strings in Dhaka time. Timestamps are ISO strings with +06:00.

export const TIME_ZONE = 'Asia/Dhaka'
export const MOCK_TODAY = '2026-11-05'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export function parseDate(iso) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

export function toISODate(date) {
  return date.toISOString().slice(0, 10)
}

export function makeDate(y, m, d) {
  return toISODate(new Date(Date.UTC(y, m - 1, d)))
}

export function daysInMonth(y, m) {
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}

export function addDays(iso, n) {
  const d = parseDate(iso)
  d.setUTCDate(d.getUTCDate() + n)
  return toISODate(d)
}

export function diffDays(a, b) {
  return Math.round((parseDate(a) - parseDate(b)) / 86400000)
}

/** Month step that keeps the anchor day: 31 Jan → 28 Feb → 31 Mar. */
export function addMonthsAnchored(iso, months, anchorDay) {
  const d = parseDate(iso)
  const total = d.getUTCFullYear() * 12 + d.getUTCMonth() + months
  const y = Math.floor(total / 12)
  const m = (total % 12) + 1
  const day = Math.min(anchorDay ?? d.getUTCDate(), daysInMonth(y, m))
  return makeDate(y, m, day)
}

/** Year step. A plan started on 29 Feb renews on 28 Feb in other years. */
export function addYearsAnchored(iso, years, anchorDay) {
  return addMonthsAnchored(iso, years * 12, anchorDay)
}

export function monthKey(iso) {
  return iso.slice(0, 7)
}

export function monthStart(iso) {
  return `${iso.slice(0, 7)}-01`
}

export function monthEnd(iso) {
  const d = parseDate(iso)
  return makeDate(d.getUTCFullYear(), d.getUTCMonth() + 1, daysInMonth(d.getUTCFullYear(), d.getUTCMonth() + 1))
}

export function addMonthsToKey(key, n) {
  const [y, m] = key.split('-').map(Number)
  const total = y * 12 + (m - 1) + n
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, '0')}`
}

export function fmtShort(iso) {
  const d = parseDate(iso)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
}

export function fmtFull(iso) {
  const d = parseDate(iso)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

export function fmtMonth(iso) {
  const d = parseDate(iso)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

export function fmtMonthLong(iso) {
  return MONTHS_LONG[parseDate(iso).getUTCMonth()]
}

export function fmtMonthYearLong(iso) {
  const d = parseDate(iso)
  return `${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

export function monthShortName(iso) {
  return MONTHS[parseDate(iso).getUTCMonth()]
}

export function weekdayName(iso) {
  return WEEKDAYS[parseDate(iso).getUTCDay()]
}

export function weekday(iso) {
  return parseDate(iso).getUTCDay()
}

export function dayOfMonth(iso) {
  return parseDate(iso).getUTCDate()
}

const timeFmt = new Intl.DateTimeFormat('en-US', { timeZone: TIME_ZONE, hour: 'numeric', minute: '2-digit', hour12: true })
const dhakaDateFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' })

export function fmtTime(ts) {
  return timeFmt.format(new Date(ts))
}

export function dhakaDate(ts) {
  return dhakaDateFmt.format(new Date(ts))
}

/** Live Dhaka calendar date (`YYYY-MM-DD`). Use on live-backed screens; keep `MOCK_TODAY` for mock data only. */
export function todayDhaka() {
  return dhakaDateFmt.format(new Date())
}

/** "Today, 11:42 AM", "Yesterday, 9:10 AM", "3 Nov, 4:00 PM" against the mock today. */
export function fmtWhen(ts, today = MOCK_TODAY) {
  const day = dhakaDate(ts)
  const time = fmtTime(ts)
  const gap = diffDays(today, day)
  if (gap === 0) return `Today, ${time}`
  if (gap === 1) return `Yesterday, ${time}`
  return `${fmtShort(day)}, ${time}`
}

/** "Today", "Tomorrow", "in 3 days", "3 days ago". */
export function relativeDay(iso, today = MOCK_TODAY) {
  const gap = diffDays(iso, today)
  if (gap === 0) return 'Today'
  if (gap === 1) return 'Tomorrow'
  if (gap === -1) return 'Yesterday'
  if (gap > 1) return `in ${gap} days`
  return `${-gap} days ago`
}

/** A timestamp for "now" on the mock day, using the real Dhaka clock time. */
export function mockNow() {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date())
  return `${MOCK_TODAY}T${parts}+06:00`
}

export function plural(n, one, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}
