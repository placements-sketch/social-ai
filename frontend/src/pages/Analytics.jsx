import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  Users, Download, FileText, File, Bolt, MessageSquare, ArrowUpRight, UserCheck,
  TrendingUp, TrendingDown, Minus, Bot, ShoppingBag, AlertTriangle, Radio, Package,
} from 'lucide-react'
import { SkeletonAnalytics } from '../components/Skeleton'
import { useAuth } from '../context/AuthContext'
import { useCountAnimation } from '../hooks/useCountAnimation'
import clsx from 'clsx'
import { exportAnalyticsCSV, exportAnalyticsPDF } from '../utils/reportExport'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const ACCENT = '#ff5900'

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
    : isPercent
      ? (value || 0) * 100
      : (value || 0)
  const animated = useCountAnimation(numeric, 1600, isPercent || isTime)

  let display
  if (isTime) {
    display = value == null ? '—' : value < 1 ? '<1ms' : value < 1000 ? `${value}ms` : `${animated.toFixed(1)}s`
  } else if (isPercent) {
    display = `${animated.toFixed(1)}%`
  } else {
    display = Math.round(animated).toLocaleString()
  }

  return (
    <div
      className="bg-white border border-gray-200/70 rounded-2xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-gray-300"
      style={{ boxShadow: SHADOW, animation: 'an-rise .5s ease both', animationDelay: `${delay}ms` }}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="w-8 h-8 rounded-[10px] bg-gray-100 flex items-center justify-center text-gray-500">
          <Icon size={16} />
        </span>
        {current != null && previous != null && <Delta current={current} previous={previous} />}
      </div>
      <p className="text-[23px] font-bold text-gray-900 tabular-nums leading-none tracking-tight">{display}</p>
      <Eyebrow className="block mt-1.5">{label}</Eyebrow>
    </div>
  )
}

