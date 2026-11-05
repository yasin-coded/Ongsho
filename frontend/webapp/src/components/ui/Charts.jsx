import { Bar, BarChart, Cell, LabelList, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { formatBDT } from '@/lib/money'

function ChartTip({ active, payload, labelKey = 'label' }) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload
  return (
    <div className="rounded-xl border-[0.1875rem] border-black bg-white px-3 py-2 shadow-[var(--shadow-neo-sm)]">
      <p className="t-meta font-bold">{item[labelKey] ?? item.name}</p>
      <p className="t-num font-bold">{formatBDT(item.value ?? item.total, { trim: true })}</p>
    </div>
  )
}

/** Donut with the hard black outline and the small yellow centre from the wireframe. */
export function Donut({ data, size = 9, label, center = true }) {
  const total = data.reduce((a, d) => a + d.value, 0)
  return (
    <figure className="m-0">
      <div className="relative" style={{ width: `${size}rem`, height: `${size}rem` }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={total ? data : [{ name: 'none', value: 1, fill: '#eeeccc' }]} dataKey="value" innerRadius="48%" outerRadius="88%" stroke="#000" strokeWidth={3} startAngle={90} endAngle={-270} isAnimationActive={false}>
              {(total ? data : [{ fill: '#eeeccc' }]).map((d, i) => (
                <Cell key={i} fill={d.fill} />
              ))}
            </Pie>
            {total > 0 && <Tooltip content={<ChartTip labelKey="name" />} />}
          </PieChart>
        </ResponsiveContainer>
        {center && <span className="pointer-events-none absolute top-1/2 left-1/2 size-[22%] -translate-x-1/2 -translate-y-1/2 rounded-full border-[0.1875rem] border-black bg-[#fff200]" />}
      </div>
      <figcaption className="sr-only">
        {label}: {data.map((d) => `${d.name} ${formatBDT(d.value, { trim: true })}`).join(', ')}
      </figcaption>
    </figure>
  )
}

export function ForecastBars({ data, colors, height = 15 }) {
  const rows = data.map((d) => ({ ...d, value: d.total, fill: colors[d.kind] }))
  return (
    <figure className="m-0">
      <div style={{ height: `${height}rem` }} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 28, right: 8, left: 8, bottom: 0 }} barCategoryGap="22%">
            <XAxis dataKey="label" axisLine={{ stroke: '#000', strokeWidth: 3 }} tickLine={false} tick={{ fill: '#000', fontSize: '0.875rem', fontFamily: 'Bahnschrift', fontWeight: 700 }} />
            <Tooltip cursor={{ fill: 'rgba(0,0,0,0.06)' }} content={<ChartTip />} />
            <Bar dataKey="value" stroke="#000" strokeWidth={3} radius={[10, 10, 0, 0]} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.key} fill={r.fill} />
              ))}
              <LabelList dataKey="value" position="top" formatter={(v) => formatBDT(v, { compact: true })} style={{ fill: '#000', fontSize: '0.875rem', fontFamily: 'Bahnschrift', fontWeight: 700 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="sr-only">
        <table>
          <caption>Next 6 months</caption>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <th scope="row">
                  {r.label} {r.year}
                </th>
                <td>{formatBDT(r.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  )
}

export function Legend({ items, compact }) {
  return (
    <ul className="chart-legend grid gap-2">
      {items.map((i) => (
        <li
          key={i.name}
          className={compact ? 'grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-2 gap-y-0.5' : 'flex min-w-0 items-start justify-between gap-2'}
        >
          <span className="row min-w-0 gap-2">
            <span className="size-3.5 flex-none rounded-[0.25rem] border-[0.1875rem] border-black sm:size-4" style={{ background: i.fill }} aria-hidden="true" />
            <span className="t-meta min-w-0 text-[0.8125rem] leading-snug break-words sm:text-[0.875rem]">{i.name}</span>
          </span>
          {i.value !== undefined && (
            <span className="t-num shrink-0 text-right text-[0.8125rem] font-bold sm:text-[0.875rem]">{formatBDT(i.value, { trim: true, compact: compact })}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
