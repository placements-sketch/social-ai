import { useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, ShoppingBag, TrendingUp,
  Repeat, Tag, Heart, Crown, Sparkles, AlertTriangle, UserMinus, Users,
  ExternalLink, MessageSquare,
} from 'lucide-react'
import {
  LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts'
import clsx from 'clsx'
import {
  MOCK_CUSTOMERS, SEGMENT_META, buildOrderHistory, buildSpendingTrend,
} from '../data/mockCustomers'

const SEGMENT_ICONS = {
  vip: Crown, loyal: Heart, regular: Users, new: Sparkles,
  at_risk: AlertTriangle, churned: UserMinus,
}

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n)
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function CustomerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const customer = MOCK_CUSTOMERS.find(c => c.id === parseInt(id))

  const orders = useMemo(() => customer ? buildOrderHistory(customer) : [], [customer])
  const trend = useMemo(() => customer ? buildSpendingTrend(customer) : [], [customer])

  if (!customer) {
    return (
      <div className="card p-12 text-center max-w-md mx-auto mt-12">
        <h2 className="text-lg font-semibold text-ink-primary">Customer not found</h2>
        <p className="text-sm text-ink-tertiary mt-1">This customer may have been deleted.</p>
        <Link to="/customers" className="btn-secondary mt-4 inline-flex">
          <ArrowLeft size={14} /> Back to customers
        </Link>
      </div>
    )
  }

  const meta = SEGMENT_META[customer.segment]
  const SegmentIcon = SEGMENT_ICONS[customer.segment]

  return (
    <div className="space-y-6 w-full max-w-6xl mx-auto">
      {/* ── Back ────────────────────────────────────────────── */}
      <button
        onClick={() => navigate('/customers')}
        className="text-sm text-ink-secondary hover:text-ink-primary inline-flex items-center gap-1.5 transition-colors"
      >
        <ArrowLeft size={14} /> Back to all customers
      </button>

      {/* ── Header card ─────────────────────────────────────── */}
      <div className="card p-6">
        <div className="flex flex-col md:flex-row md:items-start gap-5">
          {/* Avatar */}
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-semibold shrink-0"
            style={{ background: customer.avatar_color }}
          >
            {customer.name.split(' ').map(p => p[0]).slice(0, 2).join('')}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <h1 className="text-2xl font-bold text-ink-primary tracking-tight">{customer.name}</h1>
              <SegmentPill color={meta.color}>
                <SegmentIcon size={11} strokeWidth={2.5} /> {meta.label}
              </SegmentPill>
            </div>
            <p className="text-sm text-ink-tertiary">{meta.description}</p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mt-4">
              <ContactRow icon={Mail}     value={customer.email} />
              <ContactRow icon={Phone}    value={customer.phone} />
              <ContactRow icon={MapPin}   value={customer.location} />
              <ContactRow icon={Calendar} value={`Joined ${formatDate(customer.created_at)}`} />
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex md:flex-col gap-2 shrink-0">
            <button className="btn-primary">
              <MessageSquare size={14} /> Message
            </button>
            <button className="btn-secondary">
              <ExternalLink size={14} /> Shopify
            </button>
          </div>
        </div>
      </div>

      {/* ── KPI strip ─────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          icon={ShoppingBag}
          label="Total Orders"
          value={customer.total_orders}
        />
        <KpiCard
          icon={TrendingUp}
          label="Lifetime Spend"
          value={`KES ${formatKES(customer.total_spent)}`}
        />
        <KpiCard
          icon={Repeat}
          label="Avg Order Value"
          value={customer.aov ? `KES ${formatKES(customer.aov)}` : '—'}
        />
        <KpiCard
          icon={Calendar}
          label="Last Order"
          value={customer.last_order_date
            ? `${customer.days_since_last_order}d ago`
            : 'Never'}
        />
      </div>

      {/* ── Spending trend ────────────────────────────────── */}
      <div className="card p-5">
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-ink-primary">Spending Trend</h2>
            <p className="text-xs text-ink-tertiary mt-0.5">Last 12 months</p>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={trend} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
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
              formatter={(value) => [`KES ${formatKES(value)}`, 'Spent']}
            />
            <Line type="monotone" dataKey="spent" stroke="#ff5900" strokeWidth={2}
                  dot={{ fill: '#ff5900', r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* ── Two-column: top products + tags ─────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-5 lg:col-span-2">
          <h2 className="text-base font-semibold text-ink-primary mb-4">Favorite Products</h2>
          {customer.top_products.length === 0 ? (
            <p className="text-sm text-ink-tertiary">No purchase history yet.</p>
          ) : (
            <div className="space-y-2.5">
              {customer.top_products.map((product, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-surface-overlay">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-md bg-brand-500/10 flex items-center justify-center">
                      <ShoppingBag size={14} className="text-brand-400" />
                    </div>
                    <span className="text-sm text-ink-primary font-medium">{product}</span>
                  </div>
                  <span className="text-xs text-ink-tertiary">Frequently bought</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card p-5">
          <h2 className="text-base font-semibold text-ink-primary mb-4">Tags & Preferences</h2>
          <div className="space-y-3">
            <div>
              <p className="text-xs text-ink-tertiary mb-2">Tags</p>
              {customer.tags.length === 0 ? (
                <p className="text-sm text-ink-tertiary">No tags</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {customer.tags.map(tag => (
                    <span key={tag} className="badge badge-neutral">
                      <Tag size={10} /> {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="border-t border-line pt-3">
              <p className="text-xs text-ink-tertiary mb-1">Primary Channel</p>
              <p className="text-sm text-ink-primary capitalize">{customer.primary_channel.replace('_', ' ')}</p>
            </div>
            <div className="border-t border-line pt-3">
              <p className="text-xs text-ink-tertiary mb-1">Marketing Consent</p>
              <p className="text-sm text-ink-primary">
                {customer.accepts_marketing
                  ? <span className="text-emerald-400">Opted in</span>
                  : <span className="text-ink-secondary">Opted out</span>}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Order history ─────────────────────────────────── */}
      <div className="card">
        <div className="p-5 border-b border-line">
          <h2 className="text-base font-semibold text-ink-primary">Order History</h2>
          <p className="text-xs text-ink-tertiary mt-0.5">{orders.length} {orders.length === 1 ? 'order' : 'orders'} total</p>
        </div>
        {orders.length === 0 ? (
          <div className="p-8 text-center">
            <ShoppingBag size={32} className="text-ink-quaternary mx-auto mb-2" />
            <p className="text-sm text-ink-tertiary">No orders yet</p>
          </div>
        ) : (
          <div className="divide-y divide-line">
            {orders.map(order => (
              <div key={order.id} className="p-4 flex items-center gap-4 hover:bg-surface-overlay transition-colors">
                <div className="w-10 h-10 rounded-lg bg-surface-overlay border border-line flex items-center justify-center shrink-0">
                  <ShoppingBag size={16} className="text-ink-secondary" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-ink-primary">{order.id}</p>
                    <OrderStatusBadge status={order.status} />
                  </div>
                  <p className="text-xs text-ink-tertiary mt-0.5">
                    {formatDate(order.date)} · {order.items} {order.items === 1 ? 'item' : 'items'}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-sm font-semibold text-ink-primary tabular-nums">
                    KES {formatKES(order.total)}
                  </p>
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

function ContactRow({ icon: Icon, value }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-secondary">
      <Icon size={14} className="text-ink-tertiary shrink-0" />
      <span className="truncate">{value}</span>
    </div>
  )
}

function KpiCard({ icon: Icon, label, value }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-md bg-surface-overlay flex items-center justify-center">
          <Icon size={14} className="text-ink-secondary" />
        </div>
        <p className="text-xs text-ink-secondary font-medium">{label}</p>
      </div>
      <p className="text-xl font-semibold text-ink-primary tabular-nums tracking-tight">{value}</p>
    </div>
  )
}

function SegmentPill({ color, children }) {
  const classes = {
    brand:   'bg-brand-500/15 text-brand-300 border-brand-500/30',
    success: 'bg-status-success/15 text-emerald-300 border-status-success/30',
    warning: 'bg-status-warning/15 text-amber-300 border-status-warning/30',
    danger:  'bg-status-danger/15 text-rose-300 border-status-danger/30',
    info:    'bg-status-info/15 text-blue-300 border-status-info/30',
    neutral: 'bg-surface-overlay text-ink-secondary border-line',
  }
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border', classes[color])}>
      {children}
    </span>
  )
}

function OrderStatusBadge({ status }) {
  const map = {
    fulfilled: 'badge-success',
    pending:   'badge-warning',
    refunded:  'badge-danger',
  }
  return <span className={clsx('badge', map[status] || 'badge-neutral')}>{status}</span>
}