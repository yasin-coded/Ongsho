import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { getCalendar } from '@/api/dashboard'
import { SERVICES } from '@/lib/services'
import { CUSTOM_PALETTE, hashIndex } from '@/lib/colors'
import { addDays, addMonthsToKey, dayOfMonth, fmtFull, fmtMonthYearLong, monthKey, todayDhaka, weekday, weekdayName } from '@/lib/dates'
import { formatBDT } from '@/lib/money'
import { TopBar } from '@/components/layout/TopBar'
import { Box, BoxHead, cx } from '@/components/ui/Box'
import { Button } from '@/components/ui/Button'
import { DateBadge, ErrorBox, Skeleton } from '@/components/ui/Misc'
import { EventList, eventWord } from '@/features/common/PlanBits'

const WEEK = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
const WEEK_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function serviceColor(event) {
  return SERVICES[event.serviceKey]?.color ?? CUSTOM_PALETTE[hashIndex(event.planName, CUSTOM_PALETTE.length)]
}

/** Sunday-first weeks covering the month: 5 or 6 rows. */
function monthGrid(key) {
  const first = `${key}-01`
  const start = addDays(first, -weekday(first))
  const weeks = []
  let day = start
  do {
    const week = []
    for (let i = 0; i < 7; i += 1) {
      week.push(day)
      day = addDays(day, 1)
    }
    weeks.push(week)
  } while (monthKey(day) === key)
  return weeks
}

