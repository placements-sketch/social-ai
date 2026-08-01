import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users, TrendingUp, ShoppingBag, Repeat, Search,
  Crown, Heart, AlertTriangle, UserMinus, Sparkles, ChevronRight, ChevronLeft,
  Download, RefreshCw, Loader2, AlertCircle, Package, UserPlus,
  Award, Activity, Target,
} from 'lucide-react'
import {
  ResponsiveContainer, Tooltip, CartesianGrid,
  AreaChart, Area, XAxis, YAxis, ComposedChart, Bar, Line, Legend,
} from 'recharts'
import clsx from 'clsx'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { formatDateAgo, formatTimeAgo } from '../utils/time'
import {
  listCustomers, getCustomersOverview, getCustomersSyncStatus, startCustomersSync,
} from '../api/customers'
import CustomerAIChat from './CustomerAIChat'
import CustomerTrends from './CustomerTrends'

const SEGMENT_META = {
  vip:          { label: 'VIP',          icon: Crown,         color: 'text-amber-600',  bg: 'bg-amber-50',   border: 'border-amber-200',  ring: 'ring-amber-400/30',  accent: 'from-amber-400 to-amber-600',  dot: 'bg-amber-500' },
  loyal:        { label: 'Loyal',        icon: Heart,         color: 'text-pink-600',   bg: 'bg-pink-50',    border: 'border-pink-200',   ring: 'ring-pink-400/30',   accent: 'from-pink-400 to-pink-600',    dot: 'bg-pink-500' },
  regular:      { label: 'Regular',      icon: Users,         color: 'text-blue-600',   bg: 'bg-blue-50',    border: 'border-blue-200',   ring: 'ring-blue-400/30',   accent: 'from-blue-400 to-blue-600',    dot: 'bg-blue-500' },
  new:          { label: 'New Convert',  icon: Sparkles,      color: 'text-green-600',  bg: 'bg-green-50',   border: 'border-green-200',  ring: 'ring-green-400/30',  accent: 'from-green-400 to-green-600',  dot: 'bg-green-500' },
  never_bought: { label: 'Never Bought', icon: UserPlus,      color: 'text-slate-600',  bg: 'bg-slate-50',   border: 'border-slate-200',  ring: 'ring-slate-400/30',  accent: 'from-slate-400 to-slate-500',  dot: 'bg-slate-400' },
  at_risk:      { label: 'At Risk',      icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50',  border: 'border-orange-200', ring: 'ring-orange-400/30', accent: 'from-orange-400 to-orange-600',dot: 'bg-orange-500' },
  churned:      { label: 'Churned',      icon: UserMinus,     color: 'text-gray-600',   bg: 'bg-gray-100',   border: 'border-gray-300',   ring: 'ring-gray-400/30',   accent: 'from-gray-400 to-gray-600',    dot: 'bg-gray-500' },
}

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

// ─── KPI card with gradient corner + animated count ─────────────
function KpiCard({ icon: Icon, label, value, sub, tone }) {
  const numeric = typeof value === 'number'
    ? value
    : parseFloat(String(value).replace(/[^0-9.-]/g, '')) || 0
  const animated = useCountAnimation(numeric, 1500, numeric % 1 !== 0)
  const formatted = typeof value === 'number'
    ? Math.round(animated).toLocaleString()
    : String(value).replace(/[\d,.]+/, (numeric < 100 ? animated.toFixed(0) : Math.round(animated).toLocaleString()))

  return (
    <div className="card p-4 group">
      {/* The old card carried a gradient blob bleeding off the corner and a
          second gradient behind the icon. Two decorative gradients per card,
          four cards, on a surface that is already doing the work — it read as
          busy and dated it more than anything else on the page. The icon keeps
          the colour; the card keeps the glass. */}
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest leading-relaxed">
          {label}
        </p>
        <span className={clsx(
          'w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-colors',
          tone || 'bg-gray-100 text-gray-500'
        )}>
          <Icon size={14} />
        </span>
      </div>
      <p className="text-2xl font-bold text-gray-900 mt-2 tabular-nums truncate">{formatted}</p>
      {sub && <p className="text-xs text-gray-400 mt-1 leading-snug">{sub}</p>}
    </div>
  )
}

function KpiSkeleton() {
  return (
    <div className="card p-4 animate-pulse">
      <div className="w-9 h-9 rounded-xl bg-gray-200 mb-3" />
      <div className="h-3 bg-gray-200 rounded w-2/3 mb-2" />
      <div className="h-6 bg-gray-200 rounded w-1/2 mb-1" />
      <div className="h-3 bg-gray-100 rounded w-3/4" />
    </div>
  )
}

function BlockSkeleton({ className = 'h-72' }) {
  return <div className={clsx('card bg-gray-50 animate-pulse rounded-xl', className)} />
}

// ─── Top spender/frequent card ─────────────────────────────────
function TopList({ title, icon: TitleIcon, customers, mode, navigate }) {
  if (customers.length === 0) {
    return (
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
          <TitleIcon size={14} className="text-brand-500" /> {title}
        </h2>
        <p className="text-xs text-gray-400 text-center py-8">No data yet</p>
      </div>
    )
  }
  return (
    <div className="card p-5">
      <h2 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
        <TitleIcon size={14} className="text-brand-500" /> {title}
      </h2>
      <div className="space-y-1.5">
        {customers.map((c, i) => {
          const meta = SEGMENT_META[c.segment] || SEGMENT_META.regular
          const SegIcon = meta.icon
          return (
            <button
              key={c.id}
              onClick={() => navigate(`/customers/${c.id}`)}
              className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 transition text-left"
            >
              <span className="text-xs font-bold text-gray-400 w-5 text-center shrink-0">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 truncate">{c.name}</p>
                <p className="text-xs text-gray-500 truncate">{c.email || c.phone || c.location}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-bold text-gray-900">
                  {mode === 'spent' ? `KES ${formatKES(c.total_spent)}` : `${formatKES(c.total_orders)} orders`}
                </p>
                <span className={clsx('inline-flex items-center gap-0.5 text-[10px] font-bold uppercase tracking-wide', meta.color)}>
                  <SegIcon size={9} />
                  {meta.label}
                </span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function Customers() {
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [segmentFilter, setSegmentFilter] = useState('all')
  const [sortBy, setSortBy] = useState('spent_desc')
  const [granularity, setGranularity] = useState('month')
  const [page, setPage] = useState(1)
  const PER_PAGE = 25

  const [overview, setOverview] = useState(null)
  const [customers, setCustomers] = useState([])
  const [total, setTotal] = useState(0)
  const [syncStatus, setSyncStatus] = useState(null)

  const [loadingOverview, setLoadingOverview] = useState(true)
  const [loadingList, setLoadingList] = useState(true)
  const [error, setError] = useState(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => { setPage(1) }, [debouncedSearch, segmentFilter, sortBy])

  const loadOverview = useCallback(async () => {
    setLoadingOverview(true)
    try {
      const data = await getCustomersOverview({ granularity })
      setOverview(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingOverview(false)
    }
  }, [granularity])

  const loadSyncStatus = useCallback(async () => {
    try {
      const data = await getCustomersSyncStatus()
      setSyncStatus(data)
    } catch { /* non-fatal */ }
  }, [])

  const loadCustomers = useCallback(async () => {
    setLoadingList(true)
    try {
      const data = await listCustomers({
        page, per_page: PER_PAGE,
        search: debouncedSearch || null,
        segment: segmentFilter, sort_by: sortBy,
      })
      setCustomers(data.customers || [])
      setTotal(data.total || 0)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingList(false)
    }
  }, [page, debouncedSearch, segmentFilter, sortBy])

  useEffect(() => { loadOverview() }, [loadOverview])
  useEffect(() => { loadSyncStatus() }, [loadSyncStatus])
  useEffect(() => { loadCustomers() }, [loadCustomers])

  const handleSync = async () => {
    setSyncing(true)
    setError(null)
    try {
      await startCustomersSync()
      const startedAt = Date.now()
      while (Date.now() - startedAt < 30 * 60 * 1000) {
        await new Promise(r => setTimeout(r, 3000))
        const status = await getCustomersSyncStatus()
        setSyncStatus(status)
        const job = status?.current_job
        if (job?.status === 'success') break
        if (job?.status === 'failed') {
          throw new Error(job.error || 'Sync failed')
        }
      }
      await Promise.all([loadOverview(), loadCustomers()])
    } catch (err) {
      setError(err.message)
    } finally {
      setSyncing(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))
  const lastSyncedIso = syncStatus?.last_synced_at
  const isStale = syncStatus?.stale === true
  const currentJob = syncStatus?.current_job
  const isJobRunning = currentJob?.status === 'running' || currentJob?.status === 'pending'

  const exportToCSV = () => {
    const headers = ['Name', 'Email', 'Phone', 'Location', 'Segment', 'Total Spent', 'Total Orders', 'Last Order']
    const rows = customers.map(c => [
      c.name, c.email || '', c.phone || '', c.location || '',
      SEGMENT_META[c.segment]?.label || c.segment,
      c.total_spent, c.total_orders, c.last_order_date || 'Never',
    ])
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `customers-export-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  // ─── Empty state ────────────────────────────────────────────
  if (!loadingOverview && overview?.kpis?.total_customers === 0) {
    return (
      <div className="space-y-6 w-full">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Customer Profiling</h1>
          <p className="text-sm text-gray-500 mt-0.5">Shopify customer data, order history, and spend analytics</p>
        </div>
        <div className="card p-12 flex flex-col items-center text-center relative overflow-hidden">
          <div className="absolute -right-12 -top-12 w-48 h-48 rounded-full bg-gradient-to-br from-brand-100 to-brand-300/40 blur-2xl" />
          <div className="relative">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center mx-auto mb-4 shadow-lg">
              <Users size={28} className="text-white" />
            </div>
            <h2 className="text-lg font-bold text-gray-900">No customers synced yet</h2>
            <p className="text-sm text-gray-500 mt-2 max-w-md">
              Pull your Shopify customer base into the cache to enable profiling, segments, and order history. This may take 5–10 minutes for a large catalog.
            </p>
            <button
              onClick={handleSync}
              disabled={syncing || isJobRunning}
              className="btn-primary mt-4 flex items-center gap-2 text-sm"
            >
              {syncing || isJobRunning
                ? <><Loader2 size={14} className="animate-spin" /> {currentJob?.progress || 'Syncing...'}</>
                : <><RefreshCw size={14} /> Start First Sync</>
              }
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full">
      {/* ─── HEADER ─────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Customer Profiling</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Shopify customer data, order history, and spend analytics
            {lastSyncedIso && (
              <> · <span className={isStale ? 'text-amber-600 font-medium' : ''}>
                Synced {formatTimeAgo(lastSyncedIso)}
              </span></>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportToCSV} className="btn-ghost flex items-center gap-2 text-xs">
            <Download size={13} /> CSV
          </button>
          <button
            onClick={handleSync}
            disabled={syncing || isJobRunning}
            className="btn-primary flex items-center gap-2 text-xs"
          >
            {syncing || isJobRunning
              ? <><Loader2 size={13} className="animate-spin" />{currentJob?.progress || 'Syncing...'}</>
              : <><RefreshCw size={13} /> Sync Now</>
            }
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex gap-3">
          <AlertCircle size={18} className="text-red-600 shrink-0 mt-0.5" />
          <p className="text-sm font-medium text-red-900">{error}</p>
        </div>
      )}

      {isStale && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex gap-3 items-center">
          <AlertCircle size={16} className="text-amber-600 shrink-0" />
          <p className="text-xs text-amber-900 font-medium">
            Customer data is stale (last synced {formatTimeAgo(lastSyncedIso)}). Click "Sync Now" to refresh.
          </p>
        </div>
      )}

      {/* ─── KPI STRIP ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {overview ? (
          <>
            {/* Four cards, four separate facts.
                Two of the old four stated the same one: "Retention Rate 46.5%"
                sat beside "Repeat Buyers 16,996 of 161,639 total". 16,996 IS
                the numerator of that 46.5% — but its own card divided it by
                every record instead of by buyers, implying 10.5%. Two adjacent
                cards, two different rates, one underlying fact.

                "Total Customers" has the same trouble: of 161,639 records,
                125,055 have never ordered. Leading with the bigger number
                makes every rate on the page look worse than it is, so the
                headline is buyers and the record count is the context. */}
            <KpiCard
              icon={ShoppingBag}
              label="Customers who bought"
              value={overview.kpis.buyers ?? 0}
              sub={`${formatKES(overview.kpis.total_customers)} records in Shopify · ${formatKES(overview.kpis.never_bought ?? 0)} never ordered`}
              tone="bg-brand-50 text-brand-700"
            />
            <KpiCard
              icon={TrendingUp}
              label="Revenue (ex. VAT)"
              value={`KES ${formatKES(overview.kpis.total_revenue)}`}
              sub={`KES ${formatKES(overview.kpis.avg_aov)} average order · all time`}
              tone="bg-blue-50 text-blue-600"
            />
            <KpiCard
              icon={Repeat}
              label="Came back for more"
              value={`${Math.round((overview.kpis.retention_rate || 0) * 100)}%`}
              sub={`${formatKES(overview.kpis.repeat_customers)} of ${formatKES(overview.kpis.buyers ?? 0)} buyers ordered twice or more`}
              tone="bg-amber-50 text-amber-600"
            />
            <KpiCard
              icon={Users}
              label="New in last 30 days"
              value={overview.kpis.new_this_month}
              sub="Shopify accounts created, whether or not they ordered"
              tone="bg-violet-50 text-violet-600"
            />
          </>
        ) : (
          [...Array(4)].map((_, i) => <KpiSkeleton key={i} />)
        )}
      </div>

      {/* ─── SEGMENTS + AOV TREND ───────────────────────────── */}
      {overview ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Segments column */}
          <div className="card p-5 lg:col-span-1">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                <Target size={14} className="text-brand-500" /> Segments
              </h2>
              <span className="text-[10px] text-gray-400 font-bold uppercase tracking-widest">RFM</span>
            </div>
            <div className="space-y-2">
              {Object.entries(SEGMENT_META).map(([key, meta]) => {
                const count = overview.segment_counts?.[key] || 0
                const total = overview.kpis.total_customers || 1
                const pct = (count / total) * 100
                const Icon = meta.icon
                const isActive = segmentFilter === key
                return (
                  <button
                    key={key}
                    onClick={() => setSegmentFilter(isActive ? 'all' : key)}
                    className={clsx(
                      'w-full relative overflow-hidden p-2.5 rounded-lg border transition-all text-left text-xs group',
                      isActive
                        ? `${meta.bg} ${meta.border} ring-1 ${meta.ring}`
                        : 'bg-white border-gray-100 hover:border-gray-300'
                    )}
                  >
                    {/* Subtle bar showing percentage */}
                    <div
                      className={clsx('absolute inset-y-0 left-0 opacity-10 bg-gradient-to-r', meta.accent)}
                      style={{ width: `${pct}%` }}
                    />
                    <div className="relative flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={clsx('w-7 h-7 rounded-md flex items-center justify-center bg-gradient-to-br', meta.accent)}>
                          <Icon size={13} className="text-white" />
                        </div>
                        <div>
                          <span className="font-semibold text-gray-800 block">{meta.label}</span>
                          <span className="text-[10px] text-gray-400">{pct.toFixed(1)}%</span>
                        </div>
                      </div>
                      <span className="font-bold text-gray-900 text-sm">{formatKES(count)}</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Orders & revenue over time */}
          <div className="card p-5 lg:col-span-2 flex flex-col">
            <div className="shrink-0 mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
              <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                <Activity size={14} className="text-brand-500" /> Orders & revenue over time
              </h2>
              {overview.aov_by_month?.length > 0 && (() => {
                const rows = overview.aov_by_month
                const totalOrders  = rows.reduce((s, r) => s + (r.orders || 0), 0)
                const totalRevenue = rows.reduce((s, r) => s + (r.revenue || 0), 0)
                const aov = totalOrders ? Math.round(totalRevenue / totalOrders) : 0
                return (
                  <p className="text-xs text-gray-400 mt-0.5">
                    {formatKES(totalOrders)} orders · KES {formatKES(totalRevenue)} · AOV KES {formatKES(aov)} · All time
                  </p>
                )
              })()}
              </div>
              <div className="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5 shrink-0">
                {['day', 'week', 'month'].map(g => (
                  <button
                    key={g}
                    onClick={() => setGranularity(g)}
                    className={clsx(
                      'px-2.5 py-1 rounded-md text-[11px] font-semibold capitalize transition-colors',
                      granularity === g
                        ? 'bg-white text-gray-900 shadow-sm'
                        : 'text-gray-500 hover:text-gray-800'
                    )}
                  >
                    {g === 'day' ? 'Daily' : g === 'week' ? 'Weekly' : 'Monthly'}
                  </button>
                ))}
              </div>
            </div>
            {overview.aov_by_month?.length > 0 ? (
              <div className="flex-1 min-h-[240px] -mb-2">
                <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={overview.aov_by_month} margin={{ top: 8, right: 4, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                         interval="preserveStartEnd" minTickGap={28} />
                  <YAxis yAxisId="rev" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                         tickFormatter={v => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(0)}M` : `${(v / 1000).toFixed(0)}K`} />
                  <YAxis yAxisId="ord" orientation="right" tick={{ fontSize: 11, fill: '#9ca3af' }}
                         axisLine={false} tickLine={false} />
                  <Tooltip
                    formatter={(value, name) => name === 'Revenue (KES)'
                      ? [`KES ${formatKES(value)}`, name]
                      : [formatKES(value), name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
                  <Bar yAxisId="rev" dataKey="revenue" name="Revenue (KES)" fill="#c7ea46"
                       radius={[3, 3, 0, 0]} maxBarSize={16} />
                  <Line yAxisId="ord" type="monotone" dataKey="orders" name="Orders" stroke="#111827"
                        strokeWidth={2} dot={{ r: 2 }} />
                </ComposedChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="text-center py-14">
                <Activity size={28} className="text-gray-300 mx-auto mb-2" />
                <p className="text-xs text-gray-400">No order data yet — run an order sync</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <BlockSkeleton className="lg:col-span-1 h-96" />
          <BlockSkeleton className="lg:col-span-2 h-96" />
        </div>
      )}

      <CustomerTrends />

      {/* ─── TOP SPENDERS + FREQUENT ────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {overview ? (
          <>
            <TopList title="Top Spenders" icon={Award} customers={overview.top_spenders || []} mode="spent" navigate={navigate} />
            <TopList title="Most Frequent Buyers" icon={Repeat} customers={overview.top_frequent || []} mode="orders" navigate={navigate} />
          </>
        ) : (
          <>
            <BlockSkeleton className="h-72" />
            <BlockSkeleton className="h-72" />
          </>
        )}
      </div>

      <CustomerAIChat />

      {/* ─── CUSTOMER TABLE ─────────────────────────────────── */}
      <div className="card p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <Users size={14} className="text-brand-500" />
            All Customers <span className="text-gray-400 font-normal">({formatKES(total)} total)</span>
          </h2>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-2.5 text-gray-400" />
              <input
                type="text"
                placeholder="Search name, email, phone..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="input text-xs pl-9 w-full md:w-64"
              />
            </div>
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value)}
              className="input text-xs"
            >
              <option value="spent_desc">Highest Spend</option>
              <option value="orders_desc">Most Orders</option>
              <option value="recent">Most Recent</option>
              <option value="name">Name (A–Z)</option>
            </select>
            {segmentFilter !== 'all' && (
              <button
                onClick={() => setSegmentFilter('all')}
                className={clsx(
                  'text-xs font-semibold px-2 py-1 rounded-md flex items-center gap-1',
                  SEGMENT_META[segmentFilter]?.bg,
                  SEGMENT_META[segmentFilter]?.color,
                )}
              >
                {SEGMENT_META[segmentFilter]?.label} ×
              </button>
            )}
          </div>
        </div>

        {customers.length === 0 && !loadingList ? (
          <div className="text-center py-12">
            <Package size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500 font-medium">No customers match these filters</p>
          </div>
        ) : (
          <div className="relative">
            {loadingList && (
              <div className="absolute inset-0 bg-white/60 flex items-center justify-center z-10 rounded-lg backdrop-blur-sm">
                <Loader2 size={18} className="animate-spin text-gray-400" />
              </div>
            )}
            <div className="overflow-x-auto hidden md:block">
              <table className="w-full text-sm min-w-[700px]">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="text-left px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Customer</th>
                    <th className="text-right px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">RFM</th>
                    <th className="text-left px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Segment</th>
                    <th className="text-right px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Spent</th>
                    <th className="text-right px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Orders</th>
                    <th className="text-right px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">AOV</th>
                    <th className="text-right px-3 py-2.5 text-[10px] font-bold text-gray-700 uppercase tracking-widest">Last Order</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.map(c => {
                    const meta = SEGMENT_META[c.segment] || SEGMENT_META.regular
                    const SegIcon = meta.icon
                    return (
                      <tr
                        key={c.id}
                        onClick={() => navigate(`/customers/${c.id}`)}
                        className="border-b border-gray-100 hover:bg-gray-50/60 cursor-pointer transition-colors"
                      >
                        <td className="px-3 py-3">
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-gray-900 truncate">{c.name}</p>
                            <p className="text-xs text-gray-500 truncate">{c.email || c.phone || '—'}</p>
                          </div>
                        </td>
                        <td className="px-3 py-3 text-right">
                          {c.rfm_score
                            ? <span className="inline-block px-2 py-0.5 rounded-md bg-gray-100 text-gray-700 text-xs font-bold tabular-nums">{c.rfm_score}</span>
                            : <span className="text-xs text-gray-300">—</span>}
                        </td>
                        <td className="px-3 py-3">
                          <span className={clsx('inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md', meta.bg, meta.color)}>
                            <SegIcon size={10} />
                            {meta.label}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-right text-sm font-bold text-gray-900">KES {formatKES(c.total_spent)}</td>
                        <td className="px-3 py-3 text-right text-sm text-gray-700">{formatKES(c.total_orders)}</td>
                        <td className="px-3 py-3 text-right text-sm text-gray-700">KES {formatKES(c.aov)}</td>
                        <td className="px-3 py-3 text-right text-xs text-gray-500">{formatDateAgo(c.last_order_date)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile: stacked cards — same data + tap target as the table rows */}
            <div className="md:hidden space-y-2.5">
              {customers.map(c => {
                const meta = SEGMENT_META[c.segment] || SEGMENT_META.regular
                const SegIcon = meta.icon
                const initial = (c.name || '?').charAt(0).toUpperCase()
                return (
                  <div
                    key={c.id}
                    onClick={() => navigate(`/customers/${c.id}`)}
                    className="bg-white border border-gray-200 rounded-2xl p-3.5 cursor-pointer hover:border-gray-300 active:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2 mb-3">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center text-sm font-semibold shrink-0">
                          {initial}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900 truncate">{c.name}</p>
                          <p className="text-xs text-gray-500 truncate">{c.email || c.phone || '—'}</p>
                        </div>
                      </div>
                      <span className={clsx('inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-md shrink-0', meta.bg, meta.color)}>
                        <SegIcon size={10} />
                        {meta.label}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 border-t border-gray-100 pt-3">
                      <div>
                        <p className="text-[9px] text-gray-400 uppercase tracking-wide">Spent</p>
                        <p className="text-sm font-bold text-gray-900 truncate">KES {formatKES(c.total_spent)}</p>
                      </div>
                      <div>
                        <p className="text-[9px] text-gray-400 uppercase tracking-wide">Orders</p>
                        <p className="text-sm font-bold text-gray-900">{formatKES(c.total_orders)}</p>
                      </div>
                      <div>
                        <p className="text-[9px] text-gray-400 uppercase tracking-wide">AOV</p>
                        <p className="text-sm font-bold text-gray-900 truncate">KES {formatKES(c.aov)}</p>
                      </div>
                      <div>
                        <p className="text-[9px] text-gray-400 uppercase tracking-wide">Last order</p>
                        <p className="text-sm font-bold text-gray-900">{c.days_since_last_order != null ? `${c.days_since_last_order}d ago` : '—'}</p>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 flex-wrap gap-3">
            <p className="text-xs text-gray-500">
              Showing {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, total)} of {formatKES(total)}
            </p>
            <div className="flex gap-1 items-center">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="btn-ghost px-2 py-1 text-xs disabled:opacity-40"
              >
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
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={clsx(
                        'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                        page === p
                          ? 'bg-black text-white'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      )}
                    >
                      {p}
                    </button>
                  )
                )
              })()}

              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="btn-ghost px-2 py-1 text-xs disabled:opacity-40"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}