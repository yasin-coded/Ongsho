import { delegate } from './delegate'
import * as mock from './mock/catalog'
import * as live from './live/catalog'

export const getCategories = delegate(live, mock, 'getCategories')
export const createCategory = delegate(live, mock, 'createCategory')
export const deleteCategory = delegate(live, mock, 'deleteCategory')
export const getServiceNames = delegate(live, mock, 'getServiceNames')
export const createServiceName = delegate(live, mock, 'createServiceName')
export const deleteServiceName = delegate(live, mock, 'deleteServiceName')
