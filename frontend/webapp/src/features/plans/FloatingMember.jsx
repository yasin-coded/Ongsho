import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BadgeCheck, Download, Eye, HandCoins, UserMinus, X } from 'lucide-react'
import { downloadRosterMemberStatement, getMember } from '@/api/plans'
import { METHODS } from '@/lib/colors'
import { formatBDT } from '@/lib/money'
import { monthKey, todayDhaka } from '@/lib/dates'
import { useAction } from '@/hooks/useAction'
import { Button, LinkButton } from '@/components/ui/Button'
import { Avatar } from '@/components/ui/Avatar'
import { StatusPill } from '@/components/ui/Pill'
import { Select } from '@/components/ui/Field'
import { Box } from '@/components/ui/Box'
import { ErrorBox, Skeleton } from '@/components/ui/Misc'

function EmptyWindow() {
  return (
    <Box className="float-win grid min-h-[12rem] content-center gap-3 text-center" aria-label="Member details">
      <p className="t-meta t-muted px-2">Pick a member and tap Open to see their latest payments on this plan.</p>
    </Box>
  )
}

function MemberStatementDownload({ memberId, rows }) {
  const months = useMemo(() => {
    const entries = rows.map((r) => [monthKey(r.dueDate), r.monthLabel]).filter(([k]) => Boolean(k))
    return [...new Map(entries).entries()]
  }, [rows])
  const [month, setMonth] = useState(() => monthKey(todayDhaka()))
  const statementMonth = months.some(([k]) => k === month) ? month : (months[0]?.[0] ?? monthKey(todayDhaka()))
  const download = useAction(() => downloadRosterMemberStatement(memberId, { month: statementMonth }), {
    toastMessage: (r) => (r?.number ? `Downloaded statement ${r.number}.` : 'Statement downloaded.'),
  })
  if (!months.length) return null
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Select
        label="Statement month"
        value={statementMonth}
        onChange={(e) => setMonth(e.target.value)}
        options={months.map(([value, label]) => ({ value, label }))}
        fieldClass="min-w-[10rem]"
      />
      <Button variant="ghost" icon={Download} busy={download.busy} onClick={() => download.run()}>
        Download statement
      </Button>
    </div>
  )
}

function WindowBody({ member, planId, onClose, onRemove, onAction, rowRefs }) {
  const closeRef = useRef(null)
  useEffect(() => {
    closeRef.current?.focus()
    const opener = rowRefs?.current?.[member.id]
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      opener?.focus()
    }
  }, [onClose, rowRefs, member.id])

  return (
    <Box className="float-win grid gap-5" role="dialog" aria-labelledby={`member-${member.id}`}>
      <button ref={closeRef} type="button" className="icon-btn float-win__close" onClick={onClose} aria-label="Close member window">
        <X aria-hidden="true" className="size-5" />
      </button>
      <div className="grid justify-items-center gap-3 pt-4 text-center">
        <Avatar name={member.name} color={member.avatarColor} size="lg" decorative />
        <div className="grid gap-1">
          <h3 id={`member-${member.id}`} className="t-card">
            {member.name}
            {member.isOwnerSeat ? ' (you)' : ''}
          </h3>
          <p className="t-meta break-all">{member.email}</p>
        </div>
        {member.dueStatus && <StatusPill status={member.dueStatus} />}
      </div>
      <div>
        <p className="t-label mb-2">
          Payments {member.rows.length > 0 && <span className="t-meta font-normal normal-case">(latest 5)</span>}
        </p>
        {member.rows.length ? (
          <ul className="dashed-rows">
            {member.rows.map((r) => (
              <li key={r.id} className="row-between py-2.5">
                <span className="t-meta font-bold">
                  {r.monthLabel}
                  {r.method ? ` · ${METHODS[r.method]?.label}` : ''}
                  {r.tid ? ` · ${r.tid}` : ''}
                </span>
                <span className="row gap-2">
                  <span className="t-num">{formatBDT(r.amount, { trim: true })}</span>
                  <StatusPill status={r.status} small />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="t-meta">No payments yet.</p>
        )}
      </div>
      <MemberStatementDownload memberId={member.id} rows={member.rows} />
      <div className="float-win__actions row flex-wrap justify-end gap-2">
        {member.isOwnerSeat && member.dueId && member.dueStatus === 'due' && (
          <Button variant="accept" size="sm" icon={BadgeCheck} onClick={() => onAction?.('markPaid', member)}>
            Mark paid
          </Button>
        )}
        {member.dueId && member.dueStatus === 'due' && (
          <Button variant="waive" size="sm" icon={HandCoins} onClick={() => onAction?.('waive', member)}>
            Waive
          </Button>
        )}
        {member.pendingPaymentId && (
          <LinkButton to={`/app/plans/${planId}/review`} variant="review" size="sm" icon={Eye}>
            Review Payment
          </LinkButton>
        )}
        {!member.isOwnerSeat && member.status !== 'left' && (
          <Button variant="ghost" size="sm" icon={UserMinus} onClick={() => onRemove(member)}>
            Remove
          </Button>
        )}
      </div>
    </Box>
  )
}

export function FloatingMember({ memberId, planId, onClose, onRemove, onAction, rowRefs, sheet }) {
  const query = useQuery({ queryKey: ['member', memberId], queryFn: () => getMember(memberId), enabled: Boolean(memberId) })
  const inner = !memberId ? (
    <EmptyWindow />
  ) : query.isPending ? (
    <Box className="float-win">
      <Skeleton className="h-48" />
    </Box>
  ) : query.isError ? (
    <Box className="float-win">
      <ErrorBox error={query.error} onRetry={() => query.refetch()} />
    </Box>
  ) : (
    <WindowBody member={query.data} planId={planId} onClose={onClose} onRemove={onRemove} onAction={onAction} rowRefs={rowRefs} />
  )
  if (sheet) {
    if (!memberId) return null
    return (
      <div className="float-sheet" onClick={(e) => e.target === e.currentTarget && onClose()}>
        {inner}
      </div>
    )
  }
  return <div className="float-win--dock">{inner}</div>
}