import { stats, activityFeed, alerts } from '../data/mock'
import {
  MessageSquare, Bot, UserCheck, XCircle, PackageX,
  AlertTriangle, AlertCircle, Info, Instagram, Smartphone, ShoppingBag, TrendingUp,
  Download, FileText, File,
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import clsx from 'clsx'
import { useState, useEffect } from 'react'
import { getAnalyticsSummary, getSystemLogs, getMyLogs } from '../api/dashboard'
import { SkeletonCard } from '../components/Skeleton'
import { useCountAnimation } from '../hooks/useCountAnimation'

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

export default function Dashboard() {
  const [analyticsData, setAnalyticsData] = useState(null)
  const [systemAlerts, setSystemAlerts] = useState([])
  const [activityLogs, setActivityLogs] = useState([])
  const [loadingAnalytics, setLoadingAnalytics] = useState(true)
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [loadingActivity, setLoadingActivity] = useState(true)

  // Load analytics summary
  useEffect(() => {
    const load = async () => {
      setLoadingAnalytics(true)
      try {
        const data = await getAnalyticsSummary()
        setAnalyticsData(data)
      } catch (err) {
        console.error('Failed to load analytics:', err)
        // Fall back to dummy data
      } finally {
        setLoadingAnalytics(false)
      }
    }
    load()
  }, [])

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

  // Build stat cards from analytics data or use fallback
  const getStatCards = () => {
    if (!analyticsData || !analyticsData.kpis) {
      return [
        { label: 'Total Messages',        value: 0,   icon: MessageSquare, color: 'text-blue-500',    bg: 'bg-blue-50'        },
        { label: 'Automated AI Replies',  value: 0,   icon: Bot,           color: 'text-brand-500',   bg: 'bg-brand-50'       },
        { label: 'Human Overrides',       value: 0,   icon: UserCheck,     color: 'text-amber-500',   bg: 'bg-amber-50'       },
        { label: 'Failed Responses',      value: 0,   icon: XCircle,       color: 'text-red-500',     bg: 'bg-red-50'         },
        { label: 'Escalated',             value: 0,   icon: TrendingUp,    color: 'text-purple-500',  bg: 'bg-purple-50'      },
        { label: 'AI Success Rate',       value: '0%', icon: PackageX,     color: 'text-green-500',   bg: 'bg-green-50'       },
      ]
    }

    const kpis = analyticsData.kpis
    return [
      { label: 'Total Messages',        value: kpis.messages_total || 0,           icon: MessageSquare, color: 'text-blue-500',    bg: 'bg-blue-50'        },
      { label: 'Automated AI Replies',  value: kpis.ai_replies_total || 0,         icon: Bot,           color: 'text-brand-500',   bg: 'bg-brand-50'       },
      { label: 'Human Overrides',       value: kpis.human_override_total || 0,     icon: UserCheck,     color: 'text-amber-500',   bg: 'bg-amber-50'       },
      { label: 'Failed Responses',      value: kpis.failed_responses || 0,         icon: XCircle,       color: 'text-red-500',     bg: 'bg-red-50'         },
      { label: 'Escalated',             value: kpis.escalated_total || 0,          icon: TrendingUp,    color: 'text-purple-500',  bg: 'bg-purple-50'      },
      { label: 'AI Success Rate',       value: `${(kpis.ai_success_rate * 100).toFixed(1)}%`, icon: PackageX, color: 'text-green-500', bg: 'bg-green-50' },
    ]
  }

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

  // Map activity logs to feed format
  const getActivityFeed = () => {
    if (activityLogs.length > 0) {
      return activityLogs.slice(0, 10).map(log => ({
        id: log.id,
        text: log.message || 'Activity logged',
        channel: log.source || 'system',
        time: formatTimeAgo(log.created_at),
      }))
    }
    // Fallback to mock data
    return activityFeed
  }

  const formatTimeAgo = (timestamp) => {
    const now = new Date()
    const date = new Date(timestamp)
    const seconds = Math.floor((now - date) / 1000)
    
    if (seconds < 60) return 'now'
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes} min ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  }

  const statCardsData = getStatCards()
  const systemAlertsData = getSystemAlerts()
  // Always use mock activity feed for now - it has better formatted statements
  const activityFeedData = activityFeed

  // Get channel data from analytics or use dummy
  const channelStats = !analyticsData?.channel_split ? [
    { label: 'Instagram', value: 186 },
    { label: 'WhatsApp', value: 137 },
    { label: 'Facebook', value: 152 },
    { label: 'TikTok', value: 87 },
  ] : [
    { label: 'Instagram', value: analyticsData.channel_split.filter(c => c.name.includes('instagram')).reduce((sum, c) => sum + c.count, 0) || 186 },
    { label: 'WhatsApp', value: analyticsData.channel_split.find(c => c.name === 'whatsapp')?.count || 137 },
    { label: 'Facebook', value: analyticsData.channel_split.filter(c => c.name.includes('facebook')).reduce((sum, c) => sum + c.count, 0) || 152 },
    { label: 'TikTok', value: analyticsData.channel_split.filter(c => c.name.includes('tiktok')).reduce((sum, c) => sum + c.count, 0) || 87 },
  ]

  // Chart data from analytics (only if we have it), otherwise use dummy
  const getDummyChartData = () => [
    { time: 'Mon', instagram: 12, instagram_resp: 10, whatsapp: 8, whatsapp_resp: 7, facebook: 15, facebook_resp: 12, tiktok: 5, tiktok_resp: 4 },
    { time: 'Tue', instagram: 18, instagram_resp: 15, whatsapp: 14, whatsapp_resp: 11, facebook: 12, facebook_resp: 10, tiktok: 9, tiktok_resp: 7 },
    { time: 'Wed', instagram: 15, instagram_resp: 12, whatsapp: 11, whatsapp_resp: 9, facebook: 22, facebook_resp: 18, tiktok: 7, tiktok_resp: 5 },
    { time: 'Thu', instagram: 28, instagram_resp: 24, whatsapp: 19, whatsapp_resp: 16, facebook: 18, facebook_resp: 15, tiktok: 14, tiktok_resp: 11 },
    { time: 'Fri', instagram: 22, instagram_resp: 19, whatsapp: 26, whatsapp_resp: 23, facebook: 25, facebook_resp: 21, tiktok: 11, tiktok_resp: 9 },
    { time: 'Sat', instagram: 32, instagram_resp: 28, whatsapp: 21, whatsapp_resp: 18, facebook: 16, facebook_resp: 13, tiktok: 18, tiktok_resp: 15 },
    { time: 'Sun', instagram: 26, instagram_resp: 23, whatsapp: 18, whatsapp_resp: 15, facebook: 28, facebook_resp: 24, tiktok: 13, tiktok_resp: 10 },
  ]

  const chartData = getDummyChartData()

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Live overview of your AI support system</p>
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

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCardsData.map(({ label, value, icon: Icon, color, bg }, idx) => {
          // Use animation for numeric values only
          const isNumeric = typeof value === 'number'
          const isPercentage = typeof value === 'string' && value.includes('%')
          
          let displayValue = value
          let animatedChange = 0
          
          // Animate numeric values
          if (isNumeric) {
            animatedChange = useCountAnimation(value)
            displayValue = animatedChange
          }
          
          // Animate percentage values
          if (isPercentage) {
            const percentValue = parseFloat(value)
            const animatedPercent = useCountAnimation(percentValue)
            displayValue = `${animatedPercent.toFixed(1)}%`
          }
          
          // Calculate change from yesterday (all metrics compare to yesterday)
          const kpis = analyticsData?.kpis || {}
          let change = 0
          let colorClass = 'text-gray-600'
          const periodLabel = 'yesterday'
          
          // Map label to KPI fields for yesterday comparison
          const labelToYesterdayKey = {
            'Total Messages': { current: 'messages_total', yesterday: 'yesterday_messages_total' },
            'Automated AI Replies': { current: 'ai_replies_total', yesterday: 'yesterday_ai_replies_total' },
            'Human Overrides': { current: 'human_override_total', yesterday: 'yesterday_human_override_total' },
            'Failed Responses': { current: 'failed_responses', yesterday: 'yesterday_failed_responses' },
            'Escalated': { current: 'escalated_total', yesterday: 'yesterday_escalated_total' },
          }
          
          if (isNumeric && analyticsData) {
            const keyPair = labelToYesterdayKey[label]
            
            if (keyPair && kpis[keyPair.current] !== undefined && kpis[keyPair.yesterday] !== undefined) {
              change = kpis[keyPair.current] - kpis[keyPair.yesterday]
              
              // Determine color based on change
              if (change === 0) {
                colorClass = 'text-gray-600'
              } else if (change > 0) {
                colorClass = 'text-green-600'
              } else {
                colorClass = 'text-red-600'
              }
            }
          }
          
          const arrowIcon = change > 0 ? '↑' : change < 0 ? '↓' : '→'
          
          return (
            <div key={label} className="stat-card">
              <div className="flex items-start justify-between">
                <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center', bg)}>
                  <Icon size={18} className={color} />
                </div>
                <div className="text-right">
                  <span className={`text-[10px] font-semibold ${colorClass}`}>
                    {arrowIcon} {Math.abs(change)}
                  </span>
                </div>
              </div>
              <p className="text-4xl font-bold text-gray-900 mt-2">{displayValue}</p>
              <p className="text-sm text-gray-500 font-semibold">{label}</p>
              <p className={`text-[10px] font-semibold ${colorClass}`}>
                {change > 0 ? '+' : change < 0 ? '-' : '='}{Math.abs(change)} since {periodLabel}
              </p>
            </div>
          )
        })}
      </div>

      {/* Channel Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Graph: 3/4 width */}
        <div className="lg:col-span-3 card p-6">
          <div className="mb-6">
            <h2 className="text-lg font-bold text-gray-900">Channel Performance</h2>
            <p className="text-xs text-gray-500 mt-1">Message throughput (solid = received, dotted = responded)</p>
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
              <Line 
                type="natural"
                dataKey="instagram"
                name="Instagram"
                stroke="#ec4899" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: '#ec4899', fillOpacity: 1 }}
                isAnimationActive={true}
              />
              <Line 
                type="natural"
                dataKey="instagram_resp"
                name="Instagram (Responded)"
                stroke="#ec4899" 
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#ec4899', fillOpacity: 1 }}
              />
              {/* WhatsApp */}
              <Line 
                type="natural"
                dataKey="whatsapp"
                name="WhatsApp"
                stroke="#22c55e" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: '#22c55e', fillOpacity: 1 }}
              />
              <Line 
                type="natural"
                dataKey="whatsapp_resp"
                name="WhatsApp (Responded)"
                stroke="#22c55e" 
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#22c55e', fillOpacity: 1 }}
              />
              {/* Facebook */}
              <Line 
                type="natural"
                dataKey="facebook"
                name="Facebook"
                stroke="#3b82f6" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: '#3b82f6', fillOpacity: 1 }}
              />
              <Line 
                type="natural"
                dataKey="facebook_resp"
                name="Facebook (Responded)"
                stroke="#3b82f6" 
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#3b82f6', fillOpacity: 1 }}
              />
              {/* TikTok */}
              <Line 
                type="natural"
                dataKey="tiktok"
                name="TikTok"
                stroke="#111111" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: '#111111', fillOpacity: 1 }}
              />
              <Line 
                type="natural"
                dataKey="tiktok_resp"
                name="TikTok (Responded)"
                stroke="#111111" 
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#111111', fillOpacity: 1 }}
              />
            </LineChart>
          </ResponsiveContainer>
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-6 mt-5">
            <div className="flex items-center gap-2">
              <svg width="20" height="2" className="inline"><line x1="0" y1="1" x2="20" y2="1" stroke="#ec4899" strokeWidth="2.5" /></svg>
              <span className="text-xs text-gray-600 font-medium">Instagram</span>
            </div>
            <div className="flex items-center gap-2">
              <svg width="20" height="2" className="inline"><line x1="0" y1="1" x2="20" y2="1" stroke="#22c55e" strokeWidth="2.5" /></svg>
              <span className="text-xs text-gray-600 font-medium">WhatsApp</span>
            </div>
            <div className="flex items-center gap-2">
              <svg width="20" height="2" className="inline"><line x1="0" y1="1" x2="20" y2="1" stroke="#3b82f6" strokeWidth="2.5" /></svg>
              <span className="text-xs text-gray-600 font-medium">Facebook</span>
            </div>
            <div className="flex items-center gap-2">
              <svg width="20" height="2" className="inline"><line x1="0" y1="1" x2="20" y2="1" stroke="#111111" strokeWidth="2.5" /></svg>
              <span className="text-xs text-gray-600 font-medium">TikTok</span>
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
                <p className={`text-xs ${colors.text} mt-1 opacity-75`}>+15% this week</p>
              </div>
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
              <div key={item.id} className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0">
                <div className="mt-0.5 shrink-0 w-5 h-5 rounded-lg bg-gray-50 flex items-center justify-center flex-shrink-0">
                  {channelIcon(item.channel)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800 leading-relaxed">{item.text}</p>
                </div>
                <span className="text-xs text-gray-400 shrink-0 font-medium whitespace-nowrap ml-2">{item.time}</span>
              </div>
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
    </div>
  )
}
