import { stats, activityFeed, alerts } from '../data/mock'
import {
  MessageSquare, Bot, UserCheck, XCircle, PackageX,
  AlertTriangle, AlertCircle, Info, Instagram, Smartphone, ShoppingBag, TrendingUp,
  Download, FileText, File,
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import clsx from 'clsx'

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
    return <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded text-white font-black text-[9px]" style={{ background: '#000000' }}>♪</span>
  if (ch === 'shopify')        return <ShoppingBag size={13} className="text-emerald-500" />
  if (ch === 'alert')          return <AlertTriangle size={13} className="text-amber-500" />
  return <Bot size={13} className="text-brand-500" />
}

export default function Dashboard() {
  // Export functions
  const exportToCSV = () => {
    const headers = ['Metric', 'Value']
    const rows = [
      ['Messages Today', stats.messagesToday],
      ['Auto-Replies Sent', stats.autoRepliesSent],
      ['Human Overrides', stats.humanOverrides],
      ['Failed Responses', stats.failedResponses],
      ['Out-of-Stock Queries', stats.outOfStockQueries],
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
    const rows = [
      ['Messages Today', stats.messagesToday],
      ['Auto-Replies Sent', stats.autoRepliesSent],
      ['Human Overrides', stats.humanOverrides],
      ['Failed Responses', stats.failedResponses],
      ['Out-of-Stock Queries', stats.outOfStockQueries],
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
        {statCards.map(({ label, value, icon: Icon, color, bg }) => {
          const isPositive = true // Default to positive, can be made dynamic
          return (
            <div key={label} className="stat-card">
              <div className="flex items-start justify-between">
                <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center', bg)}>
                  <Icon size={18} className={color} />
                </div>
                <div className="text-right">
                  <span className="text-[10px] font-semibold text-green-600">↑ 12%</span>
                </div>
              </div>
              <p className="text-3xl font-bold text-gray-900 mt-2">{value}</p>
              <p className="text-xs text-gray-500 font-medium">{label}</p>
              <p className={clsx('text-[10px] font-semibold', isPositive ? 'text-green-600' : 'text-brand-600')}>
                {isPositive ? '+' : '-'}24 since yesterday
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
            <LineChart data={[
              { time: 'Mon', instagram: 12, instagram_resp: 10, whatsapp: 8, whatsapp_resp: 7, facebook: 15, facebook_resp: 12, tiktok: 5, tiktok_resp: 4 },
              { time: 'Tue', instagram: 18, instagram_resp: 15, whatsapp: 14, whatsapp_resp: 11, facebook: 12, facebook_resp: 10, tiktok: 9, tiktok_resp: 7 },
              { time: 'Wed', instagram: 15, instagram_resp: 12, whatsapp: 11, whatsapp_resp: 9, facebook: 22, facebook_resp: 18, tiktok: 7, tiktok_resp: 5 },
              { time: 'Thu', instagram: 28, instagram_resp: 24, whatsapp: 19, whatsapp_resp: 16, facebook: 18, facebook_resp: 15, tiktok: 14, tiktok_resp: 11 },
              { time: 'Fri', instagram: 22, instagram_resp: 19, whatsapp: 26, whatsapp_resp: 23, facebook: 25, facebook_resp: 21, tiktok: 11, tiktok_resp: 9 },
              { time: 'Sat', instagram: 32, instagram_resp: 28, whatsapp: 21, whatsapp_resp: 18, facebook: 16, facebook_resp: 13, tiktok: 18, tiktok_resp: 15 },
              { time: 'Sun', instagram: 26, instagram_resp: 23, whatsapp: 18, whatsapp_resp: 15, facebook: 28, facebook_resp: 24, tiktok: 13, tiktok_resp: 10 },
            ]} margin={{ top: 20, right: 20, left: -20, bottom: 5 }}>
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
              <Tooltip 
                contentStyle={{
                  background: '#ffffff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '12px',
                  boxShadow: '0 8px 20px rgba(0,0,0,0.08)',
                  padding: '12px'
                }}
                labelStyle={{ color: '#1f2937', fontWeight: 600, fontSize: 12, marginBottom: '6px', fontFamily: 'Quicksand' }}
                formatter={(value) => [`${value} msgs`, '']}
                contentClassName="text-xs"
              />
              {/* Instagram */}
              <Line 
                type="natural"
                dataKey="instagram" 
                stroke="#ec4899" 
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 6, fill: '#ec4899', fillOpacity: 1 }}
                isAnimationActive={true}
              />
              <Line 
                type="natural"
                dataKey="instagram_resp" 
                stroke="#ec4899" 
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#ec4899', fillOpacity: 1 }}
              />
              {/* WhatsApp */}
              <Line 
                type="natural"
                dataKey="whatsapp" 
                stroke="#22c55e" 
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 6, fill: '#22c55e', fillOpacity: 1 }}
              />
              <Line 
                type="natural"
                dataKey="whatsapp_resp" 
                stroke="#22c55e" 
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#22c55e', fillOpacity: 1 }}
              />
              {/* Facebook */}
              <Line 
                type="natural"
                dataKey="facebook" 
                stroke="#3b82f6" 
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 6, fill: '#3b82f6', fillOpacity: 1 }}
              />
              <Line 
                type="natural"
                dataKey="facebook_resp" 
                stroke="#3b82f6" 
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#3b82f6', fillOpacity: 1 }}
              />
              {/* TikTok */}
              <Line 
                type="natural"
                dataKey="tiktok" 
                stroke="#000000" 
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 6, fill: '#000000', fillOpacity: 1 }}
              />
              <Line 
                type="natural"
                dataKey="tiktok_resp" 
                stroke="#000000" 
                strokeWidth={2.5}
                strokeDasharray="6 3"
                dot={false}
                activeDot={{ r: 6, fill: '#000000', fillOpacity: 1 }}
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
              <svg width="20" height="2" className="inline"><line x1="0" y1="1" x2="20" y2="1" stroke="#000000" strokeWidth="2.5" /></svg>
              <span className="text-xs text-gray-600 font-medium">TikTok</span>
            </div>
          </div>
        </div>

        {/* Stats: 1/4 width - each in own card */}
        <div className="lg:col-span-1 space-y-3">
          <div className="card bg-pink-50 border border-pink-100 p-4">
            <p className="text-[11px] text-pink-600 font-semibold uppercase tracking-wider">Instagram</p>
            <p className="text-2xl font-bold text-pink-600 mt-2">186</p>
            <p className="text-xs text-pink-500 mt-1">+15% this week</p>
          </div>
          <div className="card bg-green-50 border border-green-100 p-4">
            <p className="text-[11px] text-green-600 font-semibold uppercase tracking-wider">WhatsApp</p>
            <p className="text-2xl font-bold text-green-600 mt-2">137</p>
            <p className="text-xs text-green-500 mt-1">+8% this week</p>
          </div>
          <div className="card bg-blue-50 border border-blue-100 p-4">
            <p className="text-[11px] text-blue-600 font-semibold uppercase tracking-wider">Facebook</p>
            <p className="text-2xl font-bold text-blue-600 mt-2">152</p>
            <p className="text-xs text-blue-500 mt-1">+22% this week</p>
          </div>
          <div className="card bg-gray-50 border border-gray-200 p-4">
            <p className="text-[11px] text-gray-600 font-semibold uppercase tracking-wider">TikTok</p>
            <p className="text-2xl font-bold text-gray-900 mt-2">87</p>
            <p className="text-xs text-gray-500 mt-1">+14% this week</p>
          </div>
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
            {activityFeed.map((item) => (
              <div key={item.id} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
                <div className="mt-0.5 shrink-0 w-6 h-6 rounded-lg bg-gray-50 flex items-center justify-center">
                  {channelIcon(item.channel)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-700 leading-snug">{item.text}</p>
                </div>
                <span className="text-xs text-gray-400 shrink-0 font-medium">{item.time}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Alerts + quick stats */}
        <div className="space-y-4">
          <div className="card p-5">
            <h2 className="text-sm font-bold text-gray-900 mb-3">System Alerts</h2>
            <div className="space-y-2.5">
              {alerts.map((alert) => {
                const { icon: Icon, cls } = alertStyles[alert.level]
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