function RankedBars({ rows, suffix = '', emptyText = 'No data in this period' }) {
  if (!rows || rows.length === 0) {
    return <p className="text-xs text-gray-400 py-6 text-center">{emptyText}</p>
  }
  const max = Math.max(...rows.map((r) => Number(r.value) || 0), 1)
  const grays = ['#3f3f46', '#52525b', '#71717a', '#a1a1aa', '#c4c4cc', '#d4d4d8']
  return (
    <div className="flex flex-col gap-3.5">
      {rows.map((r, i) => {
        const val = Number(r.value) || 0
        const pct = Math.round((val / max) * 100)
        const color = i === 0 ? ACCENT : grays[Math.min(i - 1, grays.length - 1)]
        return (
          <div key={r.label + i}>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-xs text-gray-600 truncate pr-3">{r.label}</span>
              <span className="text-xs font-bold text-gray-900 tabular-nums shrink-0">{val.toLocaleString()}{suffix}</span>
            </div>
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${pct}%`, background: color, transition: 'width .9s cubic-bezier(0.16,1,0.3,1)', transitionDelay: `${i * 60}ms` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 text-white rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="text-gray-300 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="font-semibold tabular-nums" style={{ color: p.color }}>{p.name}: {p.value}</p>
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

  const diff = (kpis.ai_success_rate || 0) * 100 - (prev.ai_success_rate || 0) * 100
  const up = diff >= 0

  return (
    <div
      className="rounded-2xl px-6 py-5"
      style={{
        border: '0.5px solid rgba(255,89,0,0.18)',
        background: 'linear-gradient(135deg, #fff8f4 0%, #ffffff 62%)',
        boxShadow: '0 1px 2px rgba(16,24,40,0.04), 0 12px 32px -14px rgba(255,89,0,0.18)',
      }}
    >
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
          <p className="text-xs text-gray-400 mt-2.5">
            {engaged.toLocaleString()} of {handled.toLocaleString()} conversations handled &amp; engaged
          </p>
        </div>

        <div className="flex items-end gap-1 h-16 pt-1" aria-hidden="true">
          {series.length > 0 ? series.map((v, i) => {
            const h = Math.max(6, Math.round((v / sMax) * 56))
            const isLast = i >= series.length - 2
            return (
              <div
                key={i}
                style={{
                  width: 13, height: h, borderRadius: 3,
                  background: isLast ? ACCENT : `rgba(255,89,0,${0.22 + (i / series.length) * 0.5})`,
                  transformOrigin: 'bottom',
                  animation: 'an-grow .6s ease both',
                  animationDelay: `${i * 40}ms`,
                }}
              />
            )
          }) : null}
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
    setLoading(true)
    setError(null)
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
        } catch (err) {
          console.error('Failed to load agent data:', err)
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <SkeletonAnalytics />
  if (error) {
    return <div className="bg-white border border-gray-200 rounded-2xl p-6 text-sm text-gray-700" style={{ boxShadow: SHADOW }}>{error}</div>
  }
  if (!data) return null

  const { kpis, weekly, intent_breakdown, channel_split, top_products, failure_breakdown } = data
  const prev = kpis.previous || {}

  const periodLabel = days === 1 ? 'today' : days === 7 ? 'last 7 days' : days === 30 ? 'last 30 days' : `last ${days} days`

  const getSubtitle = () => {
    if (user?.role === 'agent') return 'Performance across your assigned conversations'
    if (user?.role === 'supervisor') return 'Company overview and agent performance'
    return 'Company-wide AI support analytics'
  }

  const exportMeta = () => ({
    periodLabel: DATE_RANGES.find((r) => r.days === days)?.label || `Last ${days} days`,
    generatedAt: new Date().toLocaleString(),
    periodSlug: `${days}d`,
    dateSlug: new Date().toISOString().split('T')[0],
  })
  const reportData = () => ({ ...data, agents: agentData?.agents || [] })
  const exportToCSV = () => exportAnalyticsCSV(reportData(), exportMeta())
  const exportToPDF = () => exportAnalyticsPDF(reportData(), exportMeta())

  const aiReplies = kpis.ai_replies_total || 0
  const overrideRate = aiReplies > 0 ? (kpis.human_override_total || 0) / aiReplies : 0

  const conv = data.conversion || {}
  const convRows = [
    { label: 'Recommended', value: conv.recommended_conversations || 0 },
    { label: 'Converted', value: conv.converted_conversations || 0 },
    { label: 'Attributed orders', value: conv.attributed_orders || 0 },
  ]
  const convRate = ((conv.conversion_rate || 0) * 100).toFixed(1)
  const revenue = Math.round(conv.attributed_revenue || 0)

  const FAILURE_LABELS = {
    rate_limit: 'Rate limit hit', timeout: 'Timed out', auth: 'Auth error',
    bad_request: 'Bad request', api_error: 'Claude API error', network: 'Network error',
    bad_output: 'Malformed response', unknown: 'Unknown error',
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
              <button
                key={range.days}
                onClick={() => setDays(range.days)}
                className={clsx('text-xs font-semibold px-3 py-1.5 rounded-md transition-all',
                  days === range.days ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800')}
              >
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

      <Panel title="Message volume" right={<Eyebrow>{periodLabel}</Eyebrow>} bodyClass="pt-4" lift>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={weekly || []} barGap={4} barCategoryGap="22%" margin={{ top: 8, right: 4, left: -14, bottom: 0 }}>
            <XAxis dataKey="day" tick={{ fill: '#a1a1aa', fontSize: 11, fontFamily: 'Quicksand', fontWeight: 600 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#a1a1aa', fontSize: 11, fontFamily: 'Quicksand' }} axisLine={false} tickLine={false} width={40} />
            <Tooltip content={<TrendTooltip />} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
            <Bar dataKey="inbound" name="Inbound" fill="#e4e4e7" radius={[5, 5, 0, 0]} />
            <Bar dataKey="ai_replied" name="AI replied" fill={ACCENT} radius={[5, 5, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-5 mt-3 pl-1">
          <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-2.5 h-2.5 rounded-sm bg-gray-200" />Inbound</span>
          <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: ACCENT }} />AI replied</span>
        </div>
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Top customer intents" right={<Bot size={15} className="text-gray-300" />} lift>
          <RankedBars rows={(intent_breakdown || []).map((it) => ({ label: it.name, value: it.count }))} emptyText="No intent data yet" />
        </Panel>
        <Panel title="Channels" right={<Radio size={15} className="text-gray-300" />} lift>
          <RankedBars rows={(channel_split || []).map((c) => ({ label: c.name, value: c.count }))} emptyText="No channel data yet" />
        </Panel>
        <Panel title="Most asked-about products" right={<Package size={15} className="text-gray-300" />} lift>
          <RankedBars rows={(top_products || []).map((p) => ({ label: p.name, value: p.mentions }))} emptyText="No product questions yet" />
        </Panel>
        <Panel title="AI failures by reason" right={<AlertTriangle size={15} className="text-gray-300" />} lift>
          {failureRows.length === 0
            ? <p className="text-xs text-gray-400 py-6 text-center">No AI failures in this period.</p>
            : <RankedBars rows={failureRows} />}
        </Panel>
      </div>

      <Panel title="Conversion" right={<ShoppingBag size={15} className="text-gray-300" />} lift>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="sm:col-span-2"><RankedBars rows={convRows} emptyText="No recommendations yet" /></div>
          <div className="flex sm:flex-col justify-between gap-4 sm:border-l sm:border-gray-100 sm:pl-6">
            <div>
              <p className="text-[28px] font-bold tabular-nums leading-none" style={{ color: ACCENT }}>{convRate}%</p>
              <Eyebrow className="block mt-1.5">Conversion rate</Eyebrow>
            </div>
            <div>
              <p className="text-[22px] font-bold text-gray-900 tabular-nums leading-none">
                <span className="text-sm text-gray-400 font-medium">KES </span>{revenue.toLocaleString()}
              </p>
              <Eyebrow className="block mt-1.5">Attributed revenue</Eyebrow>
            </div>
          </div>
        </div>
      </Panel>

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
