import {
  MessageSquare, Inbox, Bot, UserCheck, XCircle, PackageX, UserRound, Activity,
  AlertTriangle, AlertCircle, Info, Instagram, Smartphone, ShoppingBag, TrendingUp,
  Download, FileText, File, Calendar, Clock, TrendingUp as ChartTrendingUp, ChevronDown, X, Music,
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
        <p className="text-sm text-gray-800 leading-relaxed break-words">{item.text}</p>
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
    return systemAlerts.slice(0, 3).map(log => ({
      id: log.id,
      level: log.level || 'info',
      message: log.message || 'System event',
    }))
  }

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
        created_at: log.created_at,
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
      ['Total Messages', kpis.messages_total || 0],
      ['AI Replies', kpis.ai_replies_total || 0],
      ['Human Overrides', kpis.human_override_total || 0],
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
      ['Total Messages', kpis.messages_total || 0],
      ['AI Replies', kpis.ai_replies_total || 0],
      ['Human Overrides', kpis.human_override_total || 0],
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
            <div key={label} className="stat-card min-w-0">
              <div className="flex items-start justify-between gap-2">
                <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center shrink-0', bg)}>
                  <Icon size={18} className={color} />
                </div>
                <span className={`text-[10px] font-semibold whitespace-nowrap ${colorClass}`}>
                  {arrow} {changeDisplay}
                </span>
              </div>
              <p className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mt-2 tabular-nums truncate">{displayValue}</p>
              <p className="text-sm text-gray-500 font-semibold truncate">{label}</p>
              <p className="text-[10px] text-gray-400 truncate">vs {PREVIOUS_LABELS[period]}</p>
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
            <LineChart data={chartData} margin={{ top: 20, right: 10, left: 0, bottom: 5 }}>
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
            {loadingActivity ? (
              <div className="py-8 text-center text-xs text-gray-400">Loading activity…</div>
            ) : activityFeedData.length === 0 ? (
              <div className="py-8 text-center text-xs text-gray-400">No recent activity</div>
            ) : (
              activityFeedData.map((item) => (
                <ActivityItem key={item.id} item={item} />
              ))
            )}
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
              {loadingAlerts ? (
                <div className="py-6 text-center text-xs text-gray-400">Loading…</div>
              ) : systemAlertsData.length === 0 ? (
                <div className="py-6 text-center text-xs text-gray-400">All systems normal</div>
              ) : (
                systemAlertsData.map((alert) => {
                  const { icon: Icon, cls } = alertStyles[alert.level] || alertStyles.info
                  return (
                    <div key={alert.id} className={clsx('flex items-start gap-2.5 p-3 rounded-lg border text-xs font-medium', cls)}>
                      <Icon size={13} className="mt-0.5 shrink-0" />
                      <p className="leading-snug break-words min-w-0 flex-1">{alert.message}</p>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title mb-3">AI Performance {PERIOD_LABELS[period]}</p>
            <div className="space-y-2.5">
              {(() => {
                const kpis = analyticsData?.kpis || {}
                const successRate = ((kpis.ai_success_rate || 0) * 100).toFixed(1)
                const avgResponseMs = kpis.avg_response_time_ms
                const avgResponseStr = avgResponseMs == null
                  ? '—'
                  : avgResponseMs < 1 
                    ? '<1ms'
                    : avgResponseMs < 1000
                      ? `${avgResponseMs}ms`
                      : `${(avgResponseMs / 1000).toFixed(1)}s`
                const aiReplies = kpis.ai_replies_total || 0
                const overrides = kpis.human_override_total || 0
                const overrideRate = aiReplies > 0
                  ? ((overrides / aiReplies) * 100).toFixed(1)
                  : '0.0'
                return [
                  { label: 'Success rate',  value: `${successRate}%`,  color: 'text-green-600' },
                  { label: 'Avg response',  value: avgResponseStr,     color: 'text-gray-900'  },
                  { label: 'Override rate', value: `${overrideRate}%`, color: 'text-amber-600' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex justify-between items-center">
                    <span className="text-sm text-gray-500">{label}</span>
                    <span className={clsx('text-sm font-bold', color)}>{value}</span>
                  </div>
                ))
              })()}
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
          <div className="fixed inset-0 bg-black/50 backdrop-blur-md" onClick={() => setShowChannelModal(false)} />
          <div className="relative bg-white rounded-3xl shadow-2xl max-w-5xl w-full max-h-[90vh] overflow-y-auto border border-gray-100">
            {/* Header - Clean & Minimal */}
            <div className="sticky top-0 bg-white/80 backdrop-blur-xl border-b border-gray-100 px-4 sm:px-6 lg:px-8 py-4 lg:py-6 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg sm:text-xl lg:text-2xl font-semibold text-gray-900 truncate">Channel Performance</h2>
                <p className="text-sm text-gray-500 mt-1">Message analytics across all platforms • {PERIOD_LABELS[period]}</p>
              </div>
              <button
                onClick={() => setShowChannelModal(false)}
                className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              >
                <X size={20} />
              </button>
            </div>

            {/* Content */}
            <div className="p-4 sm:p-6 lg:p-8 space-y-6 lg:space-y-8">
              {/* Key Metrics */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {(() => {
                  const totalInbound = chartData.reduce((sum, d) => sum + d.instagram + d.whatsapp + d.facebook + d.tiktok, 0)
                  const totalAI = chartData.reduce((sum, d) => sum + d.instagram_ai + d.whatsapp_ai + d.facebook_ai + d.tiktok_ai, 0)
                  const totalHuman = chartData.reduce((sum, d) => sum + d.instagram_human + d.whatsapp_human + d.facebook_human + d.tiktok_human, 0)
                  const responseRate = totalInbound > 0 ? Math.round(((totalAI + totalHuman) / totalInbound) * 100) : 0
                  return [
                    { label: 'Total Inbound', value: totalInbound, Icon: Inbox, iconBg: 'bg-blue-50', iconColor: 'text-blue-600' },
                    { label: 'AI Replies', value: totalAI, Icon: Bot, iconBg: 'bg-brand-50', iconColor: 'text-brand-600' },
                    { label: 'Human Replies', value: totalHuman, Icon: UserRound, iconBg: 'bg-amber-50', iconColor: 'text-amber-600' },
                    { label: 'Response Rate', value: `${responseRate}%`, Icon: Activity, iconBg: 'bg-green-50', iconColor: 'text-green-600' },
                  ]
                })().map(({ label, value, Icon, iconBg, iconColor }) => (
                  <div key={label} className="bg-white border border-gray-100 rounded-2xl p-4 sm:p-5 hover:border-gray-200 hover:shadow-sm transition-all min-w-0">
                    <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center mb-3', iconBg)}>
                      <Icon size={18} className={iconColor} />
                    </div>
                    <p className="text-2xl sm:text-3xl font-bold text-gray-900 tabular-nums leading-none truncate">{value}</p>
                    <p className="text-xs text-gray-500 font-semibold mt-2 uppercase tracking-wide truncate">{label}</p>
                  </div>
                ))}
              </div>

              {/* Per-channel breakdown - Minimal cards */}
              <div>
                <h3 className="text-base font-semibold text-gray-900 mb-5">Messages by Channel</h3>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {[
                    { name: 'Instagram', color: '#ec4899', icon: Instagram, key: 'instagram' },
                    { name: 'WhatsApp', color: '#22c55e', icon: Smartphone, key: 'whatsapp' },
                    { name: 'Facebook', color: '#3b82f6', icon: MessageSquare, key: 'facebook' },
                    { name: 'TikTok', color: '#111111', icon: Music, key: 'tiktok' },
                  ].map(({ name, color, icon: Icon, key }) => {
                    const inbound = chartData.reduce((sum, d) => sum + (d[key] || 0), 0)
                    const ai = chartData.reduce((sum, d) => sum + (d[`${key}_ai`] || 0), 0)
                    const human = chartData.reduce((sum, d) => sum + (d[`${key}_human`] || 0), 0)
                    const total = inbound + ai + human
                    const inboundPct = total > 0 ? ((inbound / total) * 100).toFixed(1) : 0
                    const aiPct = total > 0 ? ((ai / total) * 100).toFixed(1) : 0
                    const humanPct = total > 0 ? ((human / total) * 100).toFixed(1) : 0
                    
                    // Platform's share of TOTAL CUSTOMER TRAFFIC (inbound only,
                    // so AI/human replies don't double-count the same convo).
                    const grandInbound = chartData.reduce((sum, d) =>
                      sum + d.instagram + d.whatsapp + d.facebook + d.tiktok, 0)
                    const platformShare = grandInbound > 0 ? ((inbound / grandInbound) * 100).toFixed(0) : 0

                    return (
                      <div
                        key={name}
                        className="rounded-2xl p-5 transition-all relative overflow-hidden"
                        style={{
                          background: `linear-gradient(135deg, ${color}08 0%, ${color}02 100%)`,
                          border: `1px solid ${color}20`,
                        }}
                      >
                        {/* Platform header */}
                        <div className="flex items-center justify-between mb-5">
                          <div className="flex items-center gap-3 min-w-0">
                            <div
                              className="w-11 h-11 rounded-xl flex items-center justify-center text-white shrink-0 shadow-sm"
                              style={{ background: color }}
                            >
                              <Icon size={20} />
                            </div>
                            <div className="min-w-0">
                              <h4 className="font-semibold text-gray-900 text-sm truncate">{name}</h4>
                              <p className="text-xs font-medium" style={{ color }}>
                                {platformShare}% of total volume
                              </p>
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="text-2xl font-bold text-gray-900 leading-none">{total}</p>
                            <p className="text-[10px] text-gray-500 mt-1 uppercase tracking-wide">messages</p>
                          </div>
                        </div>

                        {/* Stacked composition bar */}
                        {total > 0 && (
                          <div className="mb-4">
                            <div className="flex h-2.5 rounded-full overflow-hidden bg-gray-100">
                              <div style={{ width: `${inboundPct}%`, background: color, opacity: 1 }} />
                              <div style={{ width: `${aiPct}%`, background: color, opacity: 0.55 }} />
                              <div style={{ width: `${humanPct}%`, background: color, opacity: 0.25 }} />
                            </div>
                          </div>
                        )}

                        {/* Three-up stats row */}
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { label: 'Inbound', count: inbound, pct: inboundPct, opacity: 1 },
                            { label: 'AI', count: ai, pct: aiPct, opacity: 0.55 },
                            { label: 'Human', count: human, pct: humanPct, opacity: 0.25 },
                          ].map(({ label, count, pct, opacity }) => (
                            <div key={label} className="bg-white/60 backdrop-blur-sm rounded-lg p-2.5 border border-white/40">
                              <div className="flex items-center gap-1.5 mb-1">
                                <span
                                  className="w-2 h-2 rounded-full shrink-0"
                                  style={{ background: color, opacity }}
                                />
                                <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wide truncate">{label}</span>
                              </div>
                              <p className="text-base font-bold text-gray-900 leading-none">{count}</p>
                              <p className="text-[10px] text-gray-500 mt-0.5">{pct}%</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Response Mix by Platform */}
              <div className="bg-white border border-gray-100 rounded-2xl p-6">
                <div className="flex items-start justify-between mb-1">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">Response Mix by Platform</h3>
                    <p className="text-xs text-gray-500 mt-0.5">How each channel splits between AI and human replies</p>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] font-semibold text-gray-500 uppercase tracking-wide">
                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-gray-300" />Inbound</span>
                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-brand-500" />AI</span>
                    <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-500" />Human</span>
                  </div>
                </div>

                <div className="mt-6 space-y-5">
                  {[
                    { name: 'Instagram', key: 'instagram', color: '#ec4899' },
                    { name: 'WhatsApp', key: 'whatsapp', color: '#22c55e' },
                    { name: 'Facebook', key: 'facebook', color: '#3b82f6' },
                    { name: 'TikTok', key: 'tiktok', color: '#111111' },
                  ].map(({ name, key, color }) => {
                    const inbound = chartData.reduce((s, d) => s + (d[key] || 0), 0)
                    const ai = chartData.reduce((s, d) => s + (d[`${key}_ai`] || 0), 0)
                    const human = chartData.reduce((s, d) => s + (d[`${key}_human`] || 0), 0)
                    const total = inbound + ai + human
                    // Scale across all platforms so bars are comparable
                    const grandMax = Math.max(
                      ...['instagram', 'whatsapp', 'facebook', 'tiktok'].map(k =>
                        chartData.reduce((s, d) => s + (d[k] || 0) + (d[`${k}_ai`] || 0) + (d[`${k}_human`] || 0), 0)
                      )
                    )
                    const widthPct = grandMax > 0 ? (total / grandMax) * 100 : 0
                    const inboundShare = total > 0 ? (inbound / total) * 100 : 0
                    const aiShare = total > 0 ? (ai / total) * 100 : 0
                    const humanShare = total > 0 ? (human / total) * 100 : 0

                    return (
                      <div key={name}>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                            <span className="text-xs font-semibold text-gray-700">{name}</span>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] font-medium text-gray-500 tabular-nums">
                            <span><span className="text-gray-900 font-bold">{inbound}</span> in</span>
                            <span><span className="text-gray-900 font-bold">{ai}</span> ai</span>
                            <span><span className="text-gray-900 font-bold">{human}</span> hu</span>
                          </div>
                        </div>
                        <div className="h-6 rounded-lg bg-gray-50 overflow-hidden" style={{ width: `${Math.max(widthPct, 2)}%`, minWidth: '40px', transition: 'width 600ms' }}>
                          {total > 0 ? (
                            <div className="flex h-full">
                              <div style={{ width: `${inboundShare}%`, background: '#d1d5db' }} title={`${inbound} inbound`} />
                              <div style={{ width: `${aiShare}%`, background: '#ff5900' }} title={`${ai} AI replies`} />
                              <div style={{ width: `${humanShare}%`, background: '#f59e0b' }} title={`${human} human replies`} />
                            </div>
                          ) : null}
                        </div>
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
