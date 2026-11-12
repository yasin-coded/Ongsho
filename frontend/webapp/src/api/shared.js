import { delegate } from './delegate'
import * as mock from './mock/shared'
import * as live from './live/shared'

export const getMyShared = delegate(live, mock, 'getMyShared')
export const getMySharedPlan = delegate(live, mock, 'getMySharedPlan')
export const requestLeave = delegate(live, mock, 'requestLeave')
export const cancelLeaveRequest = delegate(live, mock, 'cancelLeaveRequest')
export const downloadMyStatement = delegate(live, mock, 'downloadMyStatement')
export const acceptInvite = delegate(live, mock, 'acceptInvite')
export const declineInvite = delegate(live, mock, 'declineInvite')
export const acceptInviteAsNewUser = delegate(live, mock, 'acceptInviteAsNewUser')
export const acceptTransfer = delegate(live, mock, 'acceptTransfer')
export const declineTransfer = delegate(live, mock, 'declineTransfer')
