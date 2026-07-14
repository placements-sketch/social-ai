import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  Users, Download, FileText, File, ExternalLink, ArrowUpRight, ArrowDownRight, Minus,
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

// ─────────────────────────────────────────────────────────────
// Small primitives — the shared design language
// ─────────────────────────────────────────────────────────────

// Uppercase micro-label used as an eyebrow everywhere.
function Eyebrow({ children, className }) {
  return (
    <span className={clsx('text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-400', className)}>
      {children}
    </span>
  )
}

// A ranked horizontal bar — the ONE breakdown treatment used across the page.
// First row gets the accent; the rest are graded grayscale. No rainbow.
function RankedBars({ rows, valueKey = 'value', labelKey = 'label', suffix = '', emptyText = 'No data in this period' }) {
  if (!rows || rows.length === 0) {
    return <p className="text-xs text-gray-400 py-6 text-center">{emptyText}</p>
  }
  const max = Math.max(...rows.map((r) => Number(r[valueKey]) || 0), 1)
  const grays = ['#3f3f46', '#52525b', '#71717a', '#a1a1aa', '#c4c4cc', '#d4d4d8']
  return (
    <div className="flex flex-col gap-3">
      {rows.map((r, i) => {
        const val = Number(r[valueKey]) || 0
        const pct = Math.round((val / max) * 100)
        const color = i === 0 ? ACCENT : grays[Math.min(i - 1, grays.length - 1)]
        return (
          <div key={r[labelKey] + i}>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-xs text-gray-600 truncate pr-3">{r[labelKey]}</span>
              <span className="text-xs font-bold text-gray-900 tabular-nums shrink-0">
                {val.toLocaleString()}{suffix}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
              <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// A raised panel with a hairline border — the page's only container shape.
function Panel({ title, right, children, className, bodyClass }) {
  return (
    <div className={clsx('bg-white border border-gray-200/80 rounded-2xl', className)}>
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

// Delta chip (vs previous window) — up = accent-ish green, down = gray, flat = muted.
function Delta({ current, previous, isPct = false }) {
  const cur = Number(current) || 0
  const prev = Number(previous) || 0
  const diff = isPct ? (cur - prev) * 100 : cur - prev
  const flat = Math.abs(diff) < (isPct ? 0.05 : 0.5)
  const Icon = flat ? Minus : diff > 0 ? ArrowUpRight : ArrowDownRight
  const val = isPct ? `${Math.abs(diff).toFixed(1)} pts` : Math.abs(Math.round(diff)).toLocaleString()
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs font-medium',
      flat ? 'text-gray-400' : diff > 0 ? 'text-emerald-600' : 'text-gray-500')}>
      <Icon size={14} />{val}
    </span>
  )
}

// Minimal tooltip for the trend chart.
function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 text-white rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="text-gray-300 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="font-semibold tabular-nums" style={{ color: p.color }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Hero band — the signature. Success rate as the dominant figure.
// ─────────────────────────────────────────────────────────────

function HeroBand({ kpis, periodLabel }) {
  const prev = kpis.previous || {}
  const successPct = (kpis.ai_success_rate || 0) * 100
  const animatedSuccess = useCountAnimation(successPct, 1600, true)

  const handled = kpis.ai_handled_total || 0
  const engaged = kpis.ai_engaged_total || 0

  const ms = kpis.avg_response_time_ms
  const avgStr = ms == null ? '—' : ms < 1 ? '<1ms' : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`

  const aiReplies = kpis.ai_replies_total || 0
  const overrides = kpis.human_override_total || 0
  const overrideRate = aiReplies > 0 ? ((overrides / aiReplies) * 100).toFixed(1) : '0.0'

  const strip = [
    { label: 'Avg response', value: avgStr },
    { label: 'Inbound', value: (kpis.inbound_total || 0).toLocaleString(), cur: kpis.inbound_total, prev: prev.inbound_total },
    { label: 'Escalated', value: (kpis.escalated_total || 0).toLocaleString(), cur: kpis.escalated_total, prev: prev.escalated_total },
    { label: 'Override rate', value: `${overrideRate}%` },
  ]

  return (
    <div className="bg-white border border-gray-200/80 rounded-2xl overflow-hidden">
      {/* Hero row */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 px-6 pt-5 pb-5 border-b border-gray-100">
        <div>
          <Eyebrow>AI performance · {periodLabel}</Eyebrow>
          <div className="flex items-baseline gap-2.5 mt-2.5">
            <span className="text-[52px] leading-none font-bold tabular-nums" style={{ color: ACCENT }}>
              {animatedSuccess.toFixed(1)}%
            </span>
            <span className="text-sm text-gray-500">success rate</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {engaged.toLocaleString()} of {handled.toLocaleString()} conversations handled and engaged
          </p>
        </div>
        <div className="text-left sm:text-right">
          <Eyebrow>vs {periodLabel === 'today' ? 'yesterday' : 'previous'}</Eyebrow>
          <div className="mt-1.5">
            <Delta current={kpis.ai_success_rate} previous={prev.ai_success_rate} isPct />
          </div>
        </div>
      </div>

      {/* Supporting strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-gray-100">
        {strip.map(({ label, value, cur, prev: p }, i) => (
          <div key={label} className={clsx('px-5 py-4', i >= 2 && 'border-t sm:border-t-0 border-gray-100')}>
            <p className="text-[22px] font-semibold text-gray-900 tabular-nums leading-none">{value}</p>
            <div className="flex items-center justify-between mt-2">
              <Eyebrow>{label}</Eyebrow>
              {cur != null && p != null && <Delta current={cur} previous={p} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────

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
      const analytics = await res.json()
      setData(analytics)

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
    return (
      <div className="bg-white border border-gray-200 rounded-2xl p-6 text-sm text-gray-700">
        {error}
      </div>
    )
  }
  if (!data) return null

  const { kpis, weekly, intent_breakdown, channel_split, top_products, failure_breakdown } = data

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

  // Conversion strip
  const conv = data.conversion || {}
  const convRows = [
    { label: 'Recommended', value: conv.recommended_conversations || 0 },
    { label: 'Converted', value: conv.converted_conversations || 0 },
    { label: 'Attributed orders', value: conv.attributed_orders || 0 },
  ]
  const convRate = ((conv.conversion_rate || 0) * 100).toFixed(1)
  const revenue = Math.round(conv.attributed_revenue || 0)

  // Failure labels
  const FAILURE_LABELS = {
    rate_limit: 'Rate limit hit', timeout: 'Timed out', auth: 'Auth error',
    bad_request: 'Bad request', api_error: 'Claude API error', network: 'Network error',
    bad_output: 'Malformed response', unknown: 'Unknown error',
  }
  const failureRows = (failure_breakdown || []).map((f) => ({ label: FAILURE_LABELS[f.reason] || f.reason, value: f.count }))

  const isStaffLead = user?.role === 'supervisor' || user?.role === 'admin'

  return (
    <div className="space-y-5 w-full px-0 lg:px-8 pb-10">
      {/* Header */}
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
                className={clsx(
                  'text-xs font-semibold px-3 py-1.5 rounded-md transition-colors',
                  days === range.days ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800'
                )}
              >
                {range.label}
              </button>
            ))}
          </div>
          <div className="relative">
            <button
              onClick={() => setExportOpen((o) => !o)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-900 text-white text-xs font-semibold hover:bg-black transition-colors"
            >
              <Download size={14} /><span>Export</span>
            </button>
            {exportOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setExportOpen(false)} />
                <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
                  <button onClick={() => { exportToCSV(); setExportOpen(false) }} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 first:rounded-t-lg">
                    <FileText size={13} /> Export as CSV
                  </button>
                  <button onClick={() => { exportToPDF(); setExportOpen(false) }} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 last:rounded-b-lg">
                    <File size={13} /> Export as PDF
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Hero band */}
      <HeroBand kpis={kpis} periodLabel={periodLabel} />

      {/* Trend */}
      <Panel title="Message volume" right={<Eyebrow>{periodLabel}</Eyebrow>} bodyClass="pt-4">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={weekly || []} barGap={4} barCategoryGap="22%" margin={{ top: 8, right: 4, left: -12, bottom: 0 }}>
            <XAxis dataKey="day" tick={{ fill: '#a1a1aa', fontSize: 11, fontFamily: 'Quicksand', fontWeight: 600 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#a1a1aa', fontSize: 11, fontFamily: 'Quicksand' }} axisLine={false} tickLine={false} width={40} />
            <Tooltip content={<TrendTooltip />} cursor={{ fill: 'rgba(0,0,0,0.03)' }} />
            <Bar dataKey="inbound" name="Inbound" fill="#e4e4e7" radius={[4, 4, 0, 0]} />
            <Bar dataKey="ai_replied" name="AI replied" fill={ACCENT} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-5 mt-3 pl-1">
          <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-2.5 h-2.5 rounded-sm bg-gray-200" />Inbound</span>
          <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: ACCENT }} />AI replied</span>
        </div>
      </Panel>

      {/* Breakdowns grid — all unified ranked bars */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Panel title="Top customer intents" right={<Eyebrow>volume</Eyebrow>}>
          <RankedBars rows={(intent_breakdown || []).map((it) => ({ label: it.name, value: it.count }))} emptyText="No intent data yet" />
        </Panel>

        <Panel title="Channels" right={<Eyebrow>messages</Eyebrow>}>
          <RankedBars rows={(channel_split || []).map((c) => ({ label: c.name, value: c.count }))} emptyText="No channel data yet" />
        </Panel>

        <Panel title="Most asked-about products" right={<Eyebrow>mentions</Eyebrow>}>
          <RankedBars rows={(top_products || []).map((p) => ({ label: p.name, value: p.mentions }))} emptyText="No product questions yet" />
        </Panel>

        <Panel title="AI failures by reason" right={<Eyebrow>count</Eyebrow>}>
          {failureRows.length === 0
            ? <p className="text-xs text-gray-400 py-6 text-center">No AI failures in this period.</p>
            : <RankedBars rows={failureRows} />}
        </Panel>
      </div>

      {/* Conversion */}
      <Panel title="Conversion" right={<Eyebrow>{periodLabel}</Eyebrow>}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="sm:col-span-2">
            <RankedBars rows={convRows} emptyText="No recommendations yet" />
          </div>
          <div className="flex sm:flex-col justify-between gap-4 sm:border-l sm:border-gray-100 sm:pl-6">
            <div>
              <p className="text-[28px] font-bold text-gray-900 tabular-nums leading-none">{convRate}%</p>
              <Eyebrow className="block mt-1.5">Conversion rate</Eyebrow>
            </div>
            <div>
              <p className="text-[22px] font-semibold text-gray-900 tabular-nums leading-none">
                <span className="text-sm text-gray-400 font-medium">KES </span>{revenue.toLocaleString()}
              </p>
              <Eyebrow className="block mt-1.5">Attributed revenue</Eyebrow>
            </div>
          </div>
        </div>
      </Panel>

      {/* Agent performance — supervisor + admin only */}
      {isStaffLead && agentData && agentData.agents?.length > 0 && (
        <Panel title="Agent performance" right={<span className="inline-flex items-center gap-1.5 text-gray-400"><Users size={14} /></span>}>
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
                  const initial = name.charAt(0).toUpperCase()
                  return (
                    <tr key={a.agent?.id || name} className="border-b border-gray-50 last:border-0">
                      <td className="py-3">
                        <div className="flex items-center gap-2.5">
                          <span className="w-7 h-7 rounded-full bg-gray-900 text-white text-[11px] font-semibold flex items-center justify-center shrink-0">{initial}</span>
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
