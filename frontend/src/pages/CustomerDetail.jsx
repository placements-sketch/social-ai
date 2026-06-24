import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, ShoppingBag, TrendingUp,
  Repeat, Tag, Heart, Crown, Sparkles, AlertTriangle, UserMinus, Users,
  Loader2, AlertCircle, Package, UserPlus,
} from 'lucide-react'
import {
  LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import clsx from 'clsx'
import { parseBackendTime, formatDateAgo } from '../utils/time'
import { getCustomer, getCustomerOrders } from '../api/customers'

const SEGMENT_META = {
  vip:          { label: 'VIP',          icon: Crown,         color: 'text-amber-600',  bg: 'bg-amber-50',  border: 'border-amber-200' },
  loyal:        { label: 'Loyal',        icon: Heart,         color: 'text-pink-600',   bg: 'bg-pink-50',   border: 'border-pink-200' },
  regular:      { label: 'Regular',      icon: Users,         color: 'text-blue-600',   bg: 'bg-blue-50',   border: 'border-blue-200' },
  new:          { label: 'New Convert',  icon: Sparkles,      color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-200' },
  never_bought: { label: 'Never Bought', icon: UserPlus,      color: 'text-slate-600',  bg: 'bg-slate-50',  border: 'border-slate-200' },
  at_risk:      { label: 'At Risk',      icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200' },
  churned:      { label: 'Churned',      icon: UserMinus,     color: 'text-gray-600',   bg: 'bg-gray-100',  border: 'border-gray-300' },
}

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = parseBackendTime(iso)
  return d ? d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
}

// Aggregate orders into monthly spending for the trend chart
function buildSpendingTrend(orders) {
  if (!orders?.length) return []

  // Map: YYYY-MM → { month: 'Jun', spent: N }
  const monthly = new Map()
  for (const o of orders) {
    const d = parseBackendTime(o.date)
    if (!d) continue
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleString('en-US', { month: 'short', year: '2-digit' })
    const existing = monthly.get(key) || { key, month: label, spent: 0 }
    existing.spent += o.total || 0
    monthly.set(key, existing)
  }

  // Sort by key chronologically, take last 12
  return Array.from(monthly.values())
    .sort((a, b) => a.key.localeCompare(b.key))
    .slice(-12)
}

export default function CustomerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [customer, setCustomer] = useState(null)
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [custData, ordersData] = await Promise.all([
          getCustomer(id),
          getCustomerOrders(id),
        ])
        if (!active) return
        setCustomer(custData.customer)
        setOrders(ordersData.orders || [])
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [id])

  const trend = useMemo(() => buildSpendingTrend(orders), [orders])

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 size={24} className="animate-spin text-gray-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex gap-3">
        <AlertCircle size={18} className="text-red-600 shrink-0 mt-0.5" />
        <p className="text-sm font-medium text-red-900">{error}</p>
      </div>
    )
  }

  if (!customer) {
    return <p className="text-center text-gray-500 py-20">Customer not found</p>
  }

  const meta = SEGMENT_META[customer.segment] || SEGMENT_META.regular
  const SegIcon = meta.icon

  return (
    <div className="space-y-6 w-full max-w-6xl mx-auto">
      {/* Back + header */}
      <button onClick={() => navigate('/customers')} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-900 font-medium">
        <ArrowLeft size={13} /> Back to customers
      </button>

      {/* Customer card */}
      <div className="card p-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="flex items-start gap-4 min-w-0">
            <div className={clsx('w-14 h-14 rounded-full flex items-center justify-center shrink-0', meta.bg)}>
              <span className={clsx('text-xl font-bold', meta.color)}>
                {customer.first_name?.[0] || customer.name?.[0] || '?'}
              </span>
            </div>
            <div className="min-w-0">
              <h1 className="text-2xl font-bold text-gray-900 truncate">{customer.name}</h1>
              <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md mt-2', meta.bg, meta.color)}>
                <SegIcon size={11} />
                {meta.label}
              </span>
              <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-600">
                {customer.email && <span className="flex items-center gap-1.5"><Mail size={12} /> {customer.email}</span>}
                {customer.phone && <span className="flex items-center gap-1.5"><Phone size={12} /> {customer.phone}</span>}
                {customer.location && <span className="flex items-center gap-1.5"><MapPin size={12} /> {customer.location}</span>}
                {customer.created_at && (
                  <span className="flex items-center gap-1.5">
                    <Calendar size={12} /> Customer since {formatDate(customer.created_at)}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Tags */}
        {customer.tags?.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap gap-1.5">
            {customer.tags.slice(0, 10).map((t, i) => (
              <span key={i} className="inline-flex items-center gap-1 text-[11px] bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                <Tag size={9} />
                {t}
              </span>
            ))}
            {customer.tags.length > 10 && (
              <span className="text-[11px] text-gray-500 font-medium">+{customer.tags.length - 10} more</span>
            )}
          </div>
        )}
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="card p-4">
          <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide">Total Spent</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">KES {formatKES(customer.total_spent)}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide">Total Orders</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{formatKES(customer.total_orders)}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide">Avg Order Value</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">KES {formatKES(customer.aov)}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide">Last Order</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{formatDateAgo(customer.last_order_date)}</p>
          {customer.days_since_last_order != null && (
            <p className="text-xs text-gray-400 mt-1">{customer.days_since_last_order} days ago</p>
          )}
        </div>
      </div>

      {/* Spending trend */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4">Spending Trend</h2>
        {trend.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                     tickFormatter={v => `${(v / 1000).toFixed(0)}k`} />
              <Tooltip
                formatter={v => [`KES ${formatKES(v)}`, 'Spent']}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
              />
              <Line type="monotone" dataKey="spent" stroke="#ff5900" strokeWidth={2} dot={{ r: 4, fill: '#ff5900' }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-xs text-gray-400 text-center py-12">
            No order history yet — sync orders to populate this chart
          </p>
        )}
      </div>

      {/* Order history */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-gray-900">Order History</h2>
          {orders.length > 0 && (
            <span className="text-xs text-gray-500">{orders.length} orders</span>
          )}
        </div>
        {orders.length === 0 ? (
          <div className="text-center py-12">
            <Package size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500 font-medium">No orders yet</p>
            <p className="text-xs text-gray-400 mt-1">
              {customer.total_orders > 0
                ? 'Order data is still syncing — run the orders sync'
                : 'This customer has not placed any orders'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Order</th>
                  <th className="text-left px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Date</th>
                  <th className="text-right px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Items</th>
                  <th className="text-right px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Total</th>
                  <th className="text-center px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => (
                  <tr key={o.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-3 py-3 text-sm font-semibold text-gray-900">#{o.order_number || o.id}</td>
                    <td className="px-3 py-3 text-xs text-gray-600">{formatDate(o.date)}</td>
                    <td className="px-3 py-3 text-right text-sm text-gray-700">{o.items}</td>
                    <td className="px-3 py-3 text-right text-sm font-bold text-gray-900">
                      KES {formatKES(o.total)}
                    </td>
                    <td className="px-3 py-3 text-center">
                      <span className={clsx(
                        'inline-flex text-xs font-semibold px-2 py-1 rounded-md',
                        o.status === 'fulfilled' ? 'bg-green-50 text-green-700' :
                        o.status === 'refunded'  ? 'bg-red-50 text-red-700' :
                                                   'bg-amber-50 text-amber-700'
                      )}>
                        {o.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}