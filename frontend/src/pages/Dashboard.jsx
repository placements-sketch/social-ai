import { stats, activityFeed, alerts } from '../data/mock'
import {
  MessageSquare, Bot, UserCheck, XCircle, PackageX,
  AlertTriangle, AlertCircle, Info, Instagram, Smartphone, ShoppingBag, TrendingUp,
  Download, FileText, File, Calendar, Clock, TrendingUp as ChartTrendingUp, ChevronDown, X,
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import clsx from 'clsx'
import { useState, useEffect } from 'react'
import { getAnalyticsSummary, getSystemLogs, getMyLogs } from '../api/dashboard'
import { SkeletonCard } from '../components/Skeleton'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { useTimeAgo } from '../hooks/useTimeAgo'

// Custom tooltip to ensure text is visible
const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        background: '#000000',
        border: 'none',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        padding: '8px 12px'
      }}>
        {payload.map((entry, idx) => {
          const isTikTok = entry.name.includes('TikTok')
          return (
            <p key={idx} style={{ color: isTikTok ? '#ffffff' : (entry.color || '#ffffff'), fontSize: 10, fontFamily: 'Quicksand', margin: '2px 0' }}>
              {entry.name}: <span style={{ fontWeight: 'bold' }}>{entry.value}</span>
            </p>
          )
        })}
      </div>
    )
  }
  return null
}

const statCards = [
  { label: 'Messages Today',       value: stats.messagesToday,      icon: MessageSquare, color: 'text-blue-500',    bg: 'bg-blue-50'        },
  { label: 'Auto-Replies Sent',    value: stats.autoRepliesSent,    icon: Bot,           color: 'text-brand-500',   bg: 'bg-brand-50'       },
  { label: 'Human Overrides',      value: stats.humanOverrides,     icon: UserCheck,     color: 'text-amber-500',   bg: 'bg-amber-50'       },
  { label: 'Failed Responses',     value: stats.failedResponses,    icon: XCircle,       color: 'text-red-500',     bg: 'bg-red-50'         },
  { label: 'Out-of-Stock Queries', value: stats.outOfStockQueries,  icon: PackageX,      color: 'text-orange-500',  bg: 'bg-orange-50'      },
  { label: 'Escalated',            value: 12,                       icon: TrendingUp,    color: 'text-purple-500',  bg: 'bg-purple-50'      },
]

const alertStyles = {
  error:   { icon: AlertCircle,   cls: 'border-red-200 bg-red-50 text-red-600'       },
  warning: { icon: AlertTriangle, cls: 'border-amber-200 bg-amber-50 text-amber-600' },
  info:    { icon: Info,          cls: 'border-blue-200 bg-blue-50 text-blue-600'    },
}

const channelIcon = (ch) => {
  if (ch === 'instagram_dm' || ch === 'instagram_comment') return <Instagram size={13} className="text-pink-500" />
  if (ch === 'whatsapp')       return <Smartphone size={13} className="text-green-500" />
  if (ch === 'facebook_dm' || ch === 'facebook_comment')
    return <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded text-white font-black text-[9px]" style={{ background: '#1877F2' }}>f</span>
  if (ch === 'tiktok_dm' || ch === 'tiktok_comment')
    return <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded font-black text-[9px]" style={{ background: '#000000', color: '#ffffff' }}>♪</span>
  if (ch === 'shopify')        return <ShoppingBag size={13} className="text-emerald-500" />
  if (ch === 'alert')          return <AlertTriangle size={13} className="text-amber-500" />
  return <Bot size={13} className="text-brand-500" />
}

// Separate component for activity item to use the useTimeAgo hook
function ActivityItem({ item }) {
  const timeAgoStr = useTimeAgo(item.created_at)
  
  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0">
      <div className="mt-0.5 shrink-0 w-5 h-5 rounded-lg bg-gray-50 flex items-center justify-center flex-shrink-0">
        {channelIcon(item.channel)}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 leading-relaxed">{item.text}</p>
      </div>
      <span className="text-xs text-gray-400 shrink-0 font-medium whitespace-nowrap ml-2">{timeAgoStr}</span>
    </div>
  )
}

