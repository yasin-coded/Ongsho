import { lookupServiceKey } from '@/lib/services'
import { apiRequest } from '../http'
import { idStr } from '../adapters/common'

function mapCategory(row) {
  return {
    id: idStr(row.id),
    name: row.name,
    inUse: row.in_use,
    preset: Boolean(row.is_preset),
  }
}

function mapServiceName(row, categories) {
  const categoryId = idStr(row.category)
  const category = categories?.find((c) => c.id === categoryId)
  const fallbackCategory = categories?.find((c) => c.name === 'Other')
  return {
    id: idStr(row.id),
    name: row.name,
    serviceKey: lookupServiceKey(row.name),
    categoryId: categoryId ?? fallbackCategory?.id ?? null,
    ownerId: row.owner ? idStr(row.owner) : null,
    inUse: row.in_use,
    preset: Boolean(row.is_preset),
  }
}

export async function getCategories() {
  const data = await apiRequest('get', '/api/categories/')
  const rows = Array.isArray(data) ? data : data.results ?? []
  return rows.map(mapCategory)
}

export async function createCategory({ name }) {
  const data = await apiRequest('post', '/api/categories/', { data: { name } })
  return mapCategory(data)
}

export async function deleteCategory(id) {
  await apiRequest('delete', `/api/categories/${Number(id)}/`)
}

export async function getServiceNames() {
  const [names, categories] = await Promise.all([
    apiRequest('get', '/api/service-names/'),
    getCategories(),
  ])
  const rows = Array.isArray(names) ? names : names.results ?? []
  return rows.map((row) => mapServiceName(row, categories))
}

export async function createServiceName({ name, categoryId }) {
  const data = await apiRequest('post', '/api/service-names/', {
    data: { name, category: Number(categoryId) },
  })
  const categories = await getCategories()
  return mapServiceName(data, categories)
}

export async function deleteServiceName(id) {
  await apiRequest('delete', `/api/service-names/${Number(id)}/`)
}
