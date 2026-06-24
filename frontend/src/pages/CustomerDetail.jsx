import { useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, ShoppingBag, TrendingUp,
  Repeat, Tag, Heart, Crown, Sparkles, AlertTriangle, UserMinus, Users,
  ExternalLink, Download, FileText, File,
} from 'lucide-react'
import {
  LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import clsx from 'clsx'
import {
  MOCK_CUSTOMERS, SEGMENT_META, buildOrderHistory, buildSpendingTrend,
} from '../data/mockCustomers'
import { parseBackendTime } from '../utils/time'


const SEGMENT_ICONS = {
  vip: Crown, loyal: Heart, regular: Users, new: Sparkles,
  at_risk: AlertTriangle, churned: UserMinus,
}

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n)
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = parseBackendTime(iso)
  return d ? d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
}

export default function CustomerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const customer = MOCK_CUSTOMERS.find(c => c.id === parseInt(id))

  const orders = useMemo(() => customer ? buildOrderHistory(customer) : [], [customer])
  const trend = useMemo(() => customer ? buildSpendingTrend(customer) : [], [customer])

  if (!customer) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <h2 className="text-lg font-semibold text-gray-900">Customer not found</h2>
          <p className="text-sm text-gray-500 mt-1">This customer may have been deleted.</p>
          <Link to="/customers" className="inline-flex items-center gap-2 mt-4 text-brand-600 hover:text-brand-700 font-medium text-sm">
            <ArrowLeft size={14} /> Back to customers
          </Link>
        </div>
      </div>
    )
  }

  const meta = SEGMENT_META[customer.segment]
  const SegmentIcon = SEGMENT_ICONS[customer.segment]

  const exportToCSV = () => {
    const headers = ['Order ID', 'Date', 'Items', 'Total', 'Status']
    const rows = orders.map(o => [o.id, formatDate(o.date), o.items, `KES ${formatKES(o.total)}`, o.status])
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${customer.name}-orders.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  const exportToPDF = async () => {
    const { jsPDF } = await import('jspdf')
    const { autoTable } = await import('jspdf-autotable')
    
    const doc = new jsPDF()
    const headers = ['Order ID', 'Date', 'Items', 'Total', 'Status']
    const rows = orders.map(o => [o.id, formatDate(o.date), o.items, `KES ${formatKES(o.total)}`, o.status])
    
    doc.text(`Order History - ${customer.name}`, 14, 15)
    autoTable(doc, {
      head: [headers],
      body: rows,
      startY: 25,
      styles: { fontSize: 9, cellPadding: 3 },
      headStyles: { fillColor: [0, 0, 0], textColor: [255, 255, 255] },
    })
    
    doc.save(`${customer.name}-orders.pdf`)
  }

  return (
    <div className="w-full px-4 md:px-8 pb-12">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="mb-8">
        <button
          onClick={() => navigate('/customers')}
          className="text-sm text-gray-500 hover:text-gray-700 inline-flex items-center gap-1.5 transition-colors mb-4"
        >
          <ArrowLeft size={14} /> Back
        </button>
      </div>

      {/* ── Hero Section: Customer Profile ─────────────────── */}
      <div className="mb-8">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
          <div className="flex items-end gap-4">
            {/* Avatar */}
            <div
              className="w-20 h-20 rounded-2xl flex items-center justify-center text-white text-2xl font-bold shrink-0"
              style={{ background: customer.avatar_color }}
            >
              {customer.name.split(' ').map(p => p[0]).slice(0, 2).join('')}
            </div>

            {/* Info */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <h1 className="text-2xl font-bold text-gray-900">{customer.name}</h1>
                <SegmentBadge color={meta.color}>
                  <SegmentIcon size={11} strokeWidth={2.5} />
                </SegmentBadge>
              </div>
              <p className="text-sm text-gray-500">{meta.description}</p>
            </div>
          </div>

          {/* Quick Actions */}
          <button className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors">
            <ExternalLink size={13} />
            <span>Open in Shopify</span>
          </button>
        </div>
      </div>

      {/* ── Contact Grid ────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-8">
        <div className="px-3 sm:px-4 py-3 rounded-xl border border-gray-100 bg-gray-50/50 min-w-0">
          <p className="text-xs text-gray-500 font-medium mb-1">Email</p>
          <p className="text-sm text-gray-900 font-medium truncate">{customer.email}</p>
        </div>
        <div className="px-3 sm:px-4 py-3 rounded-xl border border-gray-100 bg-gray-50/50 min-w-0">
          <p className="text-xs text-gray-500 font-medium mb-1">Phone</p>
          <p className="text-sm text-gray-900 font-medium truncate">{customer.phone}</p>
        </div>
        <div className="px-3 sm:px-4 py-3 rounded-xl border border-gray-100 bg-gray-50/50 min-w-0">
          <p className="text-xs text-gray-500 font-medium mb-1">Location</p>
          <p className="text-sm text-gray-900 font-medium truncate">{customer.location}</p>
        </div>
        <div className="px-3 sm:px-4 py-3 rounded-xl border border-gray-100 bg-gray-50/50 min-w-0">
          <p className="text-xs text-gray-500 font-medium mb-1">Joined</p>
          <p className="text-sm text-gray-900 font-medium truncate">{formatDate(customer.created_at)}</p>
        </div>
      </div>

      {/* ── KPI Metrics ────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8">
        <MetricCard
          icon={ShoppingBag}
          label="Orders"
          value={customer.total_orders}
          color="text-blue-600"
          bg="bg-blue-50"
        />
        <MetricCard
          icon={TrendingUp}
          label="Spent"
          value={`KES ${formatKES(customer.total_spent)}`}
          color="text-brand-600"
          bg="bg-brand-50"
        />
        <MetricCard
          icon={Repeat}
          label="Avg Order"
          value={customer.aov ? `KES ${formatKES(customer.aov)}` : '—'}
          color="text-amber-600"
          bg="bg-amber-50"
        />
        <MetricCard
          icon={Calendar}
          label="Last Order"
          value={customer.last_order_date ? `${customer.days_since_last_order}d ago` : 'Never'}
          color="text-green-600"
          bg="bg-green-50"
        />
      </div>

      {/* ── Two Column: Chart + Details ───────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Spending Trend Chart */}
        <div className="lg:col-span-2 card p-6">
          <div className="mb-6">
            <h2 className="text-sm font-bold text-gray-900">Spending Trend</h2>
            <p className="text-xs text-gray-500 mt-1">Last 12 months</p>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trend} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="rgba(0,0,0,0.05)" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#a1a1aa' }} axisLine={false} tickLine={false} />
              <Tooltip 
                contentStyle={{
                  background: '#000000',
                  border: 'none',
                  borderRadius: '8px',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  padding: '8px 12px'
                }}
                labelStyle={{ color: '#ffffff', fontWeight: 600, fontSize: 11, marginBottom: '4px' }}
                formatter={(value) => [`KES ${formatKES(value)}`, 'Spent']}
              />
              <Line 
                type="natural" 
                dataKey="spent" 
                stroke="#ff5900" 
                strokeWidth={1.5}
                dot={false}
                activeDot={{ r: 5, fill: '#ff5900' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Side Details */}
        <div className="space-y-4">
          {/* Tags */}
          <div className="card p-5">
            <h3 className="text-sm font-bold text-gray-900 mb-3">Tags</h3>
            {customer.tags.length === 0 ? (
              <p className="text-xs text-gray-500">No tags assigned</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {customer.tags.map(tag => (
                  <span key={tag} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-gray-100 text-gray-700 text-xs font-medium">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Channel */}
          <div className="card p-5">
            <p className="text-xs text-gray-500 font-medium mb-1">Primary Channel</p>
            <p className="text-sm font-semibold text-gray-900 capitalize">{customer.primary_channel.replace('_', ' ')}</p>
          </div>

          {/* Marketing */}
          <div className="card p-5">
            <p className="text-xs text-gray-500 font-medium mb-1">Marketing</p>
            <p className={clsx('text-sm font-semibold', customer.accepts_marketing ? 'text-green-600' : 'text-gray-600')}>
              {customer.accepts_marketing ? 'Opted in' : 'Opted out'}
            </p>
          </div>
        </div>
      </div>

      {/* ── Order History ─────────────────────────────────── */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-sm font-bold text-gray-900">Order History</h2>
            <p className="text-xs text-gray-500 mt-0.5">{orders.length} {orders.length === 1 ? 'order' : 'orders'}</p>
          </div>
          <div className="relative group">
            <button className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors">
              <Download size={13} />
              <span>Export</span>
            </button>
            <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              <button onClick={exportToCSV} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 first:rounded-t-lg">
                <FileText size={13} />
                Export as CSV
              </button>
              <button onClick={exportToPDF} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 last:rounded-b-lg">
                <File size={13} />
                Export as PDF
              </button>
            </div>
          </div>
        </div>

        {orders.length === 0 ? (
          <div className="p-12 text-center">
            <ShoppingBag size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500">No orders yet</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {orders.map(order => (
              <div key={order.id} className="px-6 py-3.5 flex items-center justify-between hover:bg-gray-50/50 transition-colors">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="text-sm font-semibold text-gray-900">{order.id}</p>
                    <span className={clsx('text-xs font-semibold px-2 py-0.5 rounded-lg', 
                      order.status === 'fulfilled' ? 'bg-green-100 text-green-700' :
                      order.status === 'pending' ? 'bg-amber-100 text-amber-700' :
                      'bg-red-100 text-red-700'
                    )}>
                      {order.status}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">
                    {formatDate(order.date)} · {order.items} {order.items === 1 ? 'item' : 'items'}
                  </p>
                </div>
                <div className="text-right ml-4 shrink-0">
                  <p className="text-sm font-bold text-gray-900">KES {formatKES(order.total)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Subcomponents ────────────────────────────────────────────────── */

function MetricCard({ icon: Icon, label, value, color, bg }) {
  return (
    <div className="card p-3 sm:p-4 min-w-0">
      <div className="flex items-center gap-2 sm:gap-2.5 mb-3">
        <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0', bg)}>
          <Icon size={15} className={color} />
        </div>
        <p className="text-xs font-medium text-gray-600 truncate">{label}</p>
      </div>
      <p className="text-lg sm:text-xl font-bold text-gray-900 truncate">{value}</p>
    </div>
  )
}

function SegmentBadge({ color, children }) {
  const classes = {
    brand:   'bg-brand-100 text-brand-700',
    success: 'bg-green-100 text-green-700',
    warning: 'bg-amber-100 text-amber-700',
    danger:  'bg-red-100 text-red-700',
    info:    'bg-blue-100 text-blue-700',
    neutral: 'bg-gray-100 text-gray-700',
  }
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-semibold', classes[color])}>
      {children}
    </span>
  )
}
