import { useState, useEffect } from 'react'
import { Loader2, TrendingUp, Clock } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { getCustomerTrends } from '../api/customers'
import { SEGMENT_COLORS, SEGMENT_LABELS, SEGMENT_FALLBACK } from '../utils/segments'

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}
function compactKES(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n || 0))
}

// Both tooltips were hardcoded to a white card with a light border, so on a
// dark page they were white slabs with unreadable content. These variables flip
// with the theme (index.css defines them under :root and .dark).
//
// Note --text, not --text-primary: the latter does not exist here, and an
// undefined CSS variable fails silently and inherits, which is a colour bug with
// nothing on screen to explain it.
const TOOLTIP_STYLE = {
  fontSize: 12,
  borderRadius: 8,
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  color: 'var(--text)',
}
const TOOLTIP_LABEL = { color: 'var(--text)', fontWeight: 600 }
const TOOLTIP_ITEM = { color: 'var(--text)' }
const TOOLTIP_CURSOR = { fill: 'var(--border)', fillOpacity: 0.35 }

// Aliased rather than renamed at every call site: the chart is the third
// consumer of the shared palette, and these two names are used throughout the
// file below.
const SEG_COLORS = SEGMENT_COLORS
const SEG_LABELS = SEGMENT_LABELS

export default function CustomerTrends() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCustomerTrends()
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="card p-5 flex items-center justify-center h-64">
        <Loader2 size={18} className="animate-spin text-gray-400" />
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="card p-5">
        <p className="text-xs text-gray-400">Couldn't load trends{error ? `: ${error}` : ''}.</p>
      </div>
    )
  }

  // Revenue by segment — exclude never_bought (always 0 revenue) so the bars are readable.
  const revenueData = (data.revenue_by_segment || [])
    .filter(s => s.segment !== 'never_bought')
    .map(s => ({ ...s, label: SEG_LABELS[s.segment] || s.segment }))

  const recencyData = (data.recency_buckets || []).map(b => ({
    ...b, label: b.bucket === '180+' ? '180d+' : `${b.bucket}d`,
  }))

  // Derived, not typed in. The caption used to read "the 125,102 who never
  // ordered are not counted" as a literal in the string. It was already wrong
  // — 125,123 by the time anyone checked — and it moves with every sync, so it
  // could only ever drift further. The count is already in the payload as the
  // never_bought segment row.
  const neverBought = (data.revenue_by_segment || [])
    .find(s => s.segment === 'never_bought')?.customers ?? 0
  const buyers = recencyData.reduce((a, b) => a + (b.customers || 0), 0)

  // 86% of buyers sit in one bucket, which flattens the other four into slivers.
  // The chart cannot say that itself, so the caption does.
  const biggest = recencyData.reduce((a, b) => (b.customers > (a?.customers ?? -1) ? b : a), null)
  const biggestShare = biggest && buyers ? Math.round((biggest.customers / buyers) * 100) : 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Revenue contribution by segment */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-1">
          <TrendingUp size={14} className="text-brand-500" /> Revenue by Segment
        </h2>
        <p className="text-xs text-gray-400 mb-4">
          Shopify's "Total spent" per customer, grouped by segment. Segments are ours —
          Shopify has no such grouping — but every shilling is its figure, and these bars
          sum to the Revenue card exactly.
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={revenueData} margin={{ top: 4, right: 8, left: 4, bottom: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeOpacity={0.6} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false}
                   tickFormatter={compactKES} />
            <Tooltip
              formatter={(v) => [`KES ${formatKES(v)}`, 'Revenue']}
              contentStyle={TOOLTIP_STYLE}
              labelStyle={TOOLTIP_LABEL}
              itemStyle={TOOLTIP_ITEM}
              cursor={TOOLTIP_CURSOR}
            />
            <Bar dataKey="revenue" radius={[4, 4, 0, 0]}>
              {revenueData.map((entry, i) => (
                <Cell key={i} fill={SEG_COLORS[entry.segment] || SEGMENT_FALLBACK} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Customers by recency */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-1">
          <Clock size={14} className="text-brand-500" /> Customers by Recency
        </h2>
        <p className="text-xs text-gray-400 mb-4">
          How long since each buyer's last order, from Shopify's last-order date.
          {' '}{formatKES(buyers)} buyers — the {formatKES(neverBought)} who never
          ordered are not counted.
          {biggest && biggestShare >= 50 && (
            <> <span className="text-gray-500">{biggestShare}% of them fall in
            {' '}{biggest.label} alone, so the remaining bars are small by
            comparison, not by absence.</span></>
          )}
        </p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={recencyData} margin={{ top: 4, right: 8, left: 4, bottom: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeOpacity={0.6} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false}
                   tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
            <Tooltip
              formatter={(v) => [`${formatKES(v)} buyers`, 'Customers']}
              contentStyle={TOOLTIP_STYLE}
              labelStyle={TOOLTIP_LABEL}
              itemStyle={TOOLTIP_ITEM}
              cursor={TOOLTIP_CURSOR}
            />
            <Bar dataKey="customers" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}