function useWideCells(ref) {
  const [wide, setWide] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const ro = new ResizeObserver(([entry]) => {
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
      setWide(entry.contentRect.width / 7 >= 7 * rem)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return wide
}

function DayCell({ date, today, inMonth, events, selected, wide, onSelect, focusRef }) {
  const isToday = date === today
  const shown = events.slice(0, 3)
  const extra = events.length - shown.length
  const label = `${WEEK_LONG[weekday(date)]}, ${fmtFull(date)}${isToday ? ', today' : ''}. ${events.length ? events.map((e) => `${e.planName} ${eventWord(e)}`).join(', ') : 'Nothing on this day'}.`
  return (
    <td role="gridcell" aria-selected={selected} className="p-0.5 align-top sm:p-1">
      <button
        ref={selected ? focusRef : undefined}
        type="button"
        tabIndex={selected ? 0 : -1}
        aria-label={label}
        onClick={() => onSelect(date)}
        className={cx(
          'grid min-h-[3.75rem] w-full content-start gap-1 rounded-[0.75rem] border-[0.1875rem] bg-white p-1.5 text-left sm:min-h-[5.5rem] sm:p-2',
          selected ? 'border-[var(--color-selected)] shadow-[0_0_0_0.1875rem_var(--color-selected)]' : 'border-black',
          isToday && 'outline-[0.3rem] outline-offset-2 outline-black outline-solid',
          !inMonth && 'opacity-40',
        )}
      >
        <span className={cx('font-[family-name:var(--font-display)] text-[0.95rem] leading-none font-bold sm:text-[1.1rem]', isToday && 'underline decoration-[0.15rem] underline-offset-4')}>{dayOfMonth(date)}</span>
        {events.length > 0 &&
          (wide ? (
            <span className="grid gap-0.5" aria-hidden="true">
              {shown.map((e) => (
                <span key={e.id} className="flex min-w-0 items-center gap-1 text-[0.75rem] leading-tight font-bold">
                  <span className="size-2.5 flex-none rounded-full border-2 border-black" style={{ background: serviceColor(e) }} />
                  <span className="truncate">{e.planName.split(' ')[0]}</span>
                </span>
              ))}
              {extra > 0 && <span className="text-[0.75rem] font-bold">+{extra}</span>}
            </span>
          ) : (
            <span className="flex flex-wrap items-center gap-0.5" aria-hidden="true">
              {shown.map((e) => (
                <span key={e.id} className="size-2.5 rounded-full border-2 border-black sm:size-3" style={{ background: serviceColor(e) }} />
              ))}
              {extra > 0 && <span className="text-[0.7rem] font-bold">+{extra}</span>}
            </span>
          ))}
      </button>
    </td>
  )
}

export function CalendarPage() {
  const today = todayDhaka()
  const [key, setKey] = useState(() => monthKey(todayDhaka()))
  const [selected, setSelected] = useState(() => todayDhaka())
  const query = useQuery({ queryKey: ['calendar', key], queryFn: () => getCalendar(key), placeholderData: keepPreviousData })
  const tableRef = useRef(null)
  const focusRef = useRef(null)
  const moved = useRef(false)
  const wide = useWideCells(tableRef)
  const weeks = useMemo(() => monthGrid(key), [key])

  const byDay = useMemo(() => {
    const map = new Map()
    for (const e of query.data?.events ?? []) map.set(e.date, [...(map.get(e.date) ?? []), e])
    return map
  }, [query.data])

  useEffect(() => {
    if (moved.current) {
      focusRef.current?.focus()
      moved.current = false
    }
  }, [selected, key, query.data])

  const select = (date, { focus = false } = {}) => {
    setSelected(date)
    if (monthKey(date) !== key) setKey(monthKey(date))
    moved.current = focus
  }

  const onKeyDown = (e) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key]
    if (step) {
      e.preventDefault()
      select(addDays(selected, step), { focus: true })
    } else if (e.key === 'Home') {
      e.preventDefault()
      select(addDays(selected, -weekday(selected)), { focus: true })
    } else if (e.key === 'End') {
      e.preventDefault()
      select(addDays(selected, 6 - weekday(selected)), { focus: true })
    }
  }

  const changeMonth = (n) => {
    const next = addMonthsToKey(key, n)
    setKey(next)
    setSelected(monthKey(today) === next ? today : `${next}-01`)
  }

  const dayEvents = monthKey(selected) === key ? byDay.get(selected) ?? [] : []

  return (
    <div className="stack-lg">
      <TopBar title="Calendar" subtitle="See every date in one place." tools={false} />
      <div className="two-col cal-layout">
        <Box roomy className="cal-layout__month !min-w-0 !rounded-[2rem]">
          <div className="mb-5 row-between">
            <h2 className="t-section" aria-live="polite">
              {fmtMonthYearLong(`${key}-01`)}
            </h2>
            <div className="row gap-2">
              <button type="button" className="icon-btn" onClick={() => changeMonth(-1)} aria-label="Previous month">
                <ChevronLeft aria-hidden="true" className="size-5" />
              </button>
              <Button variant="yellow" size="sm" onClick={() => select(today)}>
                Today
              </Button>
              <button type="button" className="icon-btn" onClick={() => changeMonth(1)} aria-label="Next month">
                <ChevronRight aria-hidden="true" className="size-5" />
              </button>
            </div>
          </div>
          {query.isError ? (
            <ErrorBox error={query.error} onRetry={() => query.refetch()} />
          ) : (
            <table ref={tableRef} role="grid" aria-label={`${fmtMonthYearLong(`${key}-01`)}. Use the arrow keys to move between days.`} className="w-full table-fixed border-collapse" onKeyDown={onKeyDown} aria-busy={query.isFetching}>
              <thead>
                <tr>
                  {WEEK.map((d, i) => (
                    <th key={d} scope="col" abbr={WEEK_LONG[i]} className="pb-2 font-[family-name:var(--font-display)] text-[0.7rem] font-bold sm:text-[0.8rem]">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {weeks.map((week) => (
                  <tr key={week[0]}>
                    {week.map((date) => (
                      <DayCell key={date} date={date} today={today} inMonth={monthKey(date) === key} events={monthKey(date) === key ? byDay.get(date) ?? [] : []} selected={date === selected} wide={wide} onSelect={(d) => select(d)} focusRef={focusRef} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Box>

        <div className="cal-layout__side stack min-w-0">
          <Box aria-live="polite" className="min-w-0 overflow-hidden">
            <div className="mb-4 row-between gap-2">
              <p className="t-sub min-w-0 truncate">{weekdayName(selected).toUpperCase()}</p>
              <DateBadge date={selected} />
            </div>
            {query.isPending ? (
              <Skeleton className="h-16" />
            ) : dayEvents.length ? (
              <ul className="dashed-rows">
                {dayEvents.map((e) => (
                  <li key={e.id} className="grid gap-1 py-3">
                    <span className="row min-w-0 gap-2">
                      <span className="size-4 flex-none rounded-full border-[0.1875rem] border-black" style={{ background: serviceColor(e) }} aria-hidden="true" />
                      <span className="t-sub min-w-0 truncate">{e.planName}</span>
                    </span>
                    <span className="row-between gap-2">
                      <span className="t-label min-w-0 truncate uppercase">{eventWord(e)}</span>
                      {e.amount > 0 && <span className="t-num shrink-0 font-bold">{formatBDT(e.amount, { trim: true, compact: true })}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="t-meta">Nothing on this day.</p>
            )}
          </Box>
          <Box className="min-w-0 overflow-hidden">
            <BoxHead title="Next 7 days" />
            {query.data ? <EventList events={query.data.next7} /> : <Skeleton className="h-32" />}
          </Box>
        </div>
      </div>
    </div>
  )
}
