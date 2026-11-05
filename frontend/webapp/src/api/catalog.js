import { db, ME, nextId } from '@/mocks/db'
import { categoryInUse, visibleCategories, visibleServiceNames } from '@/mocks/selectors'
import { ApiError, read, write } from './client'

const shape = (c) => ({ id: c.id, name: c.name, preset: c.ownerId === null, inUse: categoryInUse(c.id) })

export function getCategories() {
  return read(() => visibleCategories(ME).map(shape), { empty: (list) => list.filter((c) => c.preset) })
}

export function createCategory({ name }) {
  return write(() => {
    const clean = (name ?? '').trim().replace(/\s+/g, ' ')
    if (!clean) throw new ApiError('Type a category name.', { fields: { name: 'Type a category name.' } })
    if (clean.length > 40) throw new ApiError('Keep it under 40 characters.', { fields: { name: 'Keep it under 40 characters.' } })
    if (visibleCategories(ME).some((c) => c.name.toLowerCase() === clean.toLowerCase())) {
      throw new ApiError('You already have that category.', { fields: { name: 'You already have that category.' } })
    }
    const cat = { id: nextId('c'), name: clean, ownerId: ME }
    db.categories.push(cat)
    return shape(cat)
  })
}

export function deleteCategory(id) {
  return write(() => {
    const cat = db.categories.find((c) => c.id === id && c.ownerId === ME)
    if (!cat) throw new ApiError('Built-in categories cannot be deleted.', { status: 403 })
    const using = db.plans.filter((p) => p.categoryId === id && !p.archivedOn)
    // Plans that used it move to the closest built-in group so nothing is left without a category.
    for (const plan of using) plan.categoryId = 'c-utilities'
    db.categories.splice(db.categories.indexOf(cat), 1)
    return { moved: using.length }
  })
}

export function getServiceNames() {
  return read(() =>
    visibleServiceNames(ME).map((s) => ({ id: s.id, name: s.name, serviceKey: s.serviceKey, categoryId: s.categoryId, preset: s.ownerId === null })),
  )
}

export function createServiceName({ name, categoryId }) {
  return write(() => {
    const clean = (name ?? '').trim().replace(/\s+/g, ' ')
    if (!clean) throw new ApiError('Type a service name.', { fields: { service: 'Type a service name.' } })
    if (visibleServiceNames(ME).some((s) => s.name.toLowerCase() === clean.toLowerCase())) {
      throw new ApiError('You already have that service name.', { fields: { service: 'You already have that service name.' } })
    }
    const item = { id: nextId('s'), name: clean, serviceKey: null, categoryId: categoryId ?? 'c-utilities', ownerId: ME }
    db.serviceNames.push(item)
    return item
  })
}

export function deleteServiceName(id) {
  return write(() => {
    const item = db.serviceNames.find((s) => s.id === id && s.ownerId === ME)
    if (!item) throw new ApiError('Built-in names cannot be deleted.', { status: 403 })
    db.serviceNames.splice(db.serviceNames.indexOf(item), 1)
  })
}
