import { describe, expect, it } from 'vitest'
import { AVATAR_COLORS } from '@/lib/colors'
import { avatarColorFromId, avatarIdFromColor } from './me'

describe('avatar mapping', () => {
  it('maps color to id and back', () => {
    const color = AVATAR_COLORS[3]
    const id = avatarIdFromColor(color)
    expect(avatarColorFromId(id)).toBe(color)
  })
})
