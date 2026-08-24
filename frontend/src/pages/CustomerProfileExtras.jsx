import { useState, useEffect } from 'react'
import { Loader2, Award, Repeat, Coins, CalendarDays, Package, Tag } from 'lucide-react'
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
          <span className="text-xs font-semibold text-gray-700 tabular-nums w-10 text-right shrink-0">
            {valueFormat ? valueFormat(it[valueKey]) : it[valueKey]}
          </span>
        </div>
      ))}
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

  const { rfm, customer_since, spend_by_brand, top_items } = data

  return (
    <div className="space-y-5">

      {/* Suggested Action is gone.

          It was SEGMENT_ACTIONS[segment] — one fixed sentence per segment, the
          same "Send VIP invite + exclusive early access to new drops" on every
          VIP in the book. It read as advice about this customer and was a lookup
          on a single field, so it told an agent nothing they had not already
          learned from the VIP badge two inches above it. Advice that cannot be
          wrong also cannot be useful. */}

      {/* Spend by brand */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4">
          <Tag size={14} className="text-brand-500" /> Spend by Brand
        </h2>
        <BarList items={spend_by_brand} labelKey="brand" valueKey="items" />
      </div>

      {/* Top items purchased */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-4">
          <Package size={14} className="text-brand-500" /> Top Items Purchased
        </h2>
        <BarList items={top_items} labelKey="name" valueKey="count" />
      </div>
    </div>
  )
}