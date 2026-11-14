import { describe, expect, it } from 'vitest'
import { AVATAR_COLORS } from '@/lib/colors'
import { avatarColorFromId, avatarIdFromColor } from './me'

describe('avatar mapping', () => {
  it('maps color to id and back', () => {
    const color = AVATAR_COLORS[3]
    const id = avatarIdFromColor(color)
    expect(id).toBe('avatar_4')
    expect(avatarColorFromId(id)).toBe(color)
    expect(avatarColorFromId('avatar_4')).toBe(color)
  })
})
