import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { analyticsData } from '../data/mock'

// Brand palette for charts
const BRAND_COLORS  = ['#ff5900', '#ff7733', '#ff9966', '#ffbb99', '#ffddcc', '#fff0e8']
const CHANNEL_COLORS = ['#ec4899', '#22c55e', '#f97316', '#1877F2', '#60a5fa', '#000000']

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
  const { intentBreakdown, topProducts, weeklyMessages, channelSplit, aiPerformance } = analyticsData

  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
        <p className="text-sm text-gray-500 mt-0.5">Customer behaviour, AI performance, and channel insights</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: 'Avg Response Time', value: aiPerformance.avgResponseTime, color: 'text-green-600'  },
          { label: 'AI Success Rate',   value: aiPerformance.successRate,      color: 'text-brand-500' },
          { label: 'Override Rate',     value: aiPerformance.overrideRate,     color: 'text-amber-500' },
        ].map(k => (
          <div key={k.label} className="stat-card text-center">
            <p className={`text-4xl font-bold ${k.color}`}>{k.value}</p>
            <p className="text-xs text-gray-500 font-semibold mt-1">{k.label}</p>
          </div>
        ))}
      </div>

      {/* Weekly bar chart */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4">Messages This Week</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={weeklyMessages} barGap={4}>
            <XAxis dataKey="day" tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'Quicksand', fontWeight: 600 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 11, fontFamily: 'Quicksand' }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12, fontFamily: 'Quicksand', fontWeight: 600 }} />
            <Bar dataKey="messages" name="Inbound"    fill="#e5e7eb" radius={[6,6,0,0]} />
            <Bar dataKey="replies"  name="AI Replied" fill="#ff5900" radius={[6,6,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Intent breakdown */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Top Customer Intents</h2>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={intentBreakdown} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                {intentBreakdown.map((_, i) => <Cell key={i} fill={BRAND_COLORS[i % BRAND_COLORS.length]} />)}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">
            {intentBreakdown.map((item, i) => (
              <div key={item.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: BRAND_COLORS[i] }} />
                  <span className="text-gray-600 font-medium">{item.name}</span>
                </div>
                <span className="text-gray-900 font-bold">{item.value}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Channel split */}
        <div className="card p-5">
          <h2 className="text-sm font-bold text-gray-900 mb-4">Channel Split</h2>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={channelSplit} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                {channelSplit.map((_, i) => <Cell key={i} fill={CHANNEL_COLORS[i % CHANNEL_COLORS.length]} />)}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-2">
            {channelSplit.map((item, i) => (
              <div key={item.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: CHANNEL_COLORS[i] }} />
                  <span className="text-gray-600 font-medium">{item.name}</span>
                </div>
                <span className="text-gray-900 font-bold">{item.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top products */}
      <div className="card p-5">
        <h2 className="text-sm font-bold text-gray-900 mb-4">Most Asked-About Products</h2>
        <div className="space-y-3">
          {topProducts.map((p, i) => (
            <div key={p.name} className="flex items-center gap-3">
              <span className="text-xs text-gray-400 font-bold w-4">{i + 1}</span>
              <div className="flex-1">
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-gray-800 font-semibold">{p.name}</span>
                  <span className="text-gray-500 font-medium">{p.queries} queries</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-500 rounded-full transition-all"
                    style={{ width: `${(p.queries / topProducts[0].queries) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
