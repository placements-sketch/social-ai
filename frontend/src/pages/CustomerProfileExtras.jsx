import { useState, useEffect, useMemo } from 'react'
import { Loader2, Award, Repeat, Coins, CalendarDays, Package, Tag, Activity } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { getCustomerProfile } from '../api/customers'

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

// One RFM tile (R / F / M), 1–5 with a subtle fill bar.
function RfmTile({ label, value, Icon }) {
  const pct = value ? (value / 5) * 100 : 0
  return (
    <div className="flex-1 rounded-xl border border-gray-200 bg-white px-3 py-3 text-center">
      <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
        <Icon size={12} />
        <span className="text-[11px] font-bold uppercase tracking-widest">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900 leading-none">{value ?? '—'}</p>
      <div className="mt-2 h-1 rounded-full bg-gray-100 overflow-hidden">
        <div className="h-full bg-brand-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// Horizontal bar list (used for brands + top items).
function BarList({ items, labelKey, valueKey, valueFormat }) {
  if (!items || items.length === 0) {
    return <p className="text-xs text-gray-400 py-4 text-center">No data yet</p>
  }
  const max = Math.max(...items.map(i => i[valueKey] || 0)) || 1
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="text-xs text-gray-600 truncate w-28 shrink-0" title={it[labelKey]}>{it[labelKey]}</span>
          <div className="flex-1 h-4 rounded bg-gray-100 overflow-hidden">
            <div className="h-full bg-brand-400 rounded" style={{ width: `${((it[valueKey] || 0) / max) * 100}%` }} />
          </div>
          <span className="text-xs font-semibold text-gray-700 tabular-nums w-12 text-right shrink-0">
            {valueFormat ? valueFormat(it[valueKey]) : it[valueKey]}
          </span>
        </div>
      ))}
    </div>
  )
}

