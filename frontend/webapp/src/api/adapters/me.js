import { AVATAR_COLORS } from '@/lib/colors'
import { idStr } from './common'

export function avatarIdFromColor(color) {
  const idx = AVATAR_COLORS.indexOf(color)
  if (idx < 0) return 'avatar_1'
  return `avatar_${idx + 1}`
}

export function avatarColorFromId(avatarId) {
  if (!avatarId) return AVATAR_COLORS[0]
  const key = String(avatarId).trim()
  const tagged = /^avatar_(\d+)$/i.exec(key)
  const n = tagged ? Number(tagged[1]) : Number(key) || 1
  return AVATAR_COLORS[Math.min(Math.max(n - 1, 0), AVATAR_COLORS.length - 1)]
}

export function mapUserFromApi(user) {
  if (!user) return null
  const avatarColor = avatarColorFromId(user.avatar_id)
  return {
    id: idStr(user.id),
    email: user.email,
    name: user.name,
    avatarColor,
    emailVerified: user.email_verified ?? true,
    pendingEmail: user.pending_email ?? null,
    plansOwned: user.plans_owned ?? 0,
    plansJoined: user.plans_joined ?? 0,
  }
}

export function mapMePatch({ name, avatarColor }) {
  const body = {}
  if (name !== undefined) body.name = name
  if (avatarColor) body.avatar_id = avatarIdFromColor(avatarColor)
  return body
}
