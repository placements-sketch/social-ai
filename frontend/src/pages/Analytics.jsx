import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { useState, useEffect } from 'react'
import { Loader2, Calendar, TrendingUp, Users, CheckCircle2, MessageSquare, Download, FileText, File, Sheet } from 'lucide-react'
import { SkeletonAnalytics } from '../components/Skeleton'
import { useAuth } from '../context/AuthContext'
import clsx from 'clsx'

// Brand palette for charts
const BRAND_COLORS  = ['#ff5900', '#ff7733', '#ff9966', '#ffbb99', '#ffddcc', '#fff0e8']
const CHANNEL_COLORS = ['#ec4899', '#22c55e', '#f97316', '#1877F2', '#60a5fa', '#000000']

const DATE_RANGES = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-3 py-2 text-xs shadow-card">
      {label && <p className="text-gray-500 font-semibold mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="font-bold">
          {p.name}: {p.value}
        </p>
      ))}
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

  useEffect(() => {
    fetchAnalytics()
  }, [days])

  const fetchAnalytics = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/analytics/summary?days=${days}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load analytics')
      const analytics = await res.json()
      setData(analytics)

      // Fetch agent breakdown if user is supervisor or admin
      if (user?.role === 'supervisor' || user?.role === 'admin') {
        try {
          const agentRes = await fetch(`/api/analytics/agents?days=${days}`, {
            headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
          })
          if (agentRes.ok) {
            const agents = await agentRes.json()
            setAgentData(agents)
          }
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

  if (loading) {
    return <SkeletonAnalytics />
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-600">
        {error}
      </div>
    )
  }

  if (!data) return null

  const { kpis, weekly, intent_breakdown, channel_split, top_products } = data

  // Format KPI values
  const formatTime = (ms) => ms ? `${(ms / 1000).toFixed(1)}s` : '—'
  const formatPercent = (val) => `${(val * 100).toFixed(1)}%`

  // Role-specific subtitle
  const getSubtitle = () => {
    if (user?.role === 'agent') return 'Your assigned conversations performance'
    if (user?.role === 'supervisor') return 'Company overview and agent performance metrics'
    return 'Company-wide AI support analytics'
  }

  // Export functions
  const exportToCSV = () => {
    const headers = ['Metric', 'Value']
    const rows = [
      ['Avg Response Time (ms)', kpis.avg_response_time_ms],
      ['AI Success Rate', `${(kpis.ai_success_rate * 100).toFixed(1)}%`],
      ['Override Rate', `${(kpis.override_rate * 100).toFixed(1)}%`],
      ['Total Messages', kpis.total_messages],
      ['AI Replied', kpis.ai_replied],
      ['Human Overrides', kpis.human_overrides],
      ...weekly.map(w => [`${w.day} - Inbound`, w.inbound]),
      ...weekly.map(w => [`${w.day} - AI Replied`, w.ai_replied]),
    ]
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `analytics-export-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  const exportToPDF = async () => {
    const { jsPDF } = await import('jspdf')
    const { autoTable } = await import('jspdf-autotable')
    
    const doc = new jsPDF()
    const headers = ['Metric', 'Value']
    const rows = [
      ['Avg Response Time (ms)', kpis.avg_response_time_ms],
      ['AI Success Rate', `${(kpis.ai_success_rate * 100).toFixed(1)}%`],
      ['Override Rate', `${(kpis.override_rate * 100).toFixed(1)}%`],
      ['Total Messages', kpis.total_messages],
      ['AI Replied', kpis.ai_replied],
      ['Human Overrides', kpis.human_overrides],
    ]
    
    autoTable(doc, {
      head: [headers],
      body: rows,
      startY: 20,
      styles: { fontSize: 9, cellPadding: 3 },
      headStyles: { fillColor: [0, 0, 0], textColor: [255, 255, 255] },
    })
    
    doc.save(`analytics-export-${new Date().toISOString().split('T')[0]}.pdf`)
  }

  return (
    <div className="space-y-6 w-full px-0 md:px-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="text-sm text-gray-500 mt-0.5">{getSubtitle()}</p>
        </div>
        
        <div className="flex items-center gap-2">
          {/* Date range filter */}
          <div className="flex gap-2">
            {DATE_RANGES.map((range) => (
              <button
                key={range.days}
                onClick={() => setDays(range.days)}
                className={clsx(
                  'text-xs font-semibold px-3 py-2 rounded-lg border transition-colors',
                  days === range.days
                    ? 'bg-black text-white border-black'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                )}
              >
                {range.label}
              </button>
            ))}
          </div>

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
              <button onClick={exportToPDF} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 last:rounded-b-lg">
                <File size={13} />
                Export as PDF
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: 'Avg Response Time', value: formatTime(kpis.avg_response_time_ms), color: 'text-green-600'  },
          { label: 'AI Success Rate',   value: formatPercent(kpis.ai_success_rate),      color: 'text-brand-500' },
          { label: 'Override Rate',     value: formatPercent(kpis.override_rate),     color: 'text-amber-500' },
        ].map(k => (
          <div key={k.label} className="stat-card text-center">
            <p className={`text-4xl font-bold ${k.color}`}>{k.value}</p>
            <p className="text-xs text-gray-500 font-semibold mt-1">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Weekly bar chart */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4">
          Messages Last {days} {days === 1 ? 'Day' : 'Days'}
        </h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={weekly} barGap={4} barCategoryGap="15%">
            <XAxis dataKey="day" tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'Quicksand', fontWeight: 600 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'Quicksand' }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12, fontFamily: 'Quicksand', fontWeight: 600 }} />
            <Bar dataKey="inbound" name="Inbound"    fill="#e5e7eb" radius={[8,8,0,0]} />
            <Bar dataKey="ai_replied"  name="AI Replied" fill="#ff5900" radius={[8,8,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Intent breakdown */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Top Customer Intents</h2>
          {intent_breakdown && intent_breakdown.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={intent_breakdown} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="count">
                    {intent_breakdown.map((_, i) => <Cell key={i} fill={BRAND_COLORS[i % BRAND_COLORS.length]} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {intent_breakdown.map((item, i) => (
                  <div key={item.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ background: BRAND_COLORS[i] }} />
                      <span className="text-gray-600 font-medium">{item.name}</span>
                    </div>
                    <span className="text-gray-900 font-bold">{item.percent}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-center text-xs text-gray-400 py-8">No intent data available</p>
          )}
        </div>

        {/* Channel split */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Channel Split</h2>
          {channel_split && channel_split.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={channel_split} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="count">
                    {channel_split.map((_, i) => <Cell key={i} fill={CHANNEL_COLORS[i % CHANNEL_COLORS.length]} />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5 mt-2">
                {channel_split.map((item, i) => (
                  <div key={item.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ background: CHANNEL_COLORS[i % CHANNEL_COLORS.length] }} />
                      <span className="text-gray-600 font-medium capitalize">{item.name.replace(/_/g, ' ')}</span>
                    </div>
                    <span className="text-gray-900 font-bold">{item.percent}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-center text-xs text-gray-400 py-8">No channel data available</p>
          )}
        </div>
      </div>

      {/* Top products section */}
      {top_products && top_products.length > 0 && (
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Top Products Mentioned</h2>
          <div className="space-y-3">
            {top_products.map((product, i) => (
              <div key={product.name} className="flex items-center gap-3">
                <span className="text-xs font-bold text-gray-400 w-4">{i + 1}</span>
                <div className="flex-1">
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-gray-800 font-semibold">{product.name}</span>
                    <span className="text-gray-500 font-medium">{product.mentions} mentions</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-500 rounded-full transition-all"
                      style={{ width: `${(product.mentions / top_products[0].mentions) * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="stat-card">
          <p className="text-xs text-gray-500 font-semibold">Total Messages</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{kpis.messages_total}</p>
          <p className="text-xs text-gray-400 mt-1">{kpis.inbound_total} inbound</p>
        </div>
        <div className="stat-card">
          <p className="text-xs text-gray-500 font-semibold">AI vs Human Replies</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{kpis.ai_replies_total} / {kpis.human_replies_total}</p>
          <p className="text-xs text-gray-400 mt-1">AI / Manual responses</p>
        </div>
        <div className="stat-card">
          <p className="text-xs text-gray-500 font-semibold">Total Conversations</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{kpis.conversations_total}</p>
          <p className="text-xs text-gray-400 mt-1">{kpis.human_override_total} overridden</p>
        </div>
      </div>

      {/* Agent Performance — Supervisor & Admin only */}
      {(user?.role === 'supervisor' || user?.role === 'admin') && agentData && agentData.agents.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Users size={18} className="text-gray-600" />
            <h2 className="text-sm font-bold text-gray-900">Agent Performance</h2>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 px-3 text-gray-500 font-semibold">Agent</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-semibold">Active</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-semibold">Assigned</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-semibold">Resolved</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-semibold">Human Replies</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-semibold">AI Replies on Their Convs</th>
                </tr>
              </thead>
              <tbody>
                {agentData.agents.map((agent) => (
                  <tr key={agent.agent.id} className="border-b border-gray-100 hover:bg-gray-50 transition">
                    <td className="py-2.5 px-3">
                      <div>
                        <p className="font-semibold text-gray-900">{agent.agent.full_name}</p>
                        <p className="text-gray-400 text-[10px]">{agent.agent.email}</p>
                      </div>
                    </td>
                    <td className="text-right py-2.5 px-3">
                      <span className="inline-flex items-center gap-1 bg-blue-50 text-blue-600 font-bold px-2 py-1 rounded-md">
                        <MessageSquare size={12} />
                        {agent.active_total}
                      </span>
                    </td>
                    <td className="text-right py-2.5 px-3 text-gray-700 font-bold">{agent.assigned_total}</td>
                    <td className="text-right py-2.5 px-3">
                      <span className="inline-flex items-center gap-1 bg-green-50 text-green-600 font-bold px-2 py-1 rounded-md">
                        <CheckCircle2 size={12} />
                        {agent.resolved_in_window}
                      </span>
                    </td>
                    <td className="text-right py-2.5 px-3 text-gray-700 font-bold">{agent.human_replies_in_window}</td>
                    <td className="text-right py-2.5 px-3">
                      <span className="inline-flex items-center gap-1 bg-brand-50 text-brand-600 font-bold px-2 py-1 rounded-md">
                        <TrendingUp size={12} />
                        {agent.ai_replies_on_their_conversations}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