export default function Dashboard() {
  const [analyticsData, setAnalyticsData] = useState(null)
  const [systemAlerts, setSystemAlerts] = useState([])
  const [activityLogs, setActivityLogs] = useState([])
  const [loadingAnalytics, setLoadingAnalytics] = useState(true)
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [loadingActivity, setLoadingActivity] = useState(true)
  const [showChannelModal, setShowChannelModal] = useState(false)

  const [period, setPeriod] = useState('month')  // 'today' | 'week' | 'month'

  const PERIOD_DAYS = { today: 1, week: 7, month: 30 }
  const PERIOD_LABELS = { today: 'Today', week: 'This week', month: 'This month' }
  const PREVIOUS_LABELS = { today: 'yesterday', week: 'last week', month: 'last month' }

  // Load analytics summary
  useEffect(() => {
    const load = async () => {
      setLoadingAnalytics(true)
      try {
        const data = await getAnalyticsSummary({ days: PERIOD_DAYS[period] })
        setAnalyticsData(data)
      } catch (err) {
        console.error('Failed to load analytics:', err)
        // Fall back to dummy data
      } finally {
        setLoadingAnalytics(false)
      }
    }
    load()
  }, [period])

  // Load system alerts
  useEffect(() => {
    const load = async () => {
      setLoadingAlerts(true)
      try {
        const data = await getSystemLogs({ per_page: 5 })
        setSystemAlerts(data.logs || [])
      } catch (err) {
        console.error('Failed to load system alerts:', err)
      } finally {
        setLoadingAlerts(false)
      }
    }
    load()
  }, [])

  // Load activity feed
  useEffect(() => {
    const load = async () => {
      setLoadingActivity(true)
      try {
        const data = await getMyLogs({ per_page: 10 })
        setActivityLogs(data.logs || [])
      } catch (err) {
        console.error('Failed to load activity logs:', err)
      } finally {
        setLoadingActivity(false)
      }
    }
    load()
  }, [])

// Stat card definitions — same for empty + populated; the render block
  // reads kpiKey from analyticsData.kpis directly.
  const getStatCards = () => [
    { label: 'Messages',        kpiKey: 'messages_total',       icon: MessageSquare, color: 'text-blue-500',   bg: 'bg-blue-50'   },
    { label: 'AI Replies',      kpiKey: 'ai_replies_total',     icon: Bot,           color: 'text-brand-500',  bg: 'bg-brand-50'  },
    { label: 'Human Overrides', kpiKey: 'human_override_total', icon: UserCheck,     color: 'text-amber-500',  bg: 'bg-amber-50'  },
    { label: 'Failed Replies',  kpiKey: 'failed_responses',     icon: XCircle,       color: 'text-red-500',    bg: 'bg-red-50'    },
    { label: 'Escalated',       kpiKey: 'escalated_total',      icon: TrendingUp,    color: 'text-purple-500', bg: 'bg-purple-50' },
    { label: 'AI Success Rate', kpiKey: 'ai_success_rate',      icon: PackageX,      color: 'text-green-500',  bg: 'bg-green-50', isPercentage: true },
  ]

  // Map system logs to alert format
  const getSystemAlerts = () => {
    if (systemAlerts.length > 0) {
      return systemAlerts.slice(0, 3).map(log => ({
        id: log.id,
        level: log.level || 'info',
        message: log.message || 'System event',
      }))
    }
    // Fallback to mock data
    return alerts
  }

  // Compose a human-readable line from a log row.
// Compose a natural-language sentence from a structured log row.
  const formatActivityText = (log) => {
    const src = (log.source || '').toLowerCase()
    const p = log.payload || {}

    const chanName = ({
      instagram_dm:      'Instagram DM',
      instagram_comment: 'Instagram comment',
      whatsapp:          'WhatsApp',
      facebook_dm:       'Facebook DM',
      facebook_comment:  'Facebook comment',
      tiktok_dm:         'TikTok DM',
      tiktok_comment:    'TikTok comment',
    })[p.channel] || p.channel

    const userRef = p.user_external_id
      ? `@${p.user_external_id}`
      : (p.handle ? `@${p.handle}` : 'a customer')

    // ── Inbound message
    if (src === 'services.inbound') {
      return `${userRef} sent a message on ${chanName || 'an unknown channel'}${p.preview ? `: "${p.preview.slice(0, 60)}${p.preview.length > 60 ? '…' : ''}"` : ''}`
    }

    // ── AI reply
    if (src === 'services.ai_reply') {
      return `AI responded via ${chanName} to ${userRef}`
    }

    // ── Intents detected
    if (src === 'services.intents') {
      const list = (p.intents || []).join(', ')
      return `Detected intents: ${list || 'unknown'} for ${userRef}`
    }

    // ── Template reply used
    if (src === 'services.template_reply') {
      return `Template reply sent to ${userRef} on ${chanName}`
    }

    // ── AI suppressed
    if (src === 'services.ai_suppressed') {
      return `AI gated off for ${userRef} on ${chanName}`
    }

    // ── Shopify product lookup
    if (src === 'services.shopify_lookup') {
      const stock = p.stock_quantity
      const stockStr = stock == null ? 'untracked' : `${stock} units`
      return `Shopify stock checked: ${p.product_name || p.product_keyword} — ${stockStr}`
    }

    // ── Shopify sync
    if (src === 'integrations.shopify.sync') {
      return `Shopify sync completed — ${p.count || 0} ${p.kind || 'records'} updated`
    }

    // ── Shopify token
    if (src === 'integrations.shopify.token') {
      return `Shopify access token refreshed`
    }

    // ── Handoff
    if (src === 'handoff.triggered') {
      return `Conversation handed off to human — ${p.reason || 'rule'}${p.detail ? `: "${p.detail}"` : ''}`
    }
    if (src === 'handoff.auto_assign') {
      return `Auto-assigned to ${p.agent_name || p.agent_email}${p.reason ? ` (${p.reason})` : ''}`
    }

    // ── Manual assignment
    if (src === 'assignment.assigned') {
      const verb = p.is_reassign ? 'reassigned' : 'assigned'
      return `Conversation ${verb} to ${p.agent_name || p.agent_email}`
    }
    if (src === 'assignment.unassigned') {
      return `Conversation unassigned`
    }

    // ── AI failure
    if (src === 'ai.generator.failure') {
      return `Claude API call failed — fell back to mock reply`
    }

    // Fallback to the raw message (cleaned up)
    if (log.message) {
      return log.message.replace(/^\[(MOCK|DEBUG|INFO|TEST)\]\s*/i, '')
    }
    return log.source ? `${log.source} event` : 'System activity'
  }

  const getActivityFeed = () => {
    if (activityLogs.length === 0) {
      // Fallback to mock so the section isn't empty during early dev
      return activityFeed
    }
    // Poller logs are now filtered on the backend via ?exclude_pollers=true
    
    return activityLogs.slice(0, 12).map(log => {
      // Prefer payload.channel (now richly populated); fall back to source-based guess.
      const src = (log.source || '').toLowerCase()
      let iconChannel = 'system'
      if (log.payload?.channel) iconChannel = log.payload.channel
      else if (src.includes('shopify')) iconChannel = 'shopify'
      else if (src.includes('handoff') || src.includes('assignment')) iconChannel = 'alert'
      else if (src.includes('meta')) iconChannel = 'instagram_dm'
      else if (src.includes('ai')) iconChannel = 'system'

      return {
        id: log.id,
        text: formatActivityText(log),
        channel: iconChannel,
        created_at: log.created_at, // Pass timestamp, component will handle formatting
      }
    })
  }

  const statCardsData = getStatCards()
  const systemAlertsData = getSystemAlerts()
  const activityFeedData = getActivityFeed()

  // Real channel totals from analytics, scoped to the selected period.
  const channelSplit = analyticsData?.channel_split || []
  const channelStats = [
    { label: 'Instagram', value: channelSplit.filter(c => c.name.includes('instagram')).reduce((s, c) => s + c.count, 0) },
    { label: 'WhatsApp',  value: channelSplit.find(c => c.name === 'whatsapp')?.count || 0 },
    { label: 'Facebook',  value: channelSplit.filter(c => c.name.includes('facebook')).reduce((s, c) => s + c.count, 0) },
    { label: 'TikTok',    value: channelSplit.filter(c => c.name.includes('tiktok')).reduce((s, c) => s + c.count, 0) },
  ]

 // Real per-channel-per-day data from analytics.weekly
  const weekly = analyticsData?.weekly || []
// Trim leading days where nothing happened so the chart doesn't waste space
  const firstActiveIdx = weekly.findIndex(w =>
    (w.instagram || 0) + (w.whatsapp || 0) + (w.facebook || 0) + (w.tiktok || 0) > 0
  )
  const trimmedWeekly = firstActiveIdx === -1 ? weekly : weekly.slice(firstActiveIdx)

  const chartData = trimmedWeekly.map(w => ({
    time: period === 'month'
      ? new Date(w.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : w.day,
    // Instagram
    instagram: w.instagram || 0,
    instagram_ai: w.instagram_ai || 0,
    instagram_human: w.instagram_human || 0,
    // WhatsApp
    whatsapp: w.whatsapp || 0,
    whatsapp_ai: w.whatsapp_ai || 0,
    whatsapp_human: w.whatsapp_human || 0,
    // Facebook
    facebook: w.facebook || 0,
    facebook_ai: w.facebook_ai || 0,
    facebook_human: w.facebook_human || 0,
    // TikTok
    tiktok: w.tiktok || 0,
    tiktok_ai: w.tiktok_ai || 0,
    tiktok_human: w.tiktok_human || 0,
  }))

  const exportToCSV = () => {
    const headers = ['Metric', 'Value']
    const kpis = analyticsData?.kpis || {}
    const rows = [
      ['Total Messages', kpis.messages_total || stats.messagesToday],
      ['AI Replies', kpis.ai_replies_total || stats.autoRepliesSent],
      ['Human Overrides', kpis.human_override_total || stats.humanOverrides],
      ['Success Rate', `${((kpis.ai_success_rate || 0) * 100).toFixed(1)}%`],
      ['Conversations', kpis.conversations_total || 0],
    ]
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `dashboard-export-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  }

  const exportToPDF = async () => {
    const { jsPDF } = await import('jspdf')
    const { autoTable } = await import('jspdf-autotable')
    
    const doc = new jsPDF()
    const headers = ['Metric', 'Value']
    const kpis = analyticsData?.kpis || {}
    const rows = [
      ['Total Messages', kpis.messages_total || stats.messagesToday],
      ['AI Replies', kpis.ai_replies_total || stats.autoRepliesSent],
      ['Human Overrides', kpis.human_override_total || stats.humanOverrides],
      ['Success Rate', `${((kpis.ai_success_rate || 0) * 100).toFixed(1)}%`],
      ['Conversations', kpis.conversations_total || 0],
    ]
    
    autoTable(doc, {
      head: [headers],
      body: rows,
      startY: 20,
      styles: { fontSize: 9, cellPadding: 3 },
      headStyles: { fillColor: [0, 0, 0], textColor: [255, 255, 255] },
    })
    
    doc.save(`dashboard-export-${new Date().toISOString().split('T')[0]}.pdf`)
  }

  return (
    <div className="space-y-6 w-full">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Live overview of your AI support system</p>
        </div>
        
        {/* Period filters + Export */}
        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          {/* Desktop: Button group */}
          <div className="hidden sm:flex items-center gap-1.5 bg-white border border-gray-200 rounded-xl p-1.5 shadow-sm">
            {[
              { key: 'today', label: 'Today', icon: Clock },
              { key: 'week', label: 'This week', icon: Calendar },
              { key: 'month', label: 'This month', icon: ChartTrendingUp },
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setPeriod(key)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                  period === key
                    ? 'bg-black text-white shadow-md'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                )}
              >
                <Icon size={14} />
                <span>{label}</span>
              </button>
            ))}
          </div>

          {/* Mobile: Dropdown */}
          <div className="sm:hidden relative group">
            <button className="flex items-center gap-2 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors shadow-sm">
              <Clock size={14} />
              <span>{PERIOD_LABELS[period]}</span>
              <ChevronDown size={14} className="transition-transform group-hover:rotate-180" />
            </button>
            <div className="absolute left-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
              {[
                { key: 'today', label: 'Today', icon: Clock },
                { key: 'week', label: 'This week', icon: Calendar },
                { key: 'month', label: 'This month', icon: ChartTrendingUp },
              ].map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  onClick={() => setPeriod(key)}
                  className={clsx(
                    'w-full text-left px-4 py-2.5 text-xs font-semibold flex items-center gap-2 transition-colors',
                    period === key
                      ? 'bg-black text-white'
                      : 'text-gray-700 hover:bg-gray-50',
                    key === 'today' && 'first:rounded-t-lg',
                    key === 'month' && 'last:rounded-b-lg'
                  )}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Export dropdown */}
          <div className="relative group">
            <button className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors shadow-sm">
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

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCardsData.map(({ label, value, icon: Icon, color, bg, kpiKey, isPercentage }) => {
          // Current vs previous from the analytics response
          const kpis = analyticsData?.kpis || {}
          const prev = kpis.previous || {}
          const currentValue = kpiKey ? (kpis[kpiKey] ?? 0) : 0
          const previousValue = kpiKey ? (prev[kpiKey] ?? 0) : 0

          // Use animation for numeric and percentage values
          let animatedValue = 0
          if (isPercentage) {
            animatedValue = useCountAnimation(currentValue * 100, 2000, true)
          } else {
            animatedValue = useCountAnimation(currentValue)
          }

          // Display value
          let displayValue = value
          if (isPercentage) {
            displayValue = `${animatedValue.toFixed(1)}%`
          } else {
            displayValue = animatedValue
          }

          // Change calculation
          const change = currentValue - previousValue
          const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '→'
          const colorClass =
            change > 0 ? 'text-green-600' :
            change < 0 ? 'text-red-600'   :
                         'text-gray-500'

          // Format change display
          const changeDisplay = isPercentage
            ? `${(change * 100).toFixed(1)}%`
            : Math.abs(change)

          return (
            <div key={label} className="stat-card">
              <div className="flex items-start justify-between">
                <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center', bg)}>
                  <Icon size={18} className={color} />
                </div>
                <span className={`text-[10px] font-semibold ${colorClass}`}>
                  {arrow} {changeDisplay}
                </span>
              </div>
              <p className="text-4xl font-bold text-gray-900 mt-2 tabular-nums">{displayValue}</p>
              <p className="text-sm text-gray-500 font-semibold">{label}</p>
              <p className="text-[10px] text-gray-400">vs {PREVIOUS_LABELS[period]}</p>
            </div>
          )
        })}
      </div>

      {/* Channel Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Graph: 3/4 width */}
        <div className="lg:col-span-3 card p-6">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-gray-900">Channel Performance</h2>
              <p className="text-xs text-gray-500 mt-1">Inbound messages (solid) vs AI replies (dotted) vs Human replies (dashed)</p>
            </div>
            <button
              onClick={() => setShowChannelModal(true)}
              className="text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors whitespace-nowrap"
            >
              View Details →
            </button>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 20, right: 20, left: -20, bottom: 5 }}>
              <CartesianGrid stroke="rgba(0,0,0,0.05)" vertical={false} strokeDasharray="0" />
              <XAxis 
                dataKey="time" 
                tick={{ fontSize: 12, fill: '#a1a1aa', fontFamily: 'Quicksand' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis 
                tick={{ fontSize: 12, fill: '#a1a1aa', fontFamily: 'Quicksand' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              {/* Instagram */}
              <Line type="natural" dataKey="instagram"       name="Instagram (Inbound)"   stroke="#ec4899" strokeWidth={2} dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="instagram_ai"    name="Instagram (AI)"        stroke="#ec4899" strokeWidth={2} strokeDasharray="4 2" dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="instagram_human" name="Instagram (Human)"     stroke="#ec4899" strokeWidth={2} strokeDasharray="8 4" dot={false} activeDot={{ r: 6 }} />
              {/* WhatsApp */}
              <Line type="natural" dataKey="whatsapp"        name="WhatsApp (Inbound)"    stroke="#22c55e" strokeWidth={2} dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="whatsapp_ai"     name="WhatsApp (AI)"         stroke="#22c55e" strokeWidth={2} strokeDasharray="4 2" dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="whatsapp_human"  name="WhatsApp (Human)"      stroke="#22c55e" strokeWidth={2} strokeDasharray="8 4" dot={false} activeDot={{ r: 6 }} />
              {/* Facebook */}
              <Line type="natural" dataKey="facebook"        name="Facebook (Inbound)"    stroke="#3b82f6" strokeWidth={2} dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="facebook_ai"     name="Facebook (AI)"         stroke="#3b82f6" strokeWidth={2} strokeDasharray="4 2" dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="facebook_human"  name="Facebook (Human)"      stroke="#3b82f6" strokeWidth={2} strokeDasharray="8 4" dot={false} activeDot={{ r: 6 }} />
              {/* TikTok */}
              <Line type="natural" dataKey="tiktok"          name="TikTok (Inbound)"      stroke="#111111" strokeWidth={2} dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="tiktok_ai"       name="TikTok (AI)"           stroke="#111111" strokeWidth={2} strokeDasharray="4 2" dot={false} activeDot={{ r: 6 }} />
              <Line type="natural" dataKey="tiktok_human"    name="TikTok (Human)"        stroke="#111111" strokeWidth={2} strokeDasharray="8 4" dot={false} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
          
          {/* Legend */}
          <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-6 mt-5 text-[11px]">
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#ec4899" strokeWidth="2" /></svg>
              <span className="text-gray-600 font-medium">IG</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#22c55e" strokeWidth="2" /></svg>
              <span className="text-gray-600 font-medium">WA</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#3b82f6" strokeWidth="2" /></svg>
              <span className="text-gray-600 font-medium">FB</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#111111" strokeWidth="2" /></svg>
              <span className="text-gray-600 font-medium">TT</span>
            </div>
            <span className="text-gray-400 mx-2">|</span>
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#000" strokeWidth="1.5" /></svg>
              <span className="text-gray-600 font-medium">Inbound</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#000" strokeWidth="1.5" strokeDasharray="4 2" /></svg>
              <span className="text-gray-600 font-medium">AI</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg width="16" height="2"><line x1="0" y1="1" x2="16" y2="1" stroke="#000" strokeWidth="1.5" strokeDasharray="8 4" /></svg>
              <span className="text-gray-600 font-medium">Human</span>
            </div>
          </div>
        </div>

        {/* Stats: 1/4 width - each in own card */}
        <div className="lg:col-span-1 space-y-3">
          {channelStats.map(({ label, value }) => {
            const colorMap = {
              'Instagram': { bg: 'bg-pink-50', border: 'border-pink-100', text: 'text-pink-600', upper: 'text-pink-600' },
              'WhatsApp': { bg: 'bg-green-50', border: 'border-green-100', text: 'text-green-600', upper: 'text-green-600' },
              'Facebook': { bg: 'bg-blue-50', border: 'border-blue-100', text: 'text-blue-600', upper: 'text-blue-600' },
              'TikTok': { bg: 'bg-gray-50', border: 'border-gray-200', text: 'text-gray-600', upper: 'text-gray-600' },
            }
            const colors = colorMap[label] || colorMap['Instagram']
            return (
              <div key={label} className={`card ${colors.bg} border ${colors.border} p-4`}>
                <p className={`text-[11px] ${colors.upper} font-semibold uppercase tracking-wider`}>{label}</p>
                <p className={`text-2xl font-bold ${colors.text} mt-2`}>{value}</p>
                <p className={`text-xs ${colors.text} mt-1 opacity-75`}>{PERIOD_LABELS[period]}</p>              </div>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity feed */}
        <div className="lg:col-span-2 card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-gray-900">Live Activity</h2>
            <span className="flex items-center gap-1.5 text-xs text-green-600 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} />
              Live
            </span>
          </div>
          <div className="space-y-3">
            {activityFeedData.map((item) => (
              <ActivityItem key={item.id} item={item} />
            ))}
          </div>
        </div>

        {/* Alerts + quick stats */}
        <div className="space-y-4">
          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-gray-900">System Alerts</h2>
              <a href="/logs" className="text-xs text-brand-600 hover:text-brand-700 font-semibold transition-colors">
                View All →
              </a>
            </div>
            <div className="space-y-2.5">
              {systemAlertsData.map((alert) => {
                const { icon: Icon, cls } = alertStyles[alert.level] || alertStyles.info
                return (
                  <div key={alert.id} className={clsx('flex items-start gap-2.5 p-3 rounded-lg border text-xs font-medium', cls)}>
                    <Icon size={13} className="mt-0.5 shrink-0" />
                    <p className="leading-snug">{alert.message}</p>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title mb-3">AI Performance Today</p>
            <div className="space-y-2.5">
              {[
                { label: 'Success rate',    value: '97.2%', color: 'text-green-600'  },
                { label: 'Avg response',    value: '1.1s',  color: 'text-gray-900'   },
                { label: 'Override rate',   value: '2.8%',  color: 'text-amber-600'  },
              ].map(({ label, value, color }) => (
                <div key={label} className="flex justify-between items-center">
                  <span className="text-sm text-gray-500">{label}</span>
                  <span className={clsx('text-sm font-bold', color)}>{value}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <p className="section-title">Conversion Rate</p>
              <span className="text-xs font-bold text-green-600 bg-green-50 px-2 py-1 rounded-lg">↑ 12%</span>
            </div>
            <div className="space-y-3">
              {[
                { label: 'Conversations', value: 42, total: 156, color: 'bg-orange-500' },
                { label: 'Purchases', value: 42, total: 156, color: 'bg-black' },
                { label: 'Conversion', value: '26.9%', total: null, color: 'bg-orange-600' },
              ].map(({ label, value, total, color }) => (
                <div key={label}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-medium text-gray-600">{label}</span>
                    <span className="text-xs font-bold text-gray-900">
                      {total ? `${value}/${total}` : value}
                    </span>
                  </div>
                  {total && (
                    <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={clsx('h-full rounded-full transition-all', color)}
                        style={{ width: `${(value / total) * 100}%` }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Channel Performance Modal */}
      {showChannelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowChannelModal(false)} />
          <div className="relative bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="sticky top-0 bg-gradient-to-r from-gray-50 to-white border-b border-gray-200 px-6 py-5 flex items-start justify-between">
              <div className="flex-1">
                <h2 className="text-2xl font-bold text-gray-900">Channel Performance</h2>
                <p className="text-sm text-gray-500 mt-1">Detailed breakdown of inbound and outbound messages by channel • {PERIOD_LABELS[period]}</p>
              </div>
              <button
                onClick={() => setShowChannelModal(false)}
                className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              >
                <X size={22} />
              </button>
            </div>

            {/* Content */}
            <div className="p-8 space-y-8">
              {/* Key Metrics */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { 
                    label: 'Total Inbound', 
                    value: chartData.reduce((sum, d) => sum + d.instagram + d.whatsapp + d.facebook + d.tiktok, 0), 
                    color: 'from-blue-50 to-blue-100',
                    textColor: 'text-blue-700',
                    icon: '📥'
                  },
                  { 
                    label: 'AI Replies', 
                    value: chartData.reduce((sum, d) => sum + d.instagram_ai + d.whatsapp_ai + d.facebook_ai + d.tiktok_ai, 0), 
                    color: 'from-brand-50 to-brand-100',
                    textColor: 'text-brand-700',
                    icon: '🤖'
                  },
                  { 
                    label: 'Human Replies', 
                    value: chartData.reduce((sum, d) => sum + d.instagram_human + d.whatsapp_human + d.facebook_human + d.tiktok_human, 0), 
                    color: 'from-amber-50 to-amber-100',
                    textColor: 'text-amber-700',
                    icon: '👤'
                  },
                  { 
                    label: 'Response Rate', 
                    value: `${(chartData.reduce((sum, d) => sum + d.instagram_ai + d.whatsapp_ai + d.facebook_ai + d.tiktok_ai + d.instagram_human + d.whatsapp_human + d.facebook_human + d.tiktok_human, 0) / Math.max(chartData.reduce((sum, d) => sum + d.instagram + d.whatsapp + d.facebook + d.tiktok, 0), 1) * 100).toFixed(0)}%`, 
                    color: 'from-green-50 to-green-100',
                    textColor: 'text-green-700',
                    icon: '📊'
                  },
                ].map(({ label, value, color, textColor, icon }) => (
                  <div key={label} className={`bg-gradient-to-br ${color} rounded-xl p-5 border border-opacity-10 hover:shadow-md transition-shadow`}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-gray-600 font-semibold uppercase tracking-wider">{label}</p>
                      <span className="text-xl">{icon}</span>
                    </div>
                    <p className={`text-3xl font-bold ${textColor}`}>{value}</p>
                  </div>
                ))}
              </div>

              {/* Per-channel breakdown */}
              <div>
                <h3 className="text-lg font-bold text-gray-900 mb-4">Messages by Channel</h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {[
                    { name: 'Instagram', color: '#ec4899', borderColor: '#fda4de', key: 'instagram', emoji: '📸' },
                    { name: 'WhatsApp', color: '#22c55e', borderColor: '#86efac', key: 'whatsapp', emoji: '💬' },
                    { name: 'Facebook', color: '#3b82f6', borderColor: '#93c5fd', key: 'facebook', emoji: 'f' },
                    { name: 'TikTok', color: '#111111', borderColor: '#e5e7eb', key: 'tiktok', emoji: '♪' },
                  ].map(({ name, color, borderColor, key, emoji }) => {
                    const inbound = chartData.reduce((sum, d) => sum + (d[key] || 0), 0)
                    const ai = chartData.reduce((sum, d) => sum + (d[`${key}_ai`] || 0), 0)
                    const human = chartData.reduce((sum, d) => sum + (d[`${key}_human`] || 0), 0)
                    const total = inbound + ai + human
                    const inboundPct = total > 0 ? ((inbound / total) * 100).toFixed(1) : 0
                    const aiPct = total > 0 ? ((ai / total) * 100).toFixed(1) : 0
                    const humanPct = total > 0 ? ((human / total) * 100).toFixed(1) : 0
                    
                    return (
                      <div key={name} className="border-l-4 rounded-xl p-5 bg-gray-50 hover:bg-white transition-colors" style={{ borderLeftColor: color }}>
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg flex items-center justify-center font-bold text-white" style={{ background: color }}>
                              {emoji.length > 1 ? emoji.charAt(0) : emoji}
                            </div>
                            <div>
                              <h4 className="font-semibold text-gray-900">{name}</h4>
                              <p className="text-xs text-gray-400">Total messages</p>
                            </div>
                          </div>
                          <span className="text-2xl font-bold text-gray-900">{total}</span>
                        </div>
                        <div className="space-y-3">
                          {[
                            { label: 'Inbound', count: inbound, pct: inboundPct, opacity: 1 },
                            { label: 'AI Replies', count: ai, pct: aiPct, opacity: 0.7 },
                            { label: 'Human Replies', count: human, pct: humanPct, opacity: 0.4 },
                          ].map(({ label, count, pct, opacity }) => (
                            <div key={label}>
                              <div className="flex items-center justify-between mb-1.5">
                                <span className="text-sm font-medium text-gray-700">{label}</span>
                                <span className="text-sm font-bold text-gray-900">{count} <span className="text-xs text-gray-400">({pct}%)</span></span>
                              </div>
                              <div className="w-full h-2.5 bg-gray-200 rounded-full overflow-hidden">
                                <div
                                  className="h-full rounded-full transition-all duration-300"
                                  style={{
                                    width: `${pct}%`,
                                    background: color,
                                    opacity: opacity,
                                  }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Response efficiency chart */}
              <div className="bg-gradient-to-r from-blue-50 to-cyan-50 border border-blue-200 rounded-xl p-6">
                <h3 className="text-sm font-bold text-gray-900 mb-4">Response Distribution</h3>
                <div className="flex items-end justify-around h-24 gap-2">
                  {[
                    { label: 'Inbound', value: chartData.reduce((sum, d) => sum + d.instagram + d.whatsapp + d.facebook + d.tiktok, 0), color: '#3b82f6' },
                    { label: 'AI', value: chartData.reduce((sum, d) => sum + d.instagram_ai + d.whatsapp_ai + d.facebook_ai + d.tiktok_ai, 0), color: '#f59e0b' },
                    { label: 'Human', value: chartData.reduce((sum, d) => sum + d.instagram_human + d.whatsapp_human + d.facebook_human + d.tiktok_human, 0), color: '#10b981' },
                  ].map(({ label, value, color }) => {
                    const maxVal = Math.max(
                      chartData.reduce((sum, d) => sum + d.instagram + d.whatsapp + d.facebook + d.tiktok, 0),
                      chartData.reduce((sum, d) => sum + d.instagram_ai + d.whatsapp_ai + d.facebook_ai + d.tiktok_ai, 0),
                      chartData.reduce((sum, d) => sum + d.instagram_human + d.whatsapp_human + d.facebook_human + d.tiktok_human, 0)
                    )
                    const height = maxVal > 0 ? (value / maxVal) * 100 : 0
                    return (
                      <div key={label} className="flex flex-col items-center flex-1">
                        <div
                          className="w-full rounded-t-lg transition-all duration-300 hover:opacity-80"
                          style={{
                            height: `${height || 10}%`,
                            background: color,
                            minHeight: '8px',
                          }}
                        />
                        <p className="text-xs font-semibold text-gray-600 mt-2">{label}</p>
                        <p className="text-sm font-bold text-gray-900">{value}</p>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
