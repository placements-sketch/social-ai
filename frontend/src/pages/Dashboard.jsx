import { stats, activityFeed, alerts } from '../data/mock'
import {
  MessageSquare, Bot, UserCheck, XCircle, PackageX,
  AlertTriangle, AlertCircle, Info, Instagram, Smartphone, ShoppingBag, TrendingUp,
} from 'lucide-react'
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
  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">Live overview of your AI support system</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="stat-card">
            <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center', bg)}>
              <Icon size={18} className={color} />
            </div>
            <p className="text-3xl font-bold text-gray-900 mt-2">{value}</p>
            <p className="text-xs text-gray-500 font-medium">{label}</p>
          </div>
        ))}
      </div>

      {/* Channel Performance */}
      <div className="card p-6">
        <div className="mb-5">
          <h2 className="text-lg font-bold text-gray-900">Channel Performance</h2>
          <p className="text-xs text-gray-500 mt-1">Message throughput across platforms</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { name: 'Instagram', icon: Instagram, color: 'text-pink-500', messages: 24, total: 30 },
            { name: 'WhatsApp', icon: Smartphone, color: 'text-green-500', messages: 18, total: 25 },
            { name: 'Facebook', icon: null, color: 'text-blue-600', messages: 12, total: 20, fbIcon: true },
            { name: 'TikTok', icon: null, color: 'text-gray-900', messages: 8, total: 15, tikIcon: true },
          ].map((channel) => {
            const percentage = Math.round((channel.messages / channel.total) * 100)
            let Icon = channel.icon
            return (
              <div key={channel.name} className="p-3 rounded-lg bg-white border border-gray-100 transition-all hover:border-gray-200">
                {/* Channel name + percentage */}
                <div className="flex items-center justify-between mb-2.5">
                  <div className="flex items-center gap-2">
                    {channel.fbIcon ? (
                      <span className="inline-flex items-center justify-center w-4 h-4 rounded text-white font-black text-[8px]" style={{ background: '#1877F2' }}>f</span>
                    ) : channel.tikIcon ? (
                      <span className="inline-flex items-center justify-center w-4 h-4 rounded text-white font-black text-[7px]" style={{ background: '#000000' }}>♪</span>
                    ) : (
                      <Icon size={14} className={channel.color} />
                    )}
                    <span className="text-xs font-semibold text-gray-900">{channel.name}</span>
                  </div>
                  <span className="text-xs font-bold text-gray-900">{percentage}%</span>
                </div>

                {/* Progress bar */}
                <div className="w-full h-1 bg-gray-200 rounded-full overflow-hidden mb-2">
                  <div
                    className="h-full bg-gray-900 rounded-full transition-all duration-500"
                    style={{ width: `${percentage}%` }}
                  />
                </div>

                {/* Message count */}
                <p className="text-xs text-gray-500 font-medium">{channel.messages} of {channel.total}</p>
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
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
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
                { label: 'Purchases', value: 42, total: 156, color: 'bg-gray-900' },
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
