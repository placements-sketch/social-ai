import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users, TrendingUp, ShoppingBag, Repeat, Search,
  Crown, Heart, AlertTriangle, UserMinus, Sparkles, ChevronRight, ChevronLeft,
  Download, RefreshCw, Loader2, AlertCircle, Package,
} from 'lucide-react'
import {
  ResponsiveContainer, Tooltip, CartesianGrid,
  LineChart, Line, XAxis, YAxis,
} from 'recharts'
import clsx from 'clsx'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { formatDateAgo, formatTimeAgo } from '../utils/time'
import {
  listCustomers, getCustomersOverview, getCustomersSyncStatus, startCustomersSync,
} from '../api/customers'

const SEGMENT_META = {
  vip:     { label: 'VIP',     icon: Crown,         color: 'text-amber-600',  bg: 'bg-amber-50',  border: 'border-amber-200',  dot: 'bg-amber-500' },
  loyal:   { label: 'Loyal',   icon: Heart,         color: 'text-pink-600',   bg: 'bg-pink-50',   border: 'border-pink-200',   dot: 'bg-pink-500' },
  regular: { label: 'Regular', icon: Users,         color: 'text-blue-600',   bg: 'bg-blue-50',   border: 'border-blue-200',   dot: 'bg-blue-500' },
  new:     { label: 'New',     icon: Sparkles,      color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-200',  dot: 'bg-green-500' },
  at_risk: { label: 'At Risk', icon: AlertTriangle, color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200', dot: 'bg-orange-500' },
  churned: { label: 'Churned', icon: UserMinus,     color: 'text-gray-600',   bg: 'bg-gray-100',  border: 'border-gray-300',   dot: 'bg-gray-500' },
}

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

// KPI card with animated value
function KpiCard({ icon: Icon, label, value, sub, color, bg }) {
  const numeric = typeof value === 'number'
    ? value
    : parseFloat(String(value).replace(/[^0-9.-]/g, '')) || 0
  const animated = useCountAnimation(numeric, 1500, numeric % 1 !== 0)
  const formatted = typeof value === 'number'
    ? Math.round(animated).toLocaleString()
    : String(value).replace(/[\d,.]+/, (numeric < 100 ? animated.toFixed(0) : Math.round(animated).toLocaleString()))

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-gray-500 font-semibold uppercase tracking-wide truncate">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 truncate">{formatted}</p>
          {sub && <p className="text-xs text-gray-400 mt-1 truncate">{sub}</p>}
        </div>
        <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center shrink-0', bg)}>
          <Icon size={16} className={color} />
        </div>
      </div>
    </div>
  )
}

// Skeleton for KPI card while overview is loading
function KpiSkeleton() {
  return (
    <div className="card p-4 animate-pulse">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 space-y-2">
          <div className="h-3 bg-gray-200 rounded w-2/3" />
          <div className="h-6 bg-gray-200 rounded w-1/2" />
          <div className="h-3 bg-gray-200 rounded w-3/4" />
        </div>
        <div className="w-9 h-9 rounded-lg bg-gray-200" />
      </div>
    </div>
  )
}

// Generic block-shape skeleton
function BlockSkeleton({ className = 'h-72' }) {
  return <div className={clsx('card bg-gray-50 animate-pulse rounded-xl', className)} />
}

// Top spender/frequent list — used twice
function TopList({ title, customers, mode, navigate }) {
  if (customers.length === 0) {
    return (
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4">{title}</h2>
        <p className="text-xs text-gray-400 text-center py-8">No data yet</p>
      </div>
    )
  }
  return (
    <div className="card p-5">
      <h2 className="text-sm font-bold text-gray-900 mb-4">{title}</h2>
      <div className="space-y-2">
        {customers.map((c, i) => {
          const meta = SEGMENT_META[c.segment] || SEGMENT_META.regular
          return (
            <button
              key={c.id}
              onClick={() => navigate(`/customers/${c.id}`)}
              className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 transition text-left"
            >
              <span className="text-xs font-bold text-gray-400 w-5">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 truncate">{c.name}</p>
                <p className="text-xs text-gray-500 truncate">{c.email || c.phone}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-sm font-bold text-gray-900">
                  {mode === 'spent' ? `KES ${formatKES(c.total_spent)}` : `${formatKES(c.total_orders)} orders`}
                </p>
                <span className={clsx('text-[10px] font-semibold uppercase', meta.color)}>{meta.label}</span>
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

  // Filters / pagination state
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [segmentFilter, setSegmentFilter] = useState('all')
  const [sortBy, setSortBy] = useState('spent_desc')
  const [page, setPage] = useState(1)
  const PER_PAGE = 25

  // Data
  const [overview, setOverview] = useState(null)
  const [customers, setCustomers] = useState([])
  const [total, setTotal] = useState(0)
  const [syncStatus, setSyncStatus] = useState(null)

  const [loadingOverview, setLoadingOverview] = useState(true)
  const [loadingList, setLoadingList] = useState(true)
  const [error, setError] = useState(null)
  const [syncing, setSyncing] = useState(false)

  // Debounce search input → 350ms before triggering API call
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  // Reset page when filters change
  useEffect(() => { setPage(1) }, [debouncedSearch, segmentFilter, sortBy])

  // Load overview once
  const loadOverview = useCallback(async () => {
    setLoadingOverview(true)
    try {
      const data = await getCustomersOverview()
      setOverview(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingOverview(false)
    }
  }, [])

  // Load sync status once + after sync
  const loadSyncStatus = useCallback(async () => {
    try {
      const data = await getCustomersSyncStatus()
      setSyncStatus(data)
    } catch {
      // non-fatal
    }
  }, [])

  // Load customer list whenever filters/page change
  const loadCustomers = useCallback(async () => {
    setLoadingList(true)
    try {
      const data = await listCustomers({
        page,
        per_page: PER_PAGE,
        search: debouncedSearch || null,
        segment: segmentFilter,
        sort_by: sortBy,
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

  // Sync trigger — poll status until done
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
      c.name,
      c.email || '',
      c.phone || '',
      c.location || '',
      SEGMENT_META[c.segment]?.label || c.segment,
      c.total_spent,
      c.total_orders,
      c.last_order_date || 'Never',
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

  // Empty / first-time state — only show after overview confirms 0 customers
  if (!loadingOverview && overview?.kpis?.total_customers === 0) {
    return (
      <div className="space-y-6 w-full">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Customer Profiling</h1>
          <p className="text-sm text-gray-500 mt-0.5">Shopify customer data, order history, and spend analytics</p>
        </div>
        <div className="card p-12 flex flex-col items-center text-center">
          <Users size={48} className="text-gray-300 mb-4" />
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
    )
  }

  return (
    <div className="space-y-6 w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Customer Profiling</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Shopify customer data, order history, and spend analytics
            {lastSyncedIso && (
              <> · <span className={isStale ? 'text-amber-600 font-medium' : ''}>Synced {formatTimeAgo(lastSyncedIso)}</span></>
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

      {/* KPI strip — skeleton while overview loads */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {overview ? (
          <>
            <KpiCard
              icon={Users}
              label="Total Customers"
              value={overview.kpis.total_customers}
              sub={`${formatKES(overview.kpis.new_this_month)} new this month`}
              color="text-blue-500" bg="bg-blue-50"
            />
            <KpiCard
              icon={TrendingUp}
              label="Total Revenue"
              value={`KES ${formatKES(overview.kpis.total_revenue)}`}
              sub={`KES ${formatKES(overview.kpis.avg_aov)} avg order`}
              color="text-brand-500" bg="bg-brand-50"
            />
            <KpiCard
              icon={Repeat}
              label="Retention Rate"
              value={`${Math.round((overview.kpis.retention_rate || 0) * 100)}%`}
              sub={`${formatKES(overview.kpis.repeat_customers)} repeat buyers`}
              color="text-amber-500" bg="bg-amber-50"
            />
            <KpiCard
              icon={ShoppingBag}
              label="Repeat Buyers"
              value={overview.kpis.repeat_customers}
              sub={`of ${formatKES(overview.kpis.total_customers)} total`}
              color="text-orange-500" bg="bg-orange-50"
            />
          </>
        ) : (
          [...Array(4)].map((_, i) => <KpiSkeleton key={i} />)
        )}
      </div>

      {/* Segments + AOV trend */}
      {overview ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Segments */}
          <div className="card p-5 lg:col-span-1">
            <div className="flex items-baseline justify-between mb-4">
              <h2 className="text-sm font-bold text-gray-900">Segments</h2>
              <span className="text-xs text-gray-400">RFM-based</span>
            </div>
            <div className="space-y-2">
              {Object.entries(SEGMENT_META).map(([key, meta]) => {
                const count = overview.segment_counts?.[key] || 0
                const Icon = meta.icon
                return (
                  <button
                    key={key}
                    onClick={() => setSegmentFilter(segmentFilter === key ? 'all' : key)}
                    className={clsx(
                      'w-full flex items-center justify-between p-2.5 rounded-lg border transition-all text-left text-xs',
                      segmentFilter === key
                        ? `${meta.bg} ${meta.border} ring-2 ring-offset-1 ring-${meta.dot.replace('bg-', '')}`
                        : 'bg-white border-gray-100 hover:border-gray-300'
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <div className={clsx('w-7 h-7 rounded-md flex items-center justify-center', meta.bg)}>
                        <Icon size={13} className={meta.color} />
                      </div>
                      <span className="font-semibold text-gray-800">{meta.label}</span>
                    </div>
                    <span className="font-bold text-gray-900">{formatKES(count)}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* AOV by month */}
          <div className="card p-5 lg:col-span-2">
            <h2 className="text-sm font-bold text-gray-900 mb-4">AOV by Month</h2>
            {overview.aov_by_month?.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={overview.aov_by_month}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false}
                         tickFormatter={v => `${(v / 1000).toFixed(1)}k`} />
                  <Tooltip
                    formatter={(value, name) => name === 'aov' ? [`KES ${formatKES(value)}`, 'AOV'] : [value, name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  />
                  <Line type="monotone" dataKey="aov" stroke="#ff5900" strokeWidth={2} dot={{ r: 4, fill: '#ff5900' }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-gray-400 text-center py-12">No order data yet — run an order sync</p>
            )}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <BlockSkeleton className="lg:col-span-1 h-80" />
          <BlockSkeleton className="lg:col-span-2 h-80" />
        </div>
      )}

      {/* Top spenders + Top frequent */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {overview ? (
          <>
            <TopList title="Top Spenders" customers={overview.top_spenders || []} mode="spent" navigate={navigate} />
            <TopList title="Most Frequent Buyers" customers={overview.top_frequent || []} mode="orders" navigate={navigate} />
          </>
        ) : (
          <>
            <BlockSkeleton className="h-72" />
            <BlockSkeleton className="h-72" />
          </>
        )}
      </div>

      {/* Customer table */}
      <div className="card p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-bold text-gray-900">
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
                className="text-xs font-medium px-2 py-1 rounded-md bg-gray-100 text-gray-700 hover:bg-gray-200"
              >
                Clear: {SEGMENT_META[segmentFilter]?.label} ×
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
              <div className="absolute inset-0 bg-white/60 flex items-center justify-center z-10 rounded-lg">
                <Loader2 size={18} className="animate-spin text-gray-400" />
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[700px]">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="text-left px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Customer</th>
                    <th className="text-left px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Segment</th>
                    <th className="text-right px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Spent</th>
                    <th className="text-right px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Orders</th>
                    <th className="text-right px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">AOV</th>
                    <th className="text-right px-3 py-2.5 text-xs font-bold text-gray-700 uppercase tracking-wider">Last Order</th>
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
                        className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors"
                      >
                        <td className="px-3 py-3">
                          <div className="min-w-0">
                            <p className="text-sm font-semibold text-gray-900 truncate">{c.name}</p>
                            <p className="text-xs text-gray-500 truncate">{c.email || c.phone || '—'}</p>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md', meta.bg, meta.color)}>
                            <SegIcon size={11} />
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
                    <span key={`ellipsis-${i}`} className="px-2 text-xs text-gray-400">…</span>
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