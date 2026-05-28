import { useState } from 'react'
import { logs } from '../data/mock'
import { CheckCircle, Info, AlertTriangle, XCircle, Search } from 'lucide-react'
import clsx from 'clsx'

const levelConfig = {
  success: { icon: CheckCircle,  color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-200'  },
  info:    { icon: Info,          color: 'text-blue-600',   bg: 'bg-blue-50',   border: 'border-blue-200'   },
  warning: { icon: AlertTriangle, color: 'text-amber-600',  bg: 'bg-amber-50',  border: 'border-amber-200'  },
  error:   { icon: XCircle,       color: 'text-red-600',    bg: 'bg-red-50',    border: 'border-red-200'    },
}

const levels = ['all', 'success', 'info', 'warning', 'error']

export default function Logs() {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  const filtered = logs.filter(l => {
    const matchLevel  = filter === 'all' || l.level === filter
    const matchSearch = !search || l.message.toLowerCase().includes(search.toLowerCase()) || l.source.toLowerCase().includes(search.toLowerCase())
    return matchLevel && matchSearch
  })

  return (
    <div className="space-y-5 w-full max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Logs</h1>
        <p className="text-sm text-gray-500 mt-0.5">Full pipeline audit trail — webhooks, AI calls, API responses</p>
      </div>

      {/* Filters — stack on mobile, row on sm+ */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
        <div className="relative flex-1 sm:max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input w-full pl-8 text-xs"
            placeholder="Search logs…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        {/* Level filter — scrollable on mobile */}
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm overflow-x-auto shrink-0">
          {levels.map(l => (
            <button
              key={l}
              onClick={() => setFilter(l)}
              className={clsx(
                'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold capitalize transition-colors whitespace-nowrap',
                filter === l ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
              )}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Log entries */}
      <div className="card overflow-hidden">
        <div className="divide-y divide-gray-50">
          {filtered.map(log => {
            const cfg = levelConfig[log.level]
            const Icon = cfg.icon
            return (
              <div key={log.id} className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors">
                <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 border', cfg.bg, cfg.border)}>
                  <Icon size={13} className={cfg.color} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-mono text-gray-400 font-semibold">{log.time}</span>
                    <span className={clsx('badge text-xs border', cfg.bg, cfg.color, cfg.border)}>{log.level}</span>
                    <span className="text-xs font-mono text-brand-600 font-semibold">{log.source}</span>
                  </div>
                  <p className="text-xs text-gray-700 leading-relaxed font-medium">{log.message}</p>
                </div>
              </div>
            )
          })}

          {filtered.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-400 font-medium">
              No logs match your filter
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-400 text-center font-medium">
        Showing {filtered.length} of {logs.length} entries · Auto-refreshes every 10s
      </p>
    </div>
  )
}
