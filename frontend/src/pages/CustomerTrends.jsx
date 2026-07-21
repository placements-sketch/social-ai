import { useState, useEffect } from 'react'
import { Loader2, TrendingUp, Clock } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { getCustomerTrends } from '../api/customers'

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}
function compactKES(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(Math.round(n || 0))
}

// Segment → colour, aligned with the app's segment palette.
const SEG_COLORS = {
  vip: '#f59e0b', loyal: '#ec4899', regular: '#3b82f6', new: '#22c55e',
  never_bought: '#94a3b8', at_risk: '#f97316', churned: '#6b7280',
}
const SEG_LABELS = {
  vip: 'VIP', loyal: 'Loyal', regular: 'Regular', new: 'New',
  never_bought: 'Never bought', at_risk: 'At risk', churned: 'Churned',
}

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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Revenue contribution by segment */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-1">
          <TrendingUp size={14} className="text-brand-500" /> Revenue by Segment
        </h2>
        <p className="text-xs text-gray-400 mb-4">Where the money actually comes from — usually a different shape than headcount.</p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={revenueData} margin={{ top: 4, right: 8, left: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                   tickFormatter={compactKES} />
            <Tooltip
              formatter={(v) => [`KES ${formatKES(v)}`, 'Revenue']}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
            />
            <Bar dataKey="revenue" radius={[4, 4, 0, 0]}>
              {revenueData.map((entry, i) => (
                <Cell key={i} fill={SEG_COLORS[entry.segment] || '#6b7280'} />
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
        <p className="text-xs text-gray-400 mb-4">How long since each buyer's last order.</p>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={recencyData} margin={{ top: 4, right: 8, left: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                   tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
            <Tooltip
              formatter={(v) => [`${formatKES(v)} customers`, 'Buyers']}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
            />
            <Bar dataKey="customers" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}