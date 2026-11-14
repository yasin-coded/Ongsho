const FORCE_MOCK = import.meta.env.VITE_FORCE_MOCK === 'true'

/** API functions wired to the Django backend by default (everything else stays on mock). */
const LIVE_FUNCTIONS = new Set([
  // accounts
  'register',
  'verifyEmail',
  'resendVerification',
  'login',
  'logout',
  'requestPasswordReset',
  'confirmPasswordReset',
  'getMe',
  'updateMe',
  'changePassword',
  'changeEmail',
  'resendEmailChange',
  'cancelEmailChange',
  'getReminderSettings',
  'updateReminderSettings',
  'getInvite',
  // catalog
  'getCategories',
  'createCategory',
  'deleteCategory',
  'getServiceNames',
  'createServiceName',
  'deleteServiceName',
  // plans
  'getSubscriptions',
  'getSubscription',
  'getPlanForm',
  'createSubscription',
  'updateSubscription',
  'deletePlan',
  'pausePlan',
  'resumePlan',
  'cancelPlan',
  'renewPlan',
  'setRarelyUsed',
  'updatePlanSplit',
  'addPriceChange',
  'correctRate',
  'createInvite',
  'cancelInvite',
  'decideLeave',
  'replaceMember',
  'startTransfer',
  'cancelTransfer',
  'getReview',
  'getLedger',
  'downloadOwnerStatement',
  'getMember',
  // payments
  'submitPayment',
  'confirmPayment',
  'rejectPayment',
  'reversePayment',
  'waivePayment',
  'waiveDue',
  'markDuePaid',
  'setDueBack',
  'normalizeTid',
  // dashboard
  'getDashboard',
  'getCalendar',
  'getNavCounts',
  'getNotifications',
  'markRead',
  'markAllRead',
  // shared
  'getMyShared',
  'getMySharedPlan',
  'downloadMyStatement',
  'acceptTransfer',
  'declineTransfer',
  'acceptInvite',
  'declineInvite',
  'acceptInviteAsNewUser',
  'getPlanJoin',
  'acceptPlanJoin',
  'signupAndJoinPlan',
  'requestLeave',
  'cancelLeaveRequest',
])

export function isLive(name) {
  if (FORCE_MOCK) return false
  return LIVE_FUNCTIONS.has(name)
}

export function forceMockMode() {
  return FORCE_MOCK
}
