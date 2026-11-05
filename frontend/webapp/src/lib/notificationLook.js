import {
  ArrowRightLeft,
  AtSign,
  BadgeDollarSign,
  Bell,
  CalendarX,
  CheckCheck,
  CircleDollarSign,
  Clock,
  Eye,
  Handshake,
  Hourglass,
  LogOut,
  Mail,
  RefreshCw,
  Trash2,
  UserCheck,
  UserPlus,
  UserRound,
  UserX,
  Users,
  XCircle,
} from 'lucide-react'

/** Icon tile per notification (or attention) kind. */
const BY_KIND = {
  payment_submitted: { icon: CircleDollarSign, tile: '#fff200' },
  payment_confirmed: { icon: CheckCheck, tile: '#2fd600' },
  payment_rejected: { icon: XCircle, tile: '#ff1a1a' },
  payment_waived: { icon: CheckCheck, tile: '#846ace' },
  invite: { icon: Mail, tile: '#14b3f2' },
  invite_accepted: { icon: UserPlus, tile: '#00ff8b' },
  invite_declined: { icon: UserX, tile: '#846ace' },
  leave_request: { icon: LogOut, tile: '#846ace' },
  leave_result: { icon: UserCheck, tile: '#846ace' },
  transfer: { icon: ArrowRightLeft, tile: '#d9ccff' },
  transfer_result: { icon: Handshake, tile: '#d9ccff' },
  renewal: { icon: RefreshCw, tile: '#e87400' },
  trial_end: { icon: Hourglass, tile: '#14b3f2' },
  due_soon: { icon: Clock, tile: '#ff9700' },
  expiry: { icon: CalendarX, tile: '#ff1a1a' },
  email_changed: { icon: AtSign, tile: '#00a8e1' },
  plan_deleted: { icon: Trash2, tile: '#ff1a1a' },
  price_change: { icon: BadgeDollarSign, tile: '#ff9700' },
  amount_changed: { icon: Users, tile: '#ff9700' },
  review: { icon: Eye, tile: '#fff200' },
  leave: { icon: LogOut, tile: '#846ace' },
}

export function notificationLook(n) {
  if (BY_KIND[n.kind]) return BY_KIND[n.kind]
  if (n.kind?.startsWith('payment')) return BY_KIND.payment_submitted
  if (n.kind?.startsWith('invite')) return BY_KIND.invite
  if (n.kind?.startsWith('leave')) return BY_KIND.leave_request
  if (n.kind?.startsWith('transfer')) return BY_KIND.transfer
  if (n.group === 'reminders') return { icon: Bell, tile: '#e87400' }
  return { icon: UserRound, tile: '#00ff8b' }
}