// ─── Spending trend ──────────────────────────────────────────
// The series is built server-side now. It used to be aggregated in the browser
// from the raw order list, which summed every order the customer ever placed —
// including 141 voided ones worth KES 1.72M that never changed hands — so the
// chart contradicted the lifetime-spend figure directly above it.
function SpendingTrend({ series }) {
  const [showAll, setShowAll] = useState(false)
  const all = series || []
  // Default to the last 12 months, but say so and offer the rest. This used to
  // slice(-12) with nothing on screen to indicate that 42 further months of
  // history existed, so the chart looked like the customer's whole life.
  const data = useMemo(() => (showAll ? all : all.slice(-12)), [all, showAll])

  if (!all.length) {
    return (
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4">
          <Activity size={14} className="text-brand-500" /> Spending Trend
        </h2>
        <div className="text-center py-14">
          <Activity size={28} className="text-gray-300 mx-auto mb-2" />
          <p className="text-xs text-gray-400">No paid orders yet</p>
        </div>
      </div>
    )
  }

  const total = data.reduce((a, b) => a + (b.spent || 0), 0)
  const orders = data.reduce((a, b) => a + (b.orders || 0), 0)
  const quiet = data.filter(d => !d.orders).length

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3 mb-1">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
          <Activity size={14} className="text-brand-500" /> Spending Trend
        </h2>
        {all.length > 12 && (
          <div className="flex rounded-lg border border-gray-200 overflow-hidden shrink-0">
            {[['Last 12 months', false], [`All ${all.length} months`, true]].map(([label, v]) => (
              <button
                key={label}
                onClick={() => setShowAll(v)}
                className={showAll === v
                  ? 'px-2.5 py-1 text-[11px] font-semibold bg-brand-500 text-black'
                  : 'px-2.5 py-1 text-[11px] font-medium text-gray-500 hover:text-gray-900'}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="text-[11px] text-gray-400 mb-4">
        {data[0].month} – {data[data.length - 1].month} · KES {formatKES(total)} across{' '}
        {formatKES(orders)} paid orders
        {quiet > 0 && ` · ${quiet} month${quiet > 1 ? 's' : ''} with no orders`}
      </p>

      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
          <defs>
            <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#99e600" stopOpacity={0.32} />
              <stop offset="100%" stopColor="#99e600" stopOpacity={0} />
            </linearGradient>
          </defs>
          {/* Was #f3f4f6 — a light-theme grey hard-coded into a card that is
              near-black in dark mode. Theme variables follow the theme. */}
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
            axisLine={false} tickLine={false}
            interval="preserveStartEnd"
            minTickGap={showAll ? 24 : 4}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
            axisLine={false} tickLine={false} width={44}
            tickFormatter={v => (v >= 1000 ? `${Math.round(v / 1000)}k` : v)}
          />
          {/* The default tooltip is a white box with a light border, which in
              dark mode was a glare panel with pale grey text inside it. */}
          <Tooltip
            cursor={{ stroke: 'var(--border)', strokeWidth: 1 }}
            contentStyle={{
              fontSize: 12, borderRadius: 10, padding: '8px 10px',
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              color: 'var(--text)', boxShadow: '0 4px 16px rgba(0,0,0,.28)',
            }}
            labelStyle={{ color: 'var(--text)', fontWeight: 700, marginBottom: 2 }}
            itemStyle={{ color: 'var(--text)' }}
            formatter={(value, _n, entry) => {
              const n = entry?.payload?.orders ?? 0
              return [`KES ${formatKES(value)} · ${n} order${n === 1 ? '' : 's'}`, 'Paid']
            }}
          />
          <Area
            type="monotone" dataKey="spent" stroke="#99e600" strokeWidth={2.5}
            fill="url(#spendGrad)"
            dot={showAll ? false : { r: 3, fill: '#99e600' }}
            activeDot={{ r: 4, fill: '#99e600' }}
          />
        </AreaChart>
      </ResponsiveContainer>

      <p className="text-[11px] text-gray-400 mt-3 pt-3 border-t border-gray-100">
        Paid orders only, at the amount charged — voided, pending and fully
        refunded orders are excluded. Partial refunds are not deducted, so this
        runs slightly above the lifetime spend figure, which is net of refunds.
      </p>
    </div>
  )
}

export default function CustomerProfileExtras({ customerId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCustomerProfile(customerId)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [customerId])

  if (loading) {
    return (
      <div className="card p-5 flex items-center justify-center h-32">
        <Loader2 size={18} className="animate-spin text-gray-400" />
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="card p-5">
        <p className="text-xs text-gray-400">Couldn't load RFM profile{error ? `: ${error}` : ''}.</p>
      </div>
    )
  }

  const { rfm, customer_since, items_by_brand, top_items, spend_over_time } = data

  return (
    <div className="space-y-5">

      {/* Suggested Action is gone.

          It was SEGMENT_ACTIONS[segment] — one fixed sentence per segment, the
          same "Send VIP invite + exclusive early access to new drops" on every
          VIP in the book. It read as advice about this customer and was a lookup
          on a single field, so it told an agent nothing they had not already
          learned from the VIP badge two inches above it. Advice that cannot be
          wrong also cannot be useful. */}

      {/* Items bought per brand.
          This was labelled "Spend by Brand" and showed no money at all — the
          numbers are item counts. orders_cache.products stores only the line
          titles (no price, no quantity), so spend per brand is not computable
          from what we hold; the count is the honest measure and the heading now
          says so. */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
          <Tag size={14} className="text-brand-500" /> Items Bought by Brand
        </h2>
        <p className="text-[11px] text-gray-400 mb-4">
          Individual items, all time · top {(items_by_brand || []).length} brands
        </p>
        <BarList items={items_by_brand} labelKey="brand" valueKey="items" />
        {(items_by_brand || []).some(b => b.brand === 'Other') && (
          <p className="text-[11px] text-gray-400 mt-3 pt-3 border-t border-gray-100">
            <span className="font-semibold">Other</span> — items whose brand is no
            longer in the catalogue, so there is nothing left to match them against.
          </p>
        )}
      </div>

      {/* Top items purchased */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4">
          <Package size={14} className="text-brand-500" /> Top Items Purchased
        </h2>
        <BarList items={top_items} labelKey="name" valueKey="count" />
      </div>

      <SpendingTrend series={spend_over_time} />
    </div>
  )
}