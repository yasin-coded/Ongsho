import { describe, expect, it } from 'vitest'
import { AVATAR_COLORS } from '@/lib/colors'
import { ME } from '@/mocks/db'
import { profileCounts } from '@/mocks/selectors'
import { avatarColorFromId, avatarIdFromColor, mapUserFromApi } from './me'

const apiUserBase = {
  id: 1,
  email: 'a@example.com',
  name: 'Ada',
  avatar_id: 'avatar_1',
  email_verified: true,
  pending_email: null,
}

describe('avatar mapping', () => {
  it('maps color to id and back', () => {
    const color = AVATAR_COLORS[3]
    const id = avatarIdFromColor(color)
    expect(id).toBe('avatar_4')
    expect(avatarColorFromId(id)).toBe(color)
    expect(avatarColorFromId('avatar_4')).toBe(color)
  })
})

describe('mapUserFromApi', () => {
  it('maps plan counts from API', () => {
    const user = mapUserFromApi({ ...apiUserBase, plans_owned: 3, plans_joined: 2 })
    expect(user.plansOwned).toBe(3)
    expect(user.plansJoined).toBe(2)
  })

  it('defaults missing or null plan counts to 0', () => {
    expect(mapUserFromApi({ ...apiUserBase }).plansOwned).toBe(0)
    expect(mapUserFromApi({ ...apiUserBase }).plansJoined).toBe(0)
    expect(mapUserFromApi({ ...apiUserBase, plans_owned: null, plans_joined: null }).plansOwned).toBe(0)
    expect(mapUserFromApi({ ...apiUserBase, plans_owned: null, plans_joined: null }).plansJoined).toBe(0)
  })

  it('matches mock profileCounts field names', () => {
    const mockCounts = profileCounts(ME)
    const liveShape = mapUserFromApi({
      ...apiUserBase,
      plans_owned: mockCounts.plansOwned,
      plans_joined: mockCounts.plansJoined,
    })
    expect(Object.keys(mockCounts).sort()).toEqual(['plansJoined', 'plansOwned'])
    expect(liveShape.plansOwned).toBe(mockCounts.plansOwned)
    expect(liveShape.plansJoined).toBe(mockCounts.plansJoined)
  })
})
