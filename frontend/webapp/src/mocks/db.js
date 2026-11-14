import { MOCK_TODAY, addDays } from '@/lib/dates'
import { hashIndex } from '@/lib/colors'
import { dueDatesBetween, periodEndFor, priceAt, splitCharge } from './schedule'

export const ME = 'u-yasin'
/** The next cycle's charge and dues appear this many days before the renewal date. */
export const LEAD_DAYS = 10

const at = (date, time) => `${date}T${time}:00+06:00`

const TID_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
function makeTid(seed) {
  let out = ''
  let h = hashIndex(seed, 2 ** 31)
  for (let i = 0; i < 8; i += 1) {
    h = (h * 1103515245 + 12345) % 2 ** 31
    out += TID_ALPHABET[h % TID_ALPHABET.length]
  }
  return out
}

function seed() {
  const users = [
    { id: ME, name: 'Yasin Bin Ahsan', email: 'yasin@example.com', pendingEmail: 'yasin.new@example.com', avatarColor: '#e87400' },
    { id: 'u-safa', name: 'Safa Rahman', email: 'safa@example.com', avatarColor: '#ff00ff' },
    { id: 'u-araf', name: 'Araf Hossain', email: 'araf@example.com', avatarColor: '#2f6fed' },
    { id: 'u-sami', name: 'Sami Karim', email: 'sami@example.com', avatarColor: '#00b8a9' },
    { id: 'u-rumi', name: 'Rumi Akter', email: 'rumi@example.com', avatarColor: '#f2c400' },
    { id: 'u-nabil', name: 'Nabil Chowdhury', email: 'nabil@example.com', avatarColor: '#846ace' },
    { id: 'u-tania', name: 'Tania Islam', email: 'tania@example.com', avatarColor: '#14b3f2' },
    { id: 'u-sameer', name: 'Sameer Haque', email: 'sameer@example.com', avatarColor: '#6d1b3a' },
    { id: 'u-mehal', name: 'Mehal Ahmed', email: 'mehal@example.com', avatarColor: '#2fd600' },
    { id: 'u-nila', name: 'Nila Sultana', email: 'nila@example.com', avatarColor: '#ff0000' },
    { id: 'u-rafi', name: 'Rafi Uddin', email: 'rafi@example.com', avatarColor: '#2f6fed' },
    { id: 'u-tuhin', name: 'Tuhin Das', email: 'tuhin@example.com', avatarColor: '#f2c400' },
  ]

  const categories = [
    { id: 'c-streaming', name: 'Streaming', ownerId: null },
    { id: 'c-music', name: 'Music', ownerId: null },
    { id: 'c-ai', name: 'AI tools', ownerId: null },
    { id: 'c-software', name: 'Software', ownerId: null },
    { id: 'c-hosting', name: 'Hosting', ownerId: null },
    { id: 'c-internet', name: 'Internet', ownerId: null },
    { id: 'c-utilities', name: 'Utilities', ownerId: null },
    { id: 'c-learning', name: 'Learning', ownerId: ME },
    { id: 'c-cloud', name: 'Cloud storage', ownerId: ME },
    { id: 'c-gaming', name: 'Gaming', ownerId: 'u-safa' },
  ]

  const serviceNames = [
    { id: 's-netflix', name: 'Netflix', serviceKey: 'netflix', categoryId: 'c-streaming', ownerId: null },
    { id: 's-spotify', name: 'Spotify', serviceKey: 'spotify', categoryId: 'c-streaming', ownerId: null },
    { id: 's-youtube', name: 'YouTube Premium', serviceKey: 'youtube', categoryId: 'c-streaming', ownerId: null },
    { id: 's-apple', name: 'Apple Music', serviceKey: 'apple_music', categoryId: 'c-streaming', ownerId: null },
    { id: 's-chatgpt', name: 'ChatGPT', serviceKey: 'chatgpt', categoryId: 'c-ai', ownerId: null },
    { id: 's-claude', name: 'Claude', serviceKey: 'claude', categoryId: 'c-ai', ownerId: null },
    { id: 's-cursor', name: 'Cursor', serviceKey: 'cursor', categoryId: 'c-ai', ownerId: null },
    { id: 's-google', name: 'Google One', serviceKey: 'google', categoryId: 'c-software', ownerId: null },
    { id: 's-prime', name: 'Amazon Prime Video', serviceKey: 'prime', categoryId: 'c-streaming', ownerId: null },
    { id: 's-hotstar', name: 'Disney+ Hotstar', serviceKey: 'hotstar', categoryId: 'c-streaming', ownerId: null },
    { id: 's-canva', name: 'Canva', serviceKey: 'canva', categoryId: 'c-software', ownerId: null },
    { id: 's-coursera', name: 'Coursera Plus', serviceKey: null, categoryId: 'c-learning', ownerId: ME },
  ]

  const monthly = { unit: 'month', count: 1 }
  const plans = [
    {
      id: 'p-netflix', ownerId: ME, serviceKey: 'netflix', serviceName: 'Netflix', planName: 'Netflix Premium', mode: 'owner',
      categoryId: 'c-streaming', currency: 'BDT', cycle: monthly, startDate: '2026-06-05', renewal: 'auto', status: 'active',
      method: 'bkash', note: 'Pay by the 4th, please.', rarelyUsed: false, seats: 4, split: 'equal', shared: true,
      prices: [{ amount: 110000, effectiveFrom: '2026-06-05' }, { amount: 120000, effectiveFrom: '2026-09-05' }],
      createdAt: at('2026-06-01', '20:00'),
    },
    {
      id: 'p-spotify', ownerId: ME, serviceKey: 'spotify', serviceName: 'Spotify', planName: 'Spotify Family', mode: 'owner',
      categoryId: 'c-streaming', currency: 'BDT', cycle: monthly, startDate: '2026-10-24', trialEnd: '2026-11-07', renewal: 'auto',
      status: 'trial', method: 'nagad', note: '', rarelyUsed: false, seats: 3, split: 'equal', shared: true,
      prices: [{ amount: 51000, effectiveFrom: '2026-10-24' }],
      createdAt: at('2026-10-24', '18:30'),
    },
    {
      id: 'p-youtube', ownerId: ME, serviceKey: 'youtube', serviceName: 'YouTube Premium', planName: 'YouTube Premium', mode: 'owner',
      categoryId: 'c-streaming', currency: 'USD', cycle: monthly, startDate: '2026-03-12', renewal: 'auto', status: 'active',
      method: 'bkash', note: '', rarelyUsed: true, seats: 1, split: 'equal', shared: false,
      prices: [{ usdCents: 1800, rate: 12000, effectiveFrom: '2026-03-12' }, { usdCents: 2000, rate: 12200, effectiveFrom: '2026-09-12' }],
      createdAt: at('2026-03-12', '09:00'),
    },
    {
      id: 'p-chatgpt', ownerId: ME, serviceKey: 'chatgpt', serviceName: 'ChatGPT', planName: 'ChatGPT Plus', mode: 'reseller',
      categoryId: 'c-ai', currency: 'USD', cycle: monthly, startDate: '2026-04-22', renewal: 'auto', status: 'active',
      method: 'bank', note: 'Login details go out after the ID is confirmed.', rarelyUsed: false, seats: 3, split: 'equal', shared: true,
      prices: [{ usdCents: 2000, rate: 12200, effectiveFrom: '2026-04-22' }],
      createdAt: at('2026-04-20', '15:00'),
    },
    {
      id: 'p-google', ownerId: ME, serviceKey: 'google', serviceName: 'Google One', planName: 'Google One 2 TB', mode: 'owner',
      categoryId: 'c-cloud', currency: 'BDT', cycle: { unit: 'year', count: 1 }, startDate: '2026-01-18', renewal: 'auto', status: 'active',
      method: 'bank', note: '', rarelyUsed: false, seats: 1, split: 'equal', shared: false,
      prices: [{ amount: 350000, effectiveFrom: '2026-01-18' }],
      createdAt: at('2026-01-18', '12:00'),
    },
    {
      id: 'p-claude', ownerId: ME, serviceKey: 'claude', serviceName: 'Claude', planName: 'Claude Pro', mode: 'owner',
      categoryId: 'c-ai', currency: 'USD', cycle: monthly, startDate: '2026-07-01', renewal: 'auto', status: 'paused', pausedOn: '2026-10-01',
      method: 'bkash', note: '', rarelyUsed: false, seats: 1, split: 'equal', shared: false,
      prices: [{ usdCents: 2000, rate: 12200, effectiveFrom: '2026-07-01' }],
      createdAt: at('2026-07-01', '11:00'),
    },
    {
      id: 'p-canva', ownerId: 'u-sameer', serviceKey: 'canva', serviceName: 'Canva', planName: 'Canva Pro', mode: 'owner',
      categoryId: 'c-software', currency: 'BDT', cycle: monthly, startDate: '2026-07-08', renewal: 'auto', status: 'active',
      method: 'bkash', note: 'Send it before the 8th so I can renew on time.', rarelyUsed: false, seats: 2, split: 'equal', shared: true,
      skipDates: ['2026-08-08'],
      prices: [{ amount: 100000, effectiveFrom: '2026-07-08' }],
      createdAt: at('2026-07-01', '10:00'),
    },
    {
      id: 'p-apple', ownerId: 'u-mehal', serviceKey: 'apple_music', serviceName: 'Apple Music', planName: 'Apple Music Duo', mode: 'owner',
      categoryId: 'c-streaming', currency: 'BDT', cycle: monthly, startDate: '2026-09-15', renewal: 'auto', status: 'active',
      method: 'bkash', note: 'Any time before the 15th is fine.', rarelyUsed: false, seats: 2, split: 'equal', shared: true,
      prices: [{ amount: 36000, effectiveFrom: '2026-09-15' }],
      createdAt: at('2026-09-01', '19:00'),
    },
    {
      id: 'p-hotstar', ownerId: 'u-nila', serviceKey: 'hotstar', serviceName: 'Disney+ Hotstar', planName: 'Disney+ Hotstar Premium', mode: 'owner',
      categoryId: 'c-streaming', currency: 'BDT', cycle: monthly, startDate: '2026-10-10', renewal: 'auto', status: 'active',
      method: 'nagad', note: '', rarelyUsed: false, seats: 4, split: 'equal', shared: true,
      prices: [{ amount: 100000, effectiveFrom: '2026-10-10' }],
      createdAt: at('2026-10-09', '21:00'),
    },
  ]

  const m = (id, planId, userId, joinedOn, extra = {}) => ({
    id, planId, userId, joinedOn, status: 'active', leftOn: null, leaveRequestedAt: null, isOwnerSeat: false, prefMethod: 'bkash', ...extra,
  })
  const members = [
    m('m-n-yasin', 'p-netflix', ME, '2026-06-01', { isOwnerSeat: true }),
    m('m-n-safa', 'p-netflix', 'u-safa', '2026-06-02', { prefMethod: 'bkash' }),
    m('m-n-araf', 'p-netflix', 'u-araf', '2026-06-02', { prefMethod: 'bkash' }),
    m('m-n-sami', 'p-netflix', 'u-sami', '2026-06-03', { prefMethod: 'nagad', status: 'leave_requested', leaveRequestedAt: at(MOCK_TODAY, '09:20') }),
    m('m-n-rumi', 'p-netflix', 'u-rumi', '2026-06-03', { prefMethod: 'rocket', status: 'left', leftOn: '2026-08-20' }),
    m('m-s-yasin', 'p-spotify', ME, '2026-10-24', { isOwnerSeat: true }),
    m('m-s-safa', 'p-spotify', 'u-safa', '2026-10-26'),
    m('m-s-araf', 'p-spotify', 'u-araf', '2026-11-03'),
    m('m-c-nabil', 'p-chatgpt', 'u-nabil', '2026-04-21', { prefMethod: 'bank' }),
    m('m-c-tania', 'p-chatgpt', 'u-tania', '2026-04-21', { prefMethod: 'mobile_banking' }),
    m('m-cv-sameer', 'p-canva', 'u-sameer', '2026-07-01', { isOwnerSeat: true }),
    m('m-cv-yasin', 'p-canva', ME, '2026-07-01'),
    m('m-a-mehal', 'p-apple', 'u-mehal', '2026-09-01', { isOwnerSeat: true }),
    m('m-a-yasin', 'p-apple', ME, '2026-09-01'),
    m('m-h-nila', 'p-hotstar', 'u-nila', '2026-10-09', { isOwnerSeat: true }),
    m('m-h-rafi', 'p-hotstar', 'u-rafi', '2026-10-09', { prefMethod: 'nagad' }),
    m('m-h-tuhin', 'p-hotstar', 'u-tuhin', '2026-10-09', { prefMethod: 'nagad' }),
  ]

  // ---- charges, dues and the default confirmed payments ----
  const charges = []
  const dues = []
  const payments = []
  const horizon = addDays(MOCK_TODAY, LEAD_DAYS)

  for (const plan of plans) {
    const until = plan.status === 'trial' ? addDays(plan.trialEnd, -1) : horizon
    for (const date of dueDatesBetween(plan, plan.startDate, until)) {
      if (plan.status === 'trial' && date > MOCK_TODAY) continue
      const price = priceAt(plan, date)
      const charge = {
        id: `ch-${plan.id}-${date}`, planId: plan.id, periodStart: date, periodEnd: periodEndFor(plan, date), dueDate: date,
        ...price, locked: date <= MOCK_TODAY,
      }
      charges.push(charge)
      if (!plan.shared) continue
      const planMembers = members.filter((x) => x.planId === plan.id)
      for (const share of splitCharge(plan, planMembers, charge.amount, date)) {
        const member = planMembers.find((x) => x.id === share.memberId)
        const due = {
          id: `due-${charge.id}-${member.id}`, chargeId: charge.id, planId: plan.id, memberId: member.id, amount: share.amount,
          status: 'due', waiverNote: null, rejectionReason: null, paidOn: null, recordedByOwner: false, note: null,
        }
        dues.push(due)
        if (member.isOwnerSeat) {
          due.status = 'paid'
          due.paidOn = date
          continue
        }
        if (date < MOCK_TODAY) {
          due.status = 'paid'
          due.paidOn = addDays(date, -1)
          payments.push({
            id: `pay-${due.id}`, planId: plan.id, payerMemberId: member.id, method: member.prefMethod,
            tid: makeTid(due.id), amount: share.amount, paidOn: null, recordedBy: member.userId,
            review: 'confirmed', submittedAt: at(addDays(date, -1), '20:15'), reviewedAt: at(addDays(date, -1), '22:40'),
            rejectionReason: null, allocations: [{ dueId: due.id, amount: share.amount }],
          })
        }
      }
    }
  }

  const dueOf = (planId, date, memberId) => dues.find((d) => d.chargeId === `ch-${planId}-${date}` && d.memberId === memberId)
  const paymentFor = (due) => {
    if (!due) return null
    return payments.find((p) => p.allocations?.some((a) => a.dueId === due.id))
  }
  const dropPayment = (due) => {
    if (!due) return
    const p = paymentFor(due)
    if (p) payments.splice(payments.indexOf(p), 1)
  }
  const setPayment = (due, fields) => {
    const p = paymentFor(due)
    if (!p) return
    Object.assign(p, fields)
  }
  const pending = (due, { method, tid, time, payer }) => {
    if (!due) return
    dropPayment(due)
    due.status = 'pending'
    due.paidOn = null
    payments.push({
      id: `pay-${due.id}`, planId: due.planId, payerMemberId: payer ?? due.memberId, method, tid, amount: due.amount, paidOn: null,
      recordedBy: members.find((x) => x.id === (payer ?? due.memberId)).userId, review: 'pending',
      submittedAt: at(MOCK_TODAY, time), reviewedAt: null, rejectionReason: null, allocations: [{ dueId: due.id, amount: due.amount }],
    })
  }

  // Netflix, October: Safa paid Araf's share together with her own, so Araf owes Safa.
  {
    const safaOct = dueOf('p-netflix', '2026-10-05', 'm-n-safa')
    const arafOct = dueOf('p-netflix', '2026-10-05', 'm-n-araf')
    if (safaOct && arafOct) {
      dropPayment(arafOct)
      const p = paymentFor(safaOct)
      if (p) {
        p.amount = safaOct.amount + arafOct.amount
        p.allocations.push({ dueId: arafOct.id, amount: arafOct.amount })
      }
    }
  }
  // Netflix, November cycle (renews today): Safa confirmed, Araf and Sami waiting for review.
  {
    const safa = dueOf('p-netflix', '2026-11-05', 'm-n-safa')
    safa.status = 'paid'
    safa.paidOn = '2026-11-04'
    payments.push({
      id: `pay-${safa.id}`, planId: 'p-netflix', payerMemberId: 'm-n-safa', method: 'bkash', tid: '7HQ2M4XR', amount: safa.amount,
      paidOn: '2026-11-04', recordedBy: 'u-safa', review: 'confirmed', submittedAt: at('2026-11-04', '21:08'),
      reviewedAt: at('2026-11-04', '22:30'), rejectionReason: null, allocations: [{ dueId: safa.id, amount: safa.amount }],
    })
    pending(dueOf('p-netflix', '2026-11-05', 'm-n-araf'), { method: 'bkash', tid: '8K2L9QX4', time: '11:42' })
    pending(dueOf('p-netflix', '2026-11-05', 'm-n-sami'), { method: 'nagad', tid: '8K3YT9X4', time: '09:15' })
  }
  // Canva Pro (Sameer owns): first bill waived, then Nagad / bKash (no due on plan start).
  {
    const aug = dueOf('p-canva', '2026-08-08', 'm-cv-yasin')
    if (aug) {
      dropPayment(aug)
      aug.status = 'waived'
      aug.paidOn = null
      aug.waiverNote = 'First month is on me.'
    }
    setPayment(dueOf('p-canva', '2026-09-08', 'm-cv-yasin'), { method: 'nagad', tid: '5U7M2RQ3' })
    setPayment(dueOf('p-canva', '2026-10-08', 'm-cv-yasin'), { method: 'bkash', tid: '5T7M2LQA' })
  }
  // Apple Music Duo (Mehal owns): one ID rejected, then confirmed (first bill Oct 15).
  {
    const oct = dueOf('p-apple', '2026-10-15', 'm-a-yasin')
    if (oct) {
      setPayment(oct, { method: 'bkash', tid: 'AM4HX8PD', submittedAt: at('2026-10-14', '19:02') })
      payments.push({
        id: 'pay-apple-oct-rejected', planId: 'p-apple', payerMemberId: 'm-a-yasin', method: 'bkash', tid: 'AM4HX8BD', amount: oct.amount,
        paidOn: null, recordedBy: ME, review: 'rejected', submittedAt: at('2026-10-13', '22:10'), reviewedAt: at('2026-10-14', '08:30'),
        rejectionReason: 'The ID does not match my bKash history. Please check one letter.', allocations: [{ dueId: oct.id, amount: oct.amount }],
      })
    }
    setPayment(dueOf('p-apple', '2026-11-15', 'm-a-yasin'), { method: 'nagad', tid: 'AM9RT2KC' })
    pending(dueOf('p-apple', '2026-12-15', 'm-a-yasin'), { method: 'bkash', tid: 'AM7Q4KZ2', time: '10:05' })
  }

  const invites = [
    { id: 'inv-n-1', planId: 'p-netflix', email: 'safa@example.com', status: 'accepted', invitedBy: ME, createdAt: at('2026-06-01', '20:10'), expiresOn: '2026-06-08', acceptedBy: 'u-safa', token: 'tok-netflix-safa' },
    { id: 'inv-n-2', planId: 'p-netflix', email: 'tuhin.old@example.com', status: 'cancelled', invitedBy: ME, createdAt: at('2026-08-21', '10:00'), expiresOn: '2026-08-28', acceptedBy: null, token: 'tok-netflix-old' },
    { id: 'inv-c-1', planId: 'p-chatgpt', email: 'mitu@example.com', status: 'pending', invitedBy: ME, createdAt: at('2026-11-03', '16:20'), expiresOn: '2026-11-10', acceptedBy: null, token: 'q7Lr2xVf9KcP' },
    { id: 'inv-s-1', planId: 'p-spotify', email: 'araf@example.com', status: 'accepted', invitedBy: ME, createdAt: at('2026-10-26', '12:00'), expiresOn: '2026-11-02', acceptedBy: 'u-araf', token: 'tok-spotify-araf' },
    { id: 'inv-h-yasin', planId: 'p-hotstar', email: 'yasin@example.com', status: 'pending', invitedBy: 'u-nila', createdAt: at(MOCK_TODAY, '08:30'), expiresOn: '2026-11-12', acceptedBy: null, token: 'hotstar-yasin' },
    { id: 'inv-new-user', planId: 'p-netflix', email: 'nadia@example.com', status: 'pending', invitedBy: 'u-safa', createdAt: at(MOCK_TODAY, '07:50'), expiresOn: '2026-11-12', acceptedBy: null, token: 'new-person' },
  ]

  const transfers = [
    { id: 'tr-canva', planId: 'p-canva', fromUserId: 'u-sameer', toUserId: ME, status: 'pending', createdAt: at('2026-11-03', '18:40') },
  ]

  const n = (id, kind, title, detail, createdAt, extra = {}) => ({
    id, userId: ME, kind, title, detail, createdAt, readAt: null, link: null, action: null, resolved: null, ...extra,
  })
  const notifications = [
    n('n-01', 'payment_submitted', 'Araf sent a transaction ID', 'Netflix Premium · bKash · ID 8K2L9QX4 · ৳300.00', at(MOCK_TODAY, '11:42'),
      { link: '/app/plans/p-netflix/review', action: { type: 'payment', paymentId: 'pay-due-ch-p-netflix-2026-11-05-m-n-araf' } }),
    n('n-02', 'leave_request', 'Sami wants to leave', 'Netflix Premium · needs your OK before the next renewal', at(MOCK_TODAY, '09:20'),
      { link: '/app/plans/p-netflix?leave=m-n-sami', action: { type: 'leave', memberId: 'm-n-sami', planId: 'p-netflix' } }),
    n('n-03', 'payment_submitted', 'Sami sent a transaction ID', 'Netflix Premium · Nagad · ID 8K3YT9X4 · ৳300.00', at(MOCK_TODAY, '09:15'),
      { link: '/app/plans/p-netflix/review', action: { type: 'payment', paymentId: 'pay-due-ch-p-netflix-2026-11-05-m-n-sami' } }),
    n('n-04', 'invite', 'Invite from Nila', 'Disney+ Hotstar Premium · shared plan · 4 seats · ৳250.00 share a month', at(MOCK_TODAY, '08:30'),
      { action: { type: 'invite', inviteId: 'inv-h-yasin' } }),
    n('n-05', 'renewal', 'Netflix Premium renews today', 'Pay Netflix ৳1,200.00 the usual way. Members have been reminded.', at(MOCK_TODAY, '07:00'),
      { link: '/app/plans/p-netflix', readAt: at(MOCK_TODAY, '07:30') }),
    n('n-06', 'payment_submitted', 'Safa sent a transaction ID', 'Netflix Premium · bKash · ID 7HQ2M4XR · ৳300.00', at('2026-11-04', '21:08'),
      { link: '/app/plans/p-netflix/review', resolved: 'approved', readAt: at('2026-11-04', '22:30') }),
    n('n-07', 'trial_end', 'Spotify Family trial ends on 7 Nov', 'The first charge of ৳510.00 starts that day. Pay Spotify before it does.', at('2026-11-04', '07:00'),
      { link: '/app/plans/p-spotify' }),
    n('n-08', 'email_changed', 'Confirm your new email', 'We sent a link to yasin.new@example.com. Your old address keeps working until then.', at('2026-11-04', '13:12'),
      { link: '/app/profile', readAt: at('2026-11-04', '13:20') }),
    n('n-09', 'transfer', 'Sameer wants to hand you Canva Pro', 'Canva Pro · ownership transfer · you would become the owner', at('2026-11-03', '18:40'),
      { action: { type: 'transfer', transferId: 'tr-canva' } }),
    n('n-10', 'invite_accepted', 'Araf joined Spotify Family', 'Spotify Family · 3 of 3 seats taken', at('2026-11-03', '12:05'),
      { link: '/app/plans/p-spotify', readAt: at('2026-11-03', '14:00') }),
    n('n-11', 'due_soon', 'Canva Pro is due on 8 Nov', 'Pay Sameer ৳500.00, then send the transaction ID.', at('2026-11-01', '08:00'),
      { link: '/app/shared/p-canva' }),
    n('n-12', 'payment_confirmed', 'Mehal confirmed your payment', 'Apple Music Duo · Nagad · ID AM9RT2KC · covered October', at('2026-10-14', '22:40'),
      { link: '/app/shared/p-apple', readAt: at('2026-10-15', '08:00') }),
    n('n-13', 'payment_confirmed', 'Sameer confirmed your payment', 'Canva Pro · bKash · ID 5T7M2LQA · covered October', at('2026-10-07', '22:40'),
      { link: '/app/shared/p-canva', readAt: at('2026-10-08', '09:00') }),
    n('n-14', 'plan_deleted', 'Rafi deleted Hoichoi Annual', 'The plan had no confirmed payments, so it was removed for everyone.', at('2026-10-02', '17:30'),
      { readAt: at('2026-10-03', '09:00') }),
    n('n-15', 'payment_rejected', 'Mehal could not match your ID', 'Apple Music Duo · ID AM4HX8BD · "The ID does not match my bKash history."', at('2026-09-14', '08:30'),
      { link: '/app/shared/p-apple', readAt: at('2026-09-14', '09:00') }),
    n('n-16', 'price_change', 'Netflix Premium costs ৳1,200.00 from 5 Sep', 'Each of the 4 seats moves from ৳275.00 to ৳300.00. Old months keep the old price.', at('2026-08-28', '10:00'),
      { link: '/app/plans/p-netflix', readAt: at('2026-08-28', '11:00') }),
    n('n-17', 'amount_changed', 'Netflix shares changed', 'Rumi left Netflix Premium, so the next charge splits 4 ways instead of 5.', at('2026-08-20', '19:00'),
      { link: '/app/plans/p-netflix', readAt: at('2026-08-20', '20:00') }),
  ]

  return {
    users, categories, serviceNames, plans, members, charges, dues, payments, invites, transfers, notifications,
    audit: [],
    reminderSettings: { daysBefore: [7, 1], email: true },
    seq: 1,
  }
}

export const db = seed()

export function resetDb() {
  Object.assign(db, seed())
}

export function nextId(prefix) {
  db.seq += 1
  return `${prefix}-${Date.now().toString(36)}-${db.seq}`
}

export { makeTid }
