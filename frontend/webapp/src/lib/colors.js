function luminance(hex) {
  const c = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}

/** Black or white, whichever has the higher contrast on `hex`. */
export function inkOn(hex) {
  const l = luminance(hex)
  return (l + 0.05) / 0.05 >= 1.05 / (l + 0.05) ? '#000000' : '#ffffff'
}

export function hashIndex(text, size) {
  let h = 0
  for (const ch of String(text)) h = (h * 31 + ch.codePointAt(0)) >>> 0
  return h % size
}

export const AVATAR_COLORS = ['#ff0000', '#e87400', '#f2c400', '#2fd600', '#00b8a9', '#14b3f2', '#2f6fed', '#846ace', '#ff00ff', '#6d1b3a']

export function avatarColor(user) {
  return user?.avatarColor || AVATAR_COLORS[hashIndex(user?.name ?? '?', AVATAR_COLORS.length)]
}

export const STATUS = {
  due: { label: 'Due', fill: '#ff1a1a' },
  pending: { label: 'Pending', fill: '#fff200' },
  paid: { label: 'Paid', fill: '#2fd600' },
  waived: { label: 'Waived', fill: '#19c8f0' },
  trial: { label: 'Trial', fill: '#d9ccff' },
}

export const PLAN_STATUS = {
  active: { label: 'Active', fill: '#2fd600' },
  trial: { label: 'Trial', fill: '#d9ccff' },
  paused: { label: 'Paused', fill: '#c9c9c0' },
  cancelled: { label: 'Cancelled', fill: '#5c5c55' },
  expired: { label: 'Expired', fill: '#c9c9c0', strike: true },
}

export const METHODS = {
  bkash: { label: 'bKash', fill: '#e2136e' },
  nagad: { label: 'Nagad', fill: '#f26522' },
  rocket: { label: 'Rocket', fill: '#8c3494' },
  mobile_banking: { label: 'Mobile Banking', fill: '#0b6b3a' },
  bank: { label: 'Bank', fill: '#1c3d8f' },
  cash: { label: 'Cash', fill: '#9a6700' },
  other: { label: 'Other', fill: '#6b6b6b' },
}

export const METHOD_KEYS = Object.keys(METHODS)

export const CATEGORY_COLORS = {
  Streaming: '#6d28d9',
  Music: '#ff6fb5',
  'AI tools': '#00b8a9',
  Software: '#2f6fed',
  Hosting: '#f59e0b',
  Internet: '#06b6d4',
  Utilities: '#84cc16',
}

export const CUSTOM_PALETTE = ['#94a3b8', '#c084fc', '#fb923c', '#34d399', '#f472b6']

export function categoryColor(name) {
  return CATEGORY_COLORS[name] ?? CUSTOM_PALETTE[hashIndex(name, CUSTOM_PALETTE.length)]
}

export const CHART = {
  owned: '#ff00ff',
  joined: '#00ff8b',
  thisMonth: '#e87400',
  regular: '#846ace',
  yearly: '#000c7c',
}
