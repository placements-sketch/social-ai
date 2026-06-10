import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users, TrendingUp, ShoppingBag, Repeat, Search,
  ArrowUpRight, Crown, Heart, AlertTriangle, UserMinus, Sparkles, ChevronRight, ChevronLeft,
  Download, FileText, Sheet, File,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, LineChart, Line,
} from 'recharts'
import clsx from 'clsx'
import { MOCK_CUSTOMERS, SEGMENT_META, buildOverview } from '../data/mockCustomers'

const SEGMENT_ICONS = {
  vip:     Crown,
  loyal:   Heart,
  regular: Users,
  new:     Sparkles,
  at_risk: AlertTriangle,
  churned: UserMinus,
}

const CHART_COLORS = ['#ff5900', '#10b981', '#3b82f6', '#f59e0b', '#a855f7', '#ec4899']

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n)
}

function timeAgo(iso) {
  if (!iso) return 'Never'
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

export default function Customers() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [segmentFilter, setSegmentFilter] = useState('all')
  const [sortBy, setSortBy] = useState('spent_desc')
  const [currentPage, setCurrentPage] = useState(1)
  const ITEMS_PER_PAGE = 25

  const customers = MOCK_CUSTOMERS
  const overview = useMemo(() => buildOverview(customers), [customers])

  const filtered = useMemo(() => {
    let result = customers
    if (segmentFilter !== 'all') {
      result = result.filter(c => c.segment === segmentFilter)
    }
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(c =>
        c.name.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q) ||
        c.phone.includes(q)
      )
    }
    result = [...result].sort((a, b) => {
      switch (sortBy) {
        case 'spent_desc':  return b.total_spent - a.total_spent
        case 'orders_desc': return b.total_orders - a.total_orders
        case 'recent':      return new Date(b.last_order_date || 0) - new Date(a.last_order_date || 0)
        case 'name':        return a.name.localeCompare(b.name)
        default: return 0
      }
    })
    return result
  }, [customers, search, segmentFilter, sortBy])

  const totalPages = Math.ceil(filtered.length / ITEMS_PER_PAGE)
  const paginatedCustomers = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE
    return filtered.slice(start, start + ITEMS_PER_PAGE)
  }, [filtered, currentPage])

  // Export functions
  const exportToCSV = () => {
    const headers = ['Name', 'Email', 'Phone', 'Location', 'Segment', 'Total Spent', 'Total Orders', 'Last Order']
    const rows = filtered.map(c => [
      c.name,
      c.email,
      c.phone,
      c.location,
      SEGMENT_META[c.segment].label,
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

  const exportToPDF = async () => {
    // Dynamic import to avoid bundle size issues
    const { jsPDF } = await import('jspdf')
    const { autoTable } = await import('jspdf-autotable')
    
    const doc = new jsPDF()
    const headers = ['Name', 'Email', 'Phone', 'Segment', 'Total Spent', 'Orders', 'Last Order']
    const rows = filtered.map(c => [
      c.name,
      c.email,
      c.phone,
      SEGMENT_META[c.segment].label,
      `KES ${formatKES(c.total_spent)}`,
      c.total_orders,
      timeAgo(c.last_order_date),
    ])
    
    autoTable(doc, {
      head: [headers],
      body: rows,
      startY: 20,
      styles: { fontSize: 9, cellPadding: 3 },
      headStyles: { fillColor: [0, 0, 0], textColor: [255, 255, 255] },
    })
    
    doc.save(`customers-export-${new Date().toISOString().split('T')[0]}.pdf`)
  }

  const exportToGoogleSheets = () => {
    // This would require Google Sheets API integration
    // For now, show a message
    alert('Google Sheets export requires additional setup. Download as CSV and import manually.')
  }

  return (
    <div className="space-y-6 w-full">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Customer Profiling</h1>
        <p className="text-sm text-gray-500 mt-0.5">Shopify customer data, order history and spend analytics</p>
      </div>

      {/* ── KPI strip ───────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          icon={Users}
          label="Total Customers"
          value={overview.kpis.total_customers}
          sub={`${overview.kpis.new_this_month} new this month`}
          color="text-blue-500"
          bg="bg-blue-50"
        />
        <KpiCard
          icon={TrendingUp}
          label="Total Revenue"
          value={`KES ${formatKES(overview.kpis.total_revenue)}`}
          sub={`KES ${formatKES(overview.kpis.avg_aov)} avg order`}
          color="text-brand-500"
          bg="bg-brand-50"
        />
        <KpiCard
          icon={Repeat}
          label="Retention Rate"
          value={`${Math.round(overview.kpis.retention_rate * 100)}%`}
          sub={`${overview.kpis.repeat_customers} repeat buyers`}
          color="text-amber-500"
          bg="bg-amber-50"
        />
        <KpiCard
          icon={ShoppingBag}
          label="Repeat Buyers"
          value={overview.kpis.repeat_customers}
          sub={`of ${overview.kpis.total_customers} total`}
          color="text-orange-500"
          bg="bg-orange-50"
        />
      </div>

      {/* ── Segments + AOV trend ────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Segments */}
        <div className="card p-5 lg:col-span-1">
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-sm font-bold text-gray-900">Segments</h2>
            <span className="text-xs text-gray-400">RFM-based</span>
          </div>
          <div className="space-y-2">
            {Object.entries(SEGMENT_META).map(([key, meta]) => {
              const count = overview.segmentCounts[key] || 0
              const Icon = SEGMENT_ICONS[key]
              return (
                <button
                  key={key}
                  onClick={() => setSegmentFilter(segmentFilter === key ? 'all' : key)}
                  className={clsx(
                    'w-full flex items-center justify-between p-2.5 rounded-lg border transition-all text-left text-xs',
                    segmentFilter === key
                      ? 'bg-gray-100 border-gray-300'
                      : 'border-gray-200 hover:bg-gray-50'
                  )}
                >
                  <div className="flex items-center gap-2.5">
                    <SegmentBadge color={meta.color}>
                      <Icon size={12} strokeWidth={2.5} />
                    </SegmentBadge>
                    <div>
                      <p className="text-xs font-medium text-gray-900">{meta.label}</p>
                      <p className="text-[10px] text-gray-500">{meta.description}</p>
                    </div>
                  </div>
                  <span className="text-xs font-semibold text-gray-700 tabular-nums">{count}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* AOV by month */}
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-baseline justify-between mb-4">
            <div>
              <h2 className="text-sm font-bold text-gray-900">Average Order Value</h2>
              <p className="text-xs text-gray-400 mt-0.5">Last 6 months</p>
            </div>
            <span className="inline-flex items-center bg-gray-100 text-gray-700 text-xs font-semibold px-2.5 py-1 rounded">KES {formatKES(overview.kpis.avg_aov)}</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={overview.aovByMonth} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis dataKey="month" stroke="#71717a" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis stroke="#71717a" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: '#16161a',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                labelStyle={{ color: '#a1a1aa' }}
              />
              <Line type="monotone" dataKey="aov" stroke="#ff5900" strokeWidth={2}
                    dot={{ fill: '#ff5900', r: 3 }} activeDot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Top performers + channel split ──────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Top spenders */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Top Spenders</h2>
          <div className="space-y-3">
            {overview.topSpenders.map((c, i) => (
              <button
                key={c.id}
                onClick={() => navigate(`/customers/${c.id}`)}
                className="w-full flex items-center gap-3 text-left hover:bg-gray-50 p-2 -mx-2 rounded-lg transition-colors text-xs"
              >
                <span className="text-gray-400 w-4 tabular-nums">{i + 1}</span>
                <Avatar customer={c} size={32} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-900 truncate">{c.name}</p>
                  <p className="text-[10px] text-gray-500">{c.total_orders} orders</p>
                </div>
                <p className="text-xs font-semibold text-gray-700 tabular-nums">
                  KES {formatKES(c.total_spent)}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Most frequent */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Most Frequent Buyers</h2>
          <div className="space-y-3">
            {overview.topFrequent.map((c, i) => (
              <button
                key={c.id}
                onClick={() => navigate(`/customers/${c.id}`)}
                className="w-full flex items-center gap-3 text-left hover:bg-gray-50 p-2 -mx-2 rounded-lg transition-colors text-xs"
              >
                <span className="text-gray-400 w-4 tabular-nums">{i + 1}</span>
                <Avatar customer={c} size={32} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-900 truncate">{c.name}</p>
                  <p className="text-[10px] text-gray-500">KES {formatKES(c.total_spent)}</p>
                </div>
                <p className="text-xs font-semibold text-gray-700 tabular-nums">
                  {c.total_orders} orders
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Channel breakdown */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Acquisition Channel</h2>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie
                data={overview.channelBreakdown}
                dataKey="count"
                nameKey="name"
                innerRadius={45}
                outerRadius={70}
                strokeWidth={0}
              >
                {overview.channelBreakdown.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: '#16161a',
                  border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-3">
            {overview.channelBreakdown.map((ch, i) => (
              <div key={ch.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                  />
                  <span className="text-gray-600 capitalize">{ch.name}</span>
                </div>
                <span className="text-gray-900 font-semibold tabular-nums">{ch.percent}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Top products purchased ─────────────────────────────── */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4">Top Products Purchased</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={overview.topProducts} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="rgba(0,0,0,0.06)" horizontal={false} />
            <XAxis type="number" stroke="#9ca3af" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" stroke="#9ca3af" tick={{ fontSize: 11 }}
                   axisLine={false} tickLine={false} width={140} />
            <Tooltip
              contentStyle={{
                background: '#ffffff',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '12px',
              }}
            />
            <Bar dataKey="purchases" fill="#ff5900" radius={[0, 8, 8, 0]} barCategoryGap="15%" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* ── All Customers section ─────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-gray-900">All Customers</h2>
            <p className="text-xs text-gray-400 mt-0.5">{paginatedCustomers.length} of {filtered.length} shown</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                placeholder="Search customers..."
                value={search}
                onChange={e => { setSearch(e.target.value); setCurrentPage(1) }}
                className="input pl-9 w-56"
              />
            </div>
            <select
              value={sortBy}
              onChange={e => { setSortBy(e.target.value); setCurrentPage(1) }}
              className="input cursor-pointer"
            >
              <option value="spent_desc">Highest spent</option>
              <option value="orders_desc">Most orders</option>
              <option value="recent">Most recent</option>
              <option value="name">Name (A–Z)</option>
            </select>
            
            {/* Export dropdown */}
            <div className="relative group">
              <button className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors">
                <Download size={14} />
                <span>Export</span>
              </button>
              <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                <button onClick={exportToCSV} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 first:rounded-t-lg">
                  <FileText size={13} />
                  Export as CSV
                </button>
                <button onClick={exportToPDF} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2">
                  <File size={13} />
                  Export as PDF
                </button>
                <button onClick={exportToGoogleSheets} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 last:rounded-b-lg">
                  <Sheet size={13} />
                  Export to Sheets
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Active filter chip */}
        {segmentFilter !== 'all' && (
          <button
            onClick={() => { setSegmentFilter('all'); setCurrentPage(1) }}
            className="badge badge-primary mb-3 hover:opacity-80 transition-opacity"
          >
            Filtered: {SEGMENT_META[segmentFilter].label} × Clear
          </button>
        )}

        {/* Customer rows */}
        <div className="card divide-y divide-gray-200">
          {paginatedCustomers.length === 0 ? (
            <div className="p-8 text-center text-gray-400 text-sm">
              No customers match the current filters.
            </div>
          ) : (
            paginatedCustomers.map(c => (
              <CustomerRow key={c.id} customer={c} onClick={() => navigate(`/customers/${c.id}`)} />
            ))
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between gap-4 mt-6">
            <p className="text-xs text-gray-400 font-medium">
              Showing {(currentPage - 1) * ITEMS_PER_PAGE + 1} to {Math.min(currentPage * ITEMS_PER_PAGE, filtered.length)} of {filtered.length} entries
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className={clsx(
                  'flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors',
                  currentPage === 1
                    ? 'border-gray-200 text-gray-300 cursor-not-allowed bg-gray-50'
                    : 'border-gray-200 text-gray-700 hover:bg-gray-50'
                )}
              >
                <ChevronLeft size={14} />
                Previous
              </button>
              
              <div className="flex items-center gap-1">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum
                  if (totalPages <= 5) {
                    pageNum = i + 1
                  } else if (currentPage <= 3) {
                    pageNum = i + 1
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i
                  } else {
                    pageNum = currentPage - 2 + i
                  }
                  
                  return (
                    <button
                      key={pageNum}
                      onClick={() => setCurrentPage(pageNum)}
                      className={clsx(
                        'w-8 h-8 rounded-lg border text-xs font-semibold transition-colors',
                        currentPage === pageNum
                          ? 'bg-black text-white border-black'
                          : 'border-gray-200 text-gray-700 hover:bg-gray-50'
                      )}
                    >
                      {pageNum}
                    </button>
                  )
                })}
              </div>

              <button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className={clsx(
                  'flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors',
                  currentPage === totalPages
                    ? 'border-gray-200 text-gray-300 cursor-not-allowed bg-gray-50'
                    : 'border-gray-200 text-gray-700 hover:bg-gray-50'
                )}
              >
                Next
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}

        <p className="text-xs text-gray-400 text-center font-medium mt-4">
          {filtered.length === 0 ? 'No customers' : `Total: ${filtered.length} entries`}
        </p>
      </div>
    </div>
  )
}

/* ── Subcomponents ────────────────────────────────────────────────── */

function KpiCard({ icon: Icon, label, value, sub, color = 'text-blue-500', bg = 'bg-blue-50' }) {
  return (
    <div className="stat-card relative overflow-hidden">
      {/* Subtle gradient overlay */}
      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300" 
           style={{ background: 'linear-gradient(135deg, rgba(0,0,0,0.02) 0%, rgba(0,0,0,0.04) 100%)' }} />
      
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center border', bg)}>
            <Icon size={16} className={color} />
          </div>
          <span className="text-[10px] font-semibold text-green-600 bg-green-50 px-1.5 py-0.5 rounded">↑ 12%</span>
        </div>
        <p className="text-xs text-gray-500 font-medium mb-1.5">{label}</p>
        <p className="text-2xl font-bold text-gray-900 tabular-nums mb-2">{value}</p>
        {sub && <p className="text-xs text-gray-400 leading-relaxed">{sub}</p>}
      </div>
    </div>
  )
}

function Avatar({ customer, size = 36 }) {
  const initials = customer.name.split(' ').map(p => p[0]).slice(0, 2).join('')
  return (
    <div
      className="rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0"
      style={{ width: size, height: size, background: '#000000' }}
    >
      {initials}
    </div>
  )
}

function SegmentBadge({ color, children }) {
  const classes = {
    brand:   'bg-brand-500/15 text-brand-300 border-brand-500/30',
    success: 'bg-status-success/15 text-emerald-300 border-status-success/30',
    warning: 'bg-status-warning/15 text-amber-300 border-status-warning/30',
    danger:  'bg-status-danger/15 text-rose-300 border-status-danger/30',
    info:    'bg-status-info/15 text-blue-300 border-status-info/30',
    neutral: 'bg-surface-overlay text-ink-secondary border-line',
  }
  return (
    <div className={clsx('w-7 h-7 rounded-md flex items-center justify-center border', classes[color])}>
      {children}
    </div>
  )
}

function CustomerRow({ customer, onClick }) {
  const meta = SEGMENT_META[customer.segment]
  const Icon = SEGMENT_ICONS[customer.segment]
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors text-left text-xs"
    >
      <Avatar customer={customer} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{customer.name}</p>
        <p className="text-xs text-gray-500 truncate">{customer.email} · {customer.location}</p>
      </div>
      <div className="hidden md:flex items-center gap-2">
        <SegmentBadge color={meta.color}>
          <Icon size={12} strokeWidth={2.5} />
        </SegmentBadge>
        <span className="text-xs text-gray-600 w-16">{meta.label}</span>
      </div>
      <div className="hidden sm:block text-right">
        <p className="text-sm font-semibold text-gray-900 tabular-nums">
          KES {formatKES(customer.total_spent)}
        </p>
        <p className="text-xs text-gray-500">{customer.total_orders} orders · {timeAgo(customer.last_order_date)}</p>
      </div>
      <ChevronRight size={16} className="text-gray-400" />
    </button>
  )
}