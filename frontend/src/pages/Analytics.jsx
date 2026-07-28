import { useState, useEffect } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  Users, Download, FileText, File, Bolt, MessageSquare, ArrowUpRight, UserCheck,
  TrendingUp, TrendingDown, Minus, Bot, ShoppingBag, AlertTriangle, Radio, Package, ExternalLink,
} from 'lucide-react'
import { SkeletonAnalytics } from '../components/Skeleton'
import { useAuth } from '../context/AuthContext'
import { useCountAnimation } from '../hooks/useCountAnimation'
import clsx from 'clsx'
import { exportAnalyticsCSV, exportAnalyticsPDF } from '../utils/reportExport'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const ACCENT = '#c7ea46'

// Coordinated donut palette: accent → warm → taupe → grays. Not a rainbow.
const DONUT = ['#c7ea46', '#d6f278', '#c99a86', '#8a8a93', '#a1a1aa', '#c4c4cc', '#d4d4d8']

const DATE_RANGES = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
]

const SHADOW = '0 1px 2px rgba(16,24,40,0.04), 0 8px 24px -12px rgba(16,24,40,0.10)'

function Eyebrow({ children, className }) {
  return (
    <span className={clsx('text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-400', className)}>
      {children}
    </span>
  )
}

function Delta({ current, previous, isPct = false }) {
  const cur = Number(current) || 0
  const prev = Number(previous) || 0
  const diff = isPct ? (cur - prev) * 100 : cur - prev
  const flat = Math.abs(diff) < (isPct ? 0.05 : 0.5)
  const up = diff > 0
  const Icon = flat ? Minus : up ? TrendingUp : TrendingDown
  const val = isPct
    ? `${Math.abs(diff).toFixed(1)} pts`
    : `${up ? '↑' : diff < 0 ? '↓' : ''}${Math.abs(Math.round((diff / (prev || 1)) * 100))}%`
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold',
      flat ? 'text-gray-400' : up ? 'text-emerald-600' : 'text-gray-500')}>
      {isPct && <Icon size={13} />}{val}
    </span>
  )
}

function Panel({ title, right, children, className, bodyClass, lift }) {
  return (
    <div
      className={clsx('bg-white border border-gray-200/70 rounded-2xl transition-all duration-200', lift && 'hover:-translate-y-0.5', className)}
      style={{ boxShadow: SHADOW }}
    >
      {(title || right) && (
        <div className="flex items-center justify-between px-5 pt-4 pb-3.5 border-b border-gray-100">
          {title && <span className="text-sm font-semibold text-gray-900">{title}</span>}
          {right}
        </div>
      )}
      <div className={clsx('p-5', bodyClass)}>{children}</div>
    </div>
  )
}

function StatTile({ icon: Icon, label, value, isPercent, isTime, current, previous, delay = 0 }) {
  const numeric = isTime
    ? (value == null ? 0 : value / 1000)
    : isPercent ? (value || 0) * 100 : (value || 0)
  const animated = useCountAnimation(numeric, 1600, isPercent || isTime)

  let display
  if (isTime) display = value == null ? '—' : value < 1 ? '<1ms' : value < 1000 ? `${value}ms` : `${animated.toFixed(1)}s`
  else if (isPercent) display = `${animated.toFixed(1)}%`
  else display = Math.round(animated).toLocaleString()

  return (
    <div
      className="bg-white border border-gray-200/70 rounded-2xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-gray-300"
      style={{ boxShadow: SHADOW, animation: 'an-rise .5s ease both', animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="w-8 h-8 rounded-[10px] bg-gray-100 flex items-center justify-center text-gray-500"><Icon size={16} /></span>
        {current != null && previous != null && <Delta current={current} previous={previous} />}
      </div>
      <p className="text-[23px] font-bold text-gray-900 tabular-nums leading-none tracking-tight">{display}</p>
      <Eyebrow className="block mt-1.5">{label}</Eyebrow>
    </div>
  )
}

// Donut with coordinated palette + center total + legend. For part-to-whole (intents).
function Donut({ rows, centerLabel = 'total', emptyText = 'No data yet' }) {
  if (!rows || rows.length === 0) return <p className="text-xs text-gray-400 py-10 text-center">{emptyText}</p>
  const total = rows.reduce((s, r) => s + (Number(r.value) || 0), 0) || 1
  const top = rows.slice(0, 6)
  const R = 15.9155
  let offset = 25 // start at top
  return (
    <div className="flex items-center gap-5">
      <div className="relative shrink-0" style={{ width: 132, height: 132 }}>
        <svg width="132" height="132" viewBox="0 0 42 42">
          <circle cx="21" cy="21" r={R} fill="none" stroke="#f4f4f5" strokeWidth="5" />
          {top.map((r, i) => {
            const frac = (Number(r.value) || 0) / total
            const len = frac * 100
            const dash = `${len} ${100 - len}`
            const el = (
              <circle key={i} cx="21" cy="21" r={R} fill="none" stroke={DONUT[i]} strokeWidth="5"
                strokeDasharray={dash} strokeDashoffset={offset} strokeLinecap="butt"
                style={{ transition: 'stroke-dasharray .9s cubic-bezier(0.16,1,0.3,1)' }} />
            )
            offset -= len
            return el
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[22px] font-bold text-gray-900 leading-none tabular-nums">{total.toLocaleString()}</span>
          <Eyebrow className="mt-0.5">{centerLabel}</Eyebrow>
        </div>
      </div>
      <div className="flex-1 flex flex-col gap-2 min-w-0">
        {top.map((r, i) => {
          const pct = Math.round(((Number(r.value) || 0) / total) * 100)
          return (
            <div key={i} className="flex items-center justify-between text-xs gap-2">
              <span className="flex items-center gap-2 min-w-0">
                <span className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: DONUT[i] }} />
                <span className="text-gray-600 truncate">{r.label}</span>
              </span>
              <span className="font-bold text-gray-900 tabular-nums shrink-0">{pct}%</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Ranked product cards — thumbnail, name, price, ask-count. Links to storefront.
function TopProducts({ rows, emptyText = 'No product questions yet' }) {
  if (!rows || rows.length === 0) return <p className="text-xs text-gray-400 py-6 text-center">{emptyText}</p>
  return (
    <div className="flex flex-col -my-1">
      {rows.map((p, i) => {
        const href = p.handle ? `https://www.shopzetu.com/products/${p.handle}` : null
        const Row = href ? 'a' : 'div'
        const rowProps = href ? { href, target: '_blank', rel: 'noopener noreferrer' } : {}
        return (
          <Row key={p.handle || p.name || i} {...rowProps}
            className="group flex items-center gap-3.5 py-2.5 px-2 -mx-2 rounded-xl hover:bg-gray-50/80 transition-colors"
            style={{ animation: 'an-rise .4s ease both', animationDelay: `${i * 50}ms` }}>
            <span className={clsx('text-xs font-bold w-4 text-center shrink-0 tabular-nums', i === 0 ? 'text-brand-600' : 'text-gray-400')}>{i + 1}</span>
            <div className="w-11 h-11 rounded-xl overflow-hidden shrink-0 bg-gradient-to-br from-brand-100 to-brand-50 flex items-center justify-center">
              {p.image
                ? <img src={p.image} alt="" className="w-full h-full object-cover" loading="lazy" />
                : <Package size={18} className="text-brand-500" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-gray-900 truncate group-hover:text-black">{p.name}</p>
              <p className="text-xs text-gray-500 mt-0.5">{p.price ? `KES ${Number(p.price).toLocaleString()}` : '—'}</p>
            </div>
            <div className="text-right shrink-0">
              <p className={clsx('text-[15px] font-bold leading-none tabular-nums', i === 0 ? 'text-brand-600' : 'text-gray-900')}>{p.mentions}</p>
              <Eyebrow className="block mt-0.5">asks</Eyebrow>
            </div>
          </Row>
        )
      })}
    </div>
  )
}

// Ranked bars — for genuine rankings (products) and small categoricals (channels, failures).
function RankedBars({ rows, emptyText = 'No data in this period' }) {
  if (!rows || rows.length === 0) return <p className="text-xs text-gray-400 py-6 text-center">{emptyText}</p>
  const max = Math.max(...rows.map((r) => Number(r.value) || 0), 1)
  const grays = ['#3f3f46', '#52525b', '#71717a', '#a1a1aa', '#c4c4cc', '#d4d4d8']
  return (
    <div className="flex flex-col gap-3.5">
      {rows.map((r, i) => {
        const val = Number(r.value) || 0
        const pct = Math.round((val / max) * 100)
        const color = i === 0 ? ACCENT : grays[Math.min(i - 1, grays.length - 1)]
        const Row = r.href ? 'a' : 'div'
        const rowProps = r.href
          ? { href: r.href, target: '_blank', rel: 'noopener noreferrer', className: 'group block' }
          : {}
        return (
          <Row key={r.label + i} {...rowProps}>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className={clsx('text-xs truncate pr-3 flex items-center gap-1', r.href ? 'text-gray-600 group-hover:text-gray-900 transition-colors' : 'text-gray-600')}>
                {r.label}
                {r.href && <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 shrink-0" />}
              </span>
              <span className="text-xs font-bold text-gray-900 tabular-nums shrink-0">{val.toLocaleString()}</span>
            </div>
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color, transition: 'width .9s cubic-bezier(0.16,1,0.3,1)', transitionDelay: `${i * 60}ms` }} />
            </div>
          </Row>
        )
      })}
    </div>
  )
}

// Conversion funnel — how often an AI product recommendation turns into an
// order. Only two stages, because that's what the attribution data actually
// supports; the money sits alongside so the panel answers "did this sell?"
function Funnel({ conversion }) {
  const recommended = conversion?.recommended_conversations || 0
  const converted   = conversion?.converted_conversations   || 0
  const rate        = (conversion?.conversion_rate || 0) * 100
  const orders      = conversion?.attributed_orders  || 0
  const revenue     = conversion?.attributed_revenue || 0

  if (recommended === 0) {
    return (
      <p className="text-xs text-gray-400 py-8 text-center">
        Nothing to show yet — this fills in once the AI starts sending tracked
        product links and orders come back against them.
      </p>
    )
  }

  const convPct = (converted / recommended) * 100
  const lost = Math.max(0, recommended - converted)
  const fmtKES = (n) => `KES ${Number(n).toLocaleString('en-KE', { maximumFractionDigits: 0 })}`

  const stages = [
    {
      label: 'AI recommended a product',
      help: 'Conversations where the assistant sent a tracked product link',
      value: recommended, pct: 100, color: ACCENT,
    },
    {
      label: 'Customer ordered',
      help: 'Those that produced an order we can attribute back',
      value: converted, pct: convPct, color: '#111827',
    },
  ]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-3 space-y-4">
        {stages.map((s, i) => (
          <div key={s.label}>
            <div className="flex items-baseline justify-between gap-3 mb-1.5">
              <div className="min-w-0">
                <p className="text-xs font-semibold text-gray-800 truncate">{s.label}</p>
                <p className="text-[11px] text-gray-400 truncate">{s.help}</p>
              </div>
              <div className="text-right shrink-0">
                <span className="text-sm font-bold text-gray-900 tabular-nums">
                  {s.value.toLocaleString()}
                </span>
                {i > 0 && (
                  <span className="text-[11px] text-gray-400 ml-1.5 tabular-nums">
                    {s.pct.toFixed(1)}%
                  </span>
                )}
              </div>
            </div>
            <div className="h-9 rounded-lg bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-lg"
                style={{
                  width: `${Math.max(s.pct, 1.5)}%`,
                  background: s.color,
                  transition: 'width .9s cubic-bezier(0.16,1,0.3,1)',
                  transitionDelay: `${i * 120}ms`,
                }}
              />
            </div>
            {i === 0 && (
              <div className="flex items-center gap-2 pl-1 mt-2">
                <div className="w-px h-4 bg-gray-200" />
                <p className="text-[11px] text-gray-400 tabular-nums">
                  {lost.toLocaleString()} didn’t order
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="lg:col-span-2 grid grid-cols-3 lg:grid-cols-1 gap-3">
        {[
          { label: 'Conversion rate',    value: `${rate.toFixed(1)}%`, accent: true },
          { label: 'Attributed orders',  value: orders.toLocaleString() },
          { label: 'Attributed revenue', value: fmtKES(revenue) },
        ].map(({ label, value, accent }) => (
          <div
            key={label}
            className={clsx('rounded-xl px-4 py-3 border',
              accent ? 'border-transparent' : 'border-gray-100 bg-white')}
            style={accent ? { background: 'rgba(255,89,0,0.07)' } : undefined}
          >
            <p
              className={clsx('text-xl font-bold tabular-nums leading-none truncate',
                !accent && 'text-gray-900')}
              style={accent ? { color: ACCENT } : undefined}
            >
              {value}
            </p>
            <p className="text-[11px] text-gray-500 mt-1.5">{label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function AreaTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 text-white rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="text-gray-300 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="font-semibold tabular-nums" style={{ color: p.stroke }}>{p.name}: {p.value}</p>
      ))}
    </div>
  )
}

function HeroBand({ kpis, weekly, periodLabel }) {
  const prev = kpis.previous || {}
  const successPct = (kpis.ai_success_rate || 0) * 100
  const animated = useCountAnimation(successPct, 1600, true)
  const handled = kpis.ai_handled_total || 0
  const engaged = kpis.ai_engaged_total || 0
  const series = (weekly || []).slice(-8).map((w) => w.ai_replied || w.inbound || 0)
  const sMax = Math.max(...series, 1)
  const diff = successPct - (prev.ai_success_rate || 0) * 100
  const up = diff >= 0

  return (
    <div className="rounded-2xl px-6 py-5" style={{
      border: '0.5px solid rgba(255,89,0,0.18)',
      background: 'linear-gradient(135deg, #fff8f4 0%, #ffffff 62%)',
      boxShadow: '0 1px 2px rgba(16,24,40,0.04), 0 12px 32px -14px rgba(255,89,0,0.18)',
    }}>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: ACCENT, boxShadow: '0 0 0 3px rgba(255,89,0,0.15)' }} />
            <Eyebrow>AI performance · {periodLabel}</Eyebrow>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="font-bold tabular-nums leading-[0.9]" style={{ color: ACCENT, fontSize: 56, letterSpacing: '-0.02em' }}>
              {animated.toFixed(1)}<span style={{ fontSize: 34 }}>%</span>
            </span>
            <div className="flex flex-col gap-1">
              <span className="text-[13px] text-gray-600 font-medium">success rate</span>
              <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold', up ? 'text-emerald-600' : 'text-gray-500')}>
                {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />}{Math.abs(diff).toFixed(1)} pts
              </span>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-2.5">{engaged.toLocaleString()} of {handled.toLocaleString()} conversations handled &amp; engaged</p>
        </div>
        <div className="flex items-end gap-1 h-16 pt-1" aria-hidden="true">
          {series.map((v, i) => {
            const h = Math.max(6, Math.round((v / sMax) * 56))
            const isLast = i >= series.length - 2
            return <div key={i} style={{ width: 13, height: h, borderRadius: 3, background: isLast ? ACCENT : `rgba(255,89,0,${0.22 + (i / series.length) * 0.5})`, transformOrigin: 'bottom', animation: 'an-grow .6s ease both', animationDelay: `${i * 40}ms` }} />
          })}
        </div>
      </div>
    </div>
  )
}

export default function Analytics() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [agentData, setAgentData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [days, setDays] = useState(7)
  const [exportOpen, setExportOpen] = useState(false)

  useEffect(() => { fetchAnalytics() }, [days])

  const fetchAnalytics = async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API_BASE}/analytics/summary?days=${days}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Could not load analytics. Try again.')
      setData(await res.json())
      if (user?.role === 'supervisor' || user?.role === 'admin') {
        try {
          const agentRes = await fetch(`${API_BASE}/analytics/agents?days=${days}`, {
            headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
          })
          if (agentRes.ok) setAgentData(await agentRes.json())
        } catch (err) { console.error('Failed to load agent data:', err) }
      }
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  if (loading) return <SkeletonAnalytics />
  if (error) return <div className="bg-white border border-gray-200 rounded-2xl p-6 text-sm text-gray-700" style={{ boxShadow: SHADOW }}>{error}</div>
  if (!data) return null

  const { kpis, weekly, intent_breakdown, channel_split, top_products, failure_breakdown, conversion } = data
  const prev = kpis.previous || {}
  const periodLabel = days === 1 ? 'today' : days === 7 ? 'last 7 days' : days === 30 ? 'last 30 days' : `last ${days} days`

  const getSubtitle = () => {
    if (user?.role === 'agent') return 'Performance across your assigned conversations'
    if (user?.role === 'supervisor') return 'Company overview and agent performance'
    return 'Company-wide AI support analytics'
  }

  const exportMeta = () => ({
    periodLabel: DATE_RANGES.find((r) => r.days === days)?.label || `Last ${days} days`,
    generatedAt: new Date().toLocaleString(), periodSlug: `${days}d`, dateSlug: new Date().toISOString().split('T')[0],
  })
  const reportData = () => ({ ...data, agents: agentData?.agents || [] })
  const exportToCSV = () => exportAnalyticsCSV(reportData(), exportMeta())
  const exportToPDF = () => exportAnalyticsPDF(reportData(), exportMeta())

  const aiReplies = kpis.ai_replies_total || 0
  // Conversations ÷ conversations. Was conversations ÷ messages.
  const convTotal = kpis.conversations_total || 0
  const overrideRate = convTotal > 0 ? (kpis.human_override_total || 0) / convTotal : 0

  const conv = data.conversion || {}
  const convRate = ((conv.conversion_rate || 0) * 100).toFixed(1)
  const revenue = Math.round(conv.attributed_revenue || 0)
  const funnelSteps = [
    { label: 'Recommended', value: conv.recommended_conversations || 0 },
    { label: 'Converted', value: conv.converted_conversations || 0 },
  ]

  const FAILURE_LABELS = {
    rate_limit: 'Rate limit hit', timeout: 'Timed out', auth: 'Auth error', bad_request: 'Bad request',
    api_error: 'Claude API error', network: 'Network error', bad_output: 'Malformed response', unknown: 'Unknown error',
  }
  const failureRows = (failure_breakdown || []).map((f) => ({ label: FAILURE_LABELS[f.reason] || f.reason, value: f.count }))
  const isStaffLead = user?.role === 'supervisor' || user?.role === 'admin'

  return (
    <div className="space-y-5 w-full px-0 lg:px-8 pb-10">
      <style>{`
        @keyframes an-rise { from { opacity:0; transform:translateY(10px) } to { opacity:1; transform:translateY(0) } }
        @keyframes an-grow { from { transform:scaleY(0) } to { transform:scaleY(1) } }
      `}</style>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Analytics</h1>
          <p className="text-sm text-gray-500 mt-0.5">{getSubtitle()}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex p-0.5 bg-gray-100 rounded-lg">
            {DATE_RANGES.map((range) => (
              <button key={range.days} onClick={() => setDays(range.days)}
                className={clsx('text-xs font-semibold px-3 py-1.5 rounded-md transition-all',
                  days === range.days ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800')}>
                {range.label}
              </button>
            ))}
          </div>
          <div className="relative">
            <button onClick={() => setExportOpen((o) => !o)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-900 text-white text-xs font-semibold hover:bg-black transition-colors">
              <Download size={14} /><span>Export</span>
            </button>
            {exportOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setExportOpen(false)} />
                <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
                  <button onClick={() => { exportToCSV(); setExportOpen(false) }} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 first:rounded-t-lg"><FileText size={13} /> Export as CSV</button>
                  <button onClick={() => { exportToPDF(); setExportOpen(false) }} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 last:rounded-b-lg"><File size={13} /> Export as PDF</button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <HeroBand kpis={kpis} weekly={weekly} periodLabel={periodLabel} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile icon={Bolt}          label="Avg response"  value={kpis.avg_response_time_ms} isTime delay={40} />
        <StatTile icon={MessageSquare} label="Inbound"       value={kpis.inbound_total}   current={kpis.inbound_total}   previous={prev.inbound_total}   delay={90} />
        <StatTile icon={ArrowUpRight}  label="Escalated"     value={kpis.escalated_total} current={kpis.escalated_total} previous={prev.escalated_total} delay={140} />
        <StatTile icon={UserCheck}     label="Override rate" value={overrideRate} isPercent delay={190} />
      </div>

      {/* Volume — area/line trend */}
      <Panel title="Message volume" right={<Eyebrow>{periodLabel}</Eyebrow>} bodyClass="pt-4" lift>
        <ResponsiveContainer width="100%" height={230}>
          <AreaChart data={weekly || []} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
            <defs>
              <linearGradient id="gInbound" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a1a1aa" stopOpacity={0.18} /><stop offset="100%" stopColor="#a1a1aa" stopOpacity={0} /></linearGradient>
              <linearGradient id="gAi" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={ACCENT} stopOpacity={0.22} /><stop offset="100%" stopColor={ACCENT} stopOpacity={0} /></linearGradient>
            </defs>
            <CartesianGrid stroke="#f1f1f2" vertical={false} />
            <XAxis dataKey="day" tick={{ fill: '#a1a1aa', fontSize: 11, fontFamily: 'Quicksand', fontWeight: 600 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#a1a1aa', fontSize: 11, fontFamily: 'Quicksand' }} axisLine={false} tickLine={false} width={40} />
            <Tooltip content={<AreaTooltip />} />
            <Area type="monotone" dataKey="inbound" name="Inbound" stroke="#a1a1aa" strokeWidth={2} fill="url(#gInbound)" />
            <Area type="monotone" dataKey="ai_replied" name="AI replied" stroke={ACCENT} strokeWidth={2.5} fill="url(#gAi)" />
          </AreaChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-5 mt-3 pl-1">
          <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-4 h-0.5 rounded bg-gray-400" />Inbound</span>
          <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-4 h-0.5 rounded" style={{ background: ACCENT }} />AI replied</span>
        </div>
      </Panel>

      {/* Intents (donut) + Channels (bars) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Top customer intents" right={<Bot size={15} className="text-gray-300" />} lift>
          <Donut rows={(intent_breakdown || []).map((it) => ({ label: it.name, value: it.count }))} centerLabel="messages" emptyText="No intent data yet" />
        </Panel>
        <Panel title="Channels" right={<Radio size={15} className="text-gray-300" />} lift>
          <RankedBars rows={(channel_split || []).map((c) => ({ label: c.name, value: c.count }))} emptyText="No channel data yet" />
        </Panel>
      </div>

      {/* Products (bars) + Failures (bars) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Most asked-about products" right={<Package size={15} className="text-gray-300" />} lift bodyClass="p-4">
          <TopProducts rows={top_products || []} />
        </Panel>
        <Panel title="AI failures by reason" right={<AlertTriangle size={15} className="text-gray-300" />} lift>
          {failureRows.length === 0 ? <p className="text-xs text-gray-400 py-6 text-center">No AI failures in this period.</p> : <RankedBars rows={failureRows} />}
        </Panel>
      </div>

      {/* Conversion (funnel) */}
      <Panel title="Conversion funnel" right={<ShoppingBag size={15} className="text-gray-300" />} lift>
        <Funnel conversion={conversion} />
      </Panel>

      {/* Agents */}
      {isStaffLead && agentData && agentData.agents?.length > 0 && (
        <Panel title="Agent performance" right={<Users size={15} className="text-gray-300" />} lift>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead>
                <tr className="border-b border-gray-100">
                  {['Agent', 'Active', 'Assigned', 'Resolved', 'Human replies', 'AI on theirs'].map((h, i) => (
                    <th key={h} className={clsx('py-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400', i === 0 ? 'text-left' : 'text-right')}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {agentData.agents.map((a) => {
                  const name = a.agent?.full_name || a.agent?.name || a.agent?.email || '—'
                  return (
                    <tr key={a.agent?.id || name} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/60 transition-colors">
                      <td className="py-3">
                        <div className="flex items-center gap-2.5">
                          <span className="w-7 h-7 rounded-full bg-gray-900 text-white text-[11px] font-semibold flex items-center justify-center shrink-0">{name.charAt(0).toUpperCase()}</span>
                          <span className="font-medium text-gray-800 truncate">{name}</span>
                        </div>
                      </td>
                      <td className="py-3 text-right tabular-nums text-gray-900 font-semibold">{a.active_total}</td>
                      <td className="py-3 text-right tabular-nums text-gray-600">{a.assigned_total}</td>
                      <td className="py-3 text-right tabular-nums text-gray-600">{a.resolved_in_window}</td>
                      <td className="py-3 text-right tabular-nums text-gray-600">{a.human_replies_in_window}</td>
                      <td className="py-3 text-right tabular-nums text-gray-600">{a.ai_replies_on_their_conversations}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  )
}
