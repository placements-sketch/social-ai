import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, ShoppingBag, TrendingUp,
  Repeat, Tag, Heart, Crown, Sparkles, AlertTriangle, UserMinus, Users,
  Loader2, AlertCircle, Package, UserPlus, ChevronLeft, ChevronRight,
  Activity, Clock, Award, Target, Zap, ExternalLink, Hash, CheckCircle2,
} from 'lucide-react'
import {
  AreaChart, Area, ResponsiveContainer, Tooltip, CartesianGrid, XAxis, YAxis,
} from 'recharts'
import clsx from 'clsx'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { formatDateAgo, formatTimeAgo, parseBackendTime } from '../utils/time'
import { getCustomer, getCustomerOrders } from '../api/customers'

const SEGMENT_META = {
  vip:          { label: 'VIP',          icon: Crown,         color: 'text-amber-600',  bg: 'bg-amber-50',  border: 'border-amber-200',  ring: 'ring-amber-400/30',  accent: 'from-amber-400 to-amber-600' },
  loyal:        { label: 'Loyal',        icon: Heart,         color: 'text-pink-600',   bg: 'bg-pink-50',   border: 'border-pink-200',   ring: 'ring-pink-400/30',   accent: 'from-pink-400 to-pink-600' },
  regular:      { label: 'Regular',      icon: Users,         color: 'text-blue-600',   bg: 'bg-blue-50',   border: 'border-blue-200',   ring: 'ring-blue-400/30',   accent: 'from-blue-400 to-blue-600' },
  new:          { label: 'New Convert',  icon: Sparkles,      color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-200',  ring: 'ring-green-400/30',  accent: 'from-green-400 to-green-600' },
  never_bought: { label: 'Never Bought', icon: UserPlus,      color: 'text-slate-600',  bg: 'bg-slate-50',  border: 'border-slate-200',  ring: 'ring-slate-400/30',  accent: 'from-slate-400 to-slate-500' },
  at_risk:      { label: 'At Risk',      icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200', ring: 'ring-orange-400/30', accent: 'from-orange-400 to-orange-600' },
  churned:      { label: 'Churned',      icon: UserMinus,     color: 'text-gray-600',   bg: 'bg-gray-100',  border: 'border-gray-300',   ring: 'ring-gray-400/30',   accent: 'from-gray-400 to-gray-600' },
}

const ORDERS_PER_PAGE = 10

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

function formatFullDate(iso) {
  const d = parseBackendTime(iso)
  if (!d) return '—'
  return d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ─── RFM score helpers ───────────────────────────────────────────
function recencyScore(daysSince) {
  if (daysSince == null) return 0
  if (daysSince <= 30) return 5
  if (daysSince <= 60) return 4
  if (daysSince <= 90) return 3
  if (daysSince <= 180) return 2
  return 1
}
function frequencyScore(orders) {
  if (!orders) return 0
  if (orders >= 10) return 5
  if (orders >= 5) return 4
  if (orders >= 3) return 3
  if (orders >= 2) return 2
  return 1
}
function monetaryScore(spent) {
  if (!spent) return 0
  if (spent >= 500000) return 5
  if (spent >= 100000) return 4
  if (spent >= 50000) return 3
  if (spent >= 10000) return 2
  return 1
}
function scoreColor(score) {
  if (score >= 5) return { bar: 'bg-green-500',  text: 'text-green-600',  bg: 'bg-green-50' }
  if (score >= 4) return { bar: 'bg-emerald-500', text: 'text-emerald-600', bg: 'bg-emerald-50' }
  if (score >= 3) return { bar: 'bg-amber-500',  text: 'text-amber-600',  bg: 'bg-amber-50' }
  if (score >= 2) return { bar: 'bg-orange-500', text: 'text-orange-600', bg: 'bg-orange-50' }
  if (score >= 1) return { bar: 'bg-red-500',    text: 'text-red-600',    bg: 'bg-red-50' }
  return { bar: 'bg-gray-300', text: 'text-gray-500', bg: 'bg-gray-50' }
}

// ─── KPI card with animated value ──────────────────────────────────
function KpiCard({ icon: Icon, label, value, sub, accent }) {
  const numeric = typeof value === 'number'
    ? value
    : parseFloat(String(value).replace(/[^0-9.-]/g, '')) || 0
  const animated = useCountAnimation(numeric, 1200)
  const formatted = typeof value === 'number'
    ? Math.round(animated).toLocaleString()
    : String(value).replace(/[\d,.]+/, Math.round(animated).toLocaleString())

  return (
    <div className="relative card p-4 overflow-hidden group hover:shadow-md transition-shadow">
      <div className={clsx('absolute -right-6 -top-6 w-20 h-20 rounded-full opacity-10 bg-gradient-to-br', accent)} />
      <div className="relative">
        <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center mb-3 bg-gradient-to-br', accent)}>
          <Icon size={16} className="text-white" />
        </div>
        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">{label}</p>
        <p className="text-xl font-bold text-gray-900 mt-1 truncate">{formatted}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5 truncate">{sub}</p>}
      </div>
    </div>
  )
}

// ─── RFM single-pillar card ────────────────────────────────────────
function RfmPillar({ icon: Icon, label, score, caption, scaleLabel }) {
  const c = scoreColor(score)
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center', c.bg)}>
            <Icon size={13} className={c.text} />
          </div>
          <span className="text-xs font-bold text-gray-700 uppercase tracking-wide">{label}</span>
        </div>
        <span className={clsx('text-xs font-bold', c.text)}>{score}/5</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-2">
        <div className={clsx('h-full rounded-full transition-all duration-700', c.bar)}
             style={{ width: `${(score / 5) * 100}%` }} />
      </div>
      <p className="text-[11px] text-gray-500 leading-relaxed">{caption}</p>
      <p className="text-[10px] text-gray-400 mt-1.5">{scaleLabel}</p>
    </div>
  )
}

export default function CustomerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [customer, setCustomer] = useState(null)
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const [cData, oData] = await Promise.all([
          getCustomer(id),
          getCustomerOrders(id),
        ])
        if (cancelled) return
        setCustomer(cData.customer)
        setOrders(oData.orders || [])
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [id])

  // Spending trend: aggregate orders by month
  const trend = useMemo(() => {
    if (!orders.length) return []
    const monthly = {}
    orders.forEach(o => {
      if (!o.date) return
      const d = new Date(o.date)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      const label = d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
      if (!monthly[key]) monthly[key] = { month: label, spent: 0, count: 0 }
      monthly[key].spent += o.total
      monthly[key].count += 1
    })
    return Object.entries(monthly)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-12)
      .map(([, v]) => v)
  }, [orders])

  // LTV projection
  const ltvProjection = useMemo(() => {
    if (!customer?.created_at || !customer.total_spent) return null
    const ageMs = Date.now() - new Date(customer.created_at).getTime()
    const ageDays = Math.max(1, ageMs / 86400000)
    const dailySpend = customer.total_spent / ageDays
    return {
      annual: dailySpend * 365,
      threeYear: dailySpend * 365 * 3,
      ageDays: Math.floor(ageDays),
    }
  }, [customer])

  // Pagination
  const totalPages = Math.max(1, Math.ceil(orders.length / ORDERS_PER_PAGE))
  const pagedOrders = useMemo(() => {
    const start = (page - 1) * ORDERS_PER_PAGE
    return orders.slice(start, start + ORDERS_PER_PAGE)
  }, [orders, page])

  // Reset page when orders change
  useEffect(() => { setPage(1) }, [orders.length])

  if (loading) {
    return (
      <div className="space-y-6 w-full">
        <div className="card h-48 bg-gray-50 animate-pulse rounded-2xl" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="card h-28 bg-gray-50 animate-pulse" />)}
        </div>
        <div className="card h-72 bg-gray-50 animate-pulse" />
      </div>
    )
  }

  if (error || !customer) {
    return (
      <div className="space-y-4 w-full">
        <button onClick={() => navigate('/customers')} className="btn-ghost flex items-center gap-2 text-xs">
          <ArrowLeft size={13} /> Back
        </button>
        <div className="card p-12 text-center">
          <AlertCircle size={36} className="text-red-400 mx-auto mb-3" />
          <p className="text-sm font-medium text-gray-900">{error || 'Customer not found'}</p>
        </div>
      </div>
    )
  }

  const meta = SEGMENT_META[customer.segment] || SEGMENT_META.regular
  const SegIcon = meta.icon
  const initials = ((customer.first_name?.[0] || customer.name?.[0] || '?') + (customer.last_name?.[0] || '')).toUpperCase()

  const recScore = recencyScore(customer.days_since_last_order)
  const freqScore = frequencyScore(customer.total_orders)
  const monScore = monetaryScore(customer.total_spent)
  const rfmTotal = recScore + freqScore + monScore

  // Next milestone copy
  let nextMilestone = null
  if (customer.segment === 'never_bought') {
    nextMilestone = { label: 'Convert with first purchase', icon: Sparkles, tone: 'text-green-600 bg-green-50' }
  } else if (customer.segment === 'new') {
    const more = Math.max(0, 5 - customer.total_orders)
    nextMilestone = { label: `${more} more order${more === 1 ? '' : 's'} to reach Loyal`, icon: Heart, tone: 'text-pink-600 bg-pink-50' }
  } else if (customer.segment === 'regular') {
    const more = Math.max(0, 5 - customer.total_orders)
    nextMilestone = more > 0
      ? { label: `${more} more order${more === 1 ? '' : 's'} to reach Loyal`, icon: Heart, tone: 'text-pink-600 bg-pink-50' }
      : { label: 'Re-engage to qualify for Loyal', icon: Activity, tone: 'text-pink-600 bg-pink-50' }
  } else if (customer.segment === 'loyal') {
    nextMilestone = { label: 'Top spenders reach VIP — keep them engaged', icon: Crown, tone: 'text-amber-600 bg-amber-50' }
  } else if (customer.segment === 'vip') {
    nextMilestone = { label: 'VIP — protect this relationship', icon: Award, tone: 'text-amber-600 bg-amber-50' }
  } else if (customer.segment === 'at_risk') {
    nextMilestone = { label: 'Win-back campaign needed', icon: Zap, tone: 'text-orange-600 bg-orange-50' }
  } else if (customer.segment === 'churned') {
    nextMilestone = { label: 'Long inactive — try a re-acquisition offer', icon: Target, tone: 'text-gray-600 bg-gray-100' }
  }

  return (
    <div className="space-y-6 w-full">
      {/* Back */}
      <button onClick={() => navigate('/customers')} className="btn-ghost flex items-center gap-2 text-xs">
        <ArrowLeft size={13} /> All Customers
      </button>

      {/* ─── HERO BANNER ────────────────────────────────────── */}
      <div className="relative card overflow-hidden">
        {/* Gradient accent stripe */}
        <div className={clsx('absolute inset-x-0 top-0 h-1 bg-gradient-to-r', meta.accent)} />

        <div className="p-5 sm:p-6">
          <div className="flex flex-col md:flex-row md:items-start gap-5">
            {/* Avatar */}
            <div className="relative shrink-0">
              <div className={clsx(
                'w-20 h-20 sm:w-24 sm:h-24 rounded-2xl flex items-center justify-center text-3xl font-bold text-white shadow-lg bg-gradient-to-br ring-4',
                meta.accent, meta.ring,
              )}>
                {initials}
              </div>
              <div className={clsx(
                'absolute -bottom-1 -right-1 w-7 h-7 rounded-full flex items-center justify-center shadow-md bg-white border-2',
                meta.border,
              )}>
                <SegIcon size={13} className={meta.color} />
              </div>
            </div>

            {/* Identity */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 truncate">{customer.name}</h1>
                <span className={clsx('inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-md', meta.bg, meta.color)}>
                  <SegIcon size={10} />
                  {meta.label}
                </span>
                {customer.accepts_marketing && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md bg-green-50 text-green-700 border border-green-100">
                    <CheckCircle2 size={10} />
                    Marketing opt-in
                  </span>
                )}
              </div>

              {/* Contact line */}
              <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3 text-xs text-gray-600">
                {customer.email && (
                  <a href={`mailto:${customer.email}`} className="flex items-center gap-1.5 hover:text-brand-600 transition-colors">
                    <Mail size={12} /> {customer.email}
                  </a>
                )}
                {customer.phone && (
                  <a href={`tel:${customer.phone}`} className="flex items-center gap-1.5 hover:text-brand-600 transition-colors">
                    <Phone size={12} /> {customer.phone}
                  </a>
                )}
                {customer.location && (
                  <span className="flex items-center gap-1.5">
                    <MapPin size={12} /> {customer.location}
                  </span>
                )}
                {customer.created_at && (
                  <span className="flex items-center gap-1.5">
                    <Calendar size={12} /> Joined {formatFullDate(customer.created_at)}
                  </span>
                )}
              </div>

              {/* Next milestone callout */}
              {nextMilestone && (
                <div className={clsx('inline-flex items-center gap-1.5 mt-4 px-3 py-1.5 rounded-lg text-xs font-semibold', nextMilestone.tone)}>
                  <nextMilestone.icon size={12} />
                  {nextMilestone.label}
                </div>
              )}
            </div>
          </div>

          {/* Tags row */}
          {customer.tags?.length > 0 && (
            <div className="mt-5 pt-4 border-t border-gray-100">
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mt-1 shrink-0">Tags</span>
                <div className="flex flex-wrap gap-1.5">
                  {customer.tags.slice(0, 12).map((t, i) => (
                    <span key={i} className="inline-flex items-center text-[11px] bg-gray-100 text-gray-700 px-2 py-0.5 rounded-md">
                      {t}
                    </span>
                  ))}
                  {customer.tags.length > 12 && (
                    <span className="text-[11px] text-gray-500 font-semibold px-1">
                      +{customer.tags.length - 12} more
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─── KPI CARDS ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard icon={TrendingUp} label="Lifetime Spend" value={`KES ${formatKES(customer.total_spent)}`}
                 sub={`Avg KES ${formatKES(customer.aov)} per order`}
                 accent="from-brand-400 to-brand-600" />
        <KpiCard icon={ShoppingBag} label="Total Orders" value={customer.total_orders || 0}
                 sub={customer.first_order_date ? `First ${formatFullDate(customer.first_order_date)}` : 'No orders yet'}
                 accent="from-blue-400 to-blue-600" />
        <KpiCard icon={Repeat} label="Average Order Value" value={`KES ${formatKES(customer.aov)}`}
                 sub={customer.total_orders > 0 ? `Across ${customer.total_orders} orders` : '—'}
                 accent="from-violet-400 to-violet-600" />
        <KpiCard icon={Clock} label="Last Order" value={customer.last_order_date ? formatDateAgo(customer.last_order_date) : 'Never'}
                 sub={customer.days_since_last_order != null ? `${customer.days_since_last_order} days ago` : 'Yet to convert'}
                 accent="from-amber-400 to-amber-600" />
      </div>

      {/* ─── RFM BREAKDOWN ──────────────────────────────────── */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <Target size={14} className="text-brand-500" /> RFM Score Breakdown
          </h2>
          <span className="text-xs text-gray-500">
            Total <span className="font-bold text-gray-900">{rfmTotal}</span><span className="text-gray-400">/15</span>
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <RfmPillar icon={Clock} label="Recency" score={recScore}
                     caption={customer.days_since_last_order != null
                       ? `Last purchase ${customer.days_since_last_order} days ago`
                       : 'No purchase history'}
                     scaleLabel="≤30d=5 · 31-60=4 · 61-90=3 · 91-180=2 · 180+=1" />
          <RfmPillar icon={Repeat} label="Frequency" score={freqScore}
                     caption={`${customer.total_orders || 0} lifetime order${customer.total_orders === 1 ? '' : 's'}`}
                     scaleLabel="10+=5 · 5-9=4 · 3-4=3 · 2=2 · 0-1=1" />
          <RfmPillar icon={TrendingUp} label="Monetary" score={monScore}
                     caption={`KES ${formatKES(customer.total_spent)} lifetime spend`}
                     scaleLabel="500k+=5 · 100k+=4 · 50k+=3 · 10k+=2 · <10k=1" />
        </div>
      </div>

      {/* ─── SPEND TREND + LTV PROJECTION ───────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Trend */}
        <div className="card p-5 lg:col-span-2">
          <h2 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
            <Activity size={14} className="text-brand-500" /> Spending Trend
          </h2>
          {trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={trend}>
                <defs>
                  <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#ff5900" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#ff5900" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                       tickFormatter={v => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  formatter={(value, name) => name === 'spent'
                    ? [`KES ${formatKES(value)}`, 'Spent']
                    : [value, name]}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                />
                <Area type="monotone" dataKey="spent" stroke="#ff5900" strokeWidth={2.5}
                      fill="url(#spendGrad)" dot={{ r: 3, fill: '#ff5900' }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-14">
              <Activity size={28} className="text-gray-300 mx-auto mb-2" />
              <p className="text-xs text-gray-400">No order history yet</p>
            </div>
          )}
        </div>

        {/* LTV projection */}
        <div className="card p-5 relative overflow-hidden">
          <div className="absolute -right-8 -top-8 w-28 h-28 rounded-full bg-gradient-to-br from-brand-200/40 to-brand-400/20 blur-xl" />
          <h2 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2 relative">
            <Award size={14} className="text-brand-500" /> Lifetime Value
          </h2>
          {ltvProjection ? (
            <div className="space-y-4 relative">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">To Date</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">KES {formatKES(customer.total_spent)}</p>
                <p className="text-xs text-gray-400 mt-0.5">over {ltvProjection.ageDays.toLocaleString()} days</p>
              </div>
              <div className="border-t border-gray-100 pt-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Projected Annual</p>
                <p className="text-xl font-bold text-brand-600 mt-1">KES {formatKES(ltvProjection.annual)}</p>
              </div>
              <div className="border-t border-gray-100 pt-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">3-Year Outlook</p>
                <p className="text-lg font-bold text-gray-700 mt-1">KES {formatKES(ltvProjection.threeYear)}</p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-400 text-center py-12 relative">
              Insufficient history to project value
            </p>
          )}
        </div>
      </div>

      {/* ─── ORDER HISTORY ──────────────────────────────────── */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <ShoppingBag size={14} className="text-brand-500" /> Order History
          </h2>
          {orders.length > 0 && (
            <span className="text-xs text-gray-500">
              <span className="font-bold text-gray-900">{formatKES(orders.length)}</span> total
            </span>
          )}
        </div>

        {orders.length === 0 ? (
          <div className="text-center py-12">
            <Package size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500 font-medium">No orders yet</p>
            <p className="text-xs text-gray-400 mt-1">
              {customer.total_orders > 0
                ? 'Shopify shows orders but local cache is empty — try syncing orders'
                : 'This customer has not placed any orders yet'}
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[720px]">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="text-left px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Order</th>
                    <th className="text-left px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Date</th>
                    <th className="text-left px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Items</th>
                    <th className="text-left px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Status</th>
                    <th className="text-right px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedOrders.map(o => {
                    const statusTone =
                      o.status === 'fulfilled' || o.status === 'shipped' ? 'bg-green-50 text-green-700' :
                      o.status === 'paid' || o.status === 'partially_paid' ? 'bg-blue-50 text-blue-700' :
                      o.status === 'pending' ? 'bg-amber-50 text-amber-700' :
                      o.status === 'refunded' || o.status === 'voided' ? 'bg-red-50 text-red-700' :
                      'bg-gray-100 text-gray-700'
                    return (
                      <tr key={o.id} className="border-b border-gray-100 hover:bg-gray-50/60 transition-colors">
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-1.5">
                            <Hash size={11} className="text-gray-400" />
                            <span className="text-sm font-semibold text-gray-900">{o.order_number}</span>
                          </div>
                        </td>
                        <td className="px-3 py-3 text-xs text-gray-600">{formatFullDate(o.date)}</td>
                        <td className="px-3 py-3">
                          <p className="text-xs text-gray-900 font-medium">{o.items} item{o.items === 1 ? '' : 's'}</p>
                          {o.products?.length > 0 && (
                            <p className="text-[11px] text-gray-500 truncate max-w-[260px]" title={o.products.join(', ')}>
                              {o.products.slice(0, 2).join(', ')}
                              {o.products.length > 2 && ` +${o.products.length - 2} more`}
                            </p>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <span className={clsx('inline-block text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded', statusTone)}>
                            {(o.status || 'unknown').replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-right text-sm font-bold text-gray-900">
                          {o.currency || 'KES'} {formatKES(o.total)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 flex-wrap gap-3">
                <p className="text-xs text-gray-500">
                  Showing {(page - 1) * ORDERS_PER_PAGE + 1}–{Math.min(page * ORDERS_PER_PAGE, orders.length)} of {formatKES(orders.length)}
                </p>
                <div className="flex gap-1 items-center">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40">
                    <ChevronLeft size={14} />
                  </button>

                  {(() => {
                    const delta = 1
                    const left = Math.max(2, page - delta)
                    const right = Math.min(totalPages - 1, page + delta)
                    const pages = [1]
                    if (left > 2) pages.push('...')
                    for (let i = left; i <= right; i++) pages.push(i)
                    if (right < totalPages - 1) pages.push('...')
                    if (totalPages > 1) pages.push(totalPages)

                    return pages.map((p, i) =>
                      p === '...' ? (
                        <span key={`el-${i}`} className="px-2 text-xs text-gray-400">…</span>
                      ) : (
                        <button key={p} onClick={() => setPage(p)}
                                className={clsx(
                                  'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                                  page === p ? 'bg-black text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                )}>
                          {p}
                        </button>
                      )
                    )
                  })()}

                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40">
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}