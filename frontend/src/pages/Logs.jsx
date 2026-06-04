import { useState, useEffect, useCallback } from 'react'
import { CheckCircle, Info, AlertTriangle, XCircle, Search, Loader2, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

const levelConfig = {
  success: { icon: CheckCircle,  color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-200'  },
  info:    { icon: Info,          color: 'text-blue-600',   bg: 'bg-blue-50',   border: 'border-blue-200'   },
  warning: { icon: AlertTriangle, color: 'text-amber-600',  bg: 'bg-amber-50',  border: 'border-amber-200'  },
  error:   { icon: XCircle,       color: 'text-red-600',    bg: 'bg-red-50',    border: 'border-red-200'    },
}

const levels = ['all', 'info', 'warning', 'error']
const sources = [
  { value: '', label: 'All Sources' },
  { value: 'services', label: 'Services' },
  { value: 'handoff', label: 'Handoff' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'api', label: 'API' },
]

export default function Logs() {
  const [userRole, setUserRole] = useState(null)
  const [logType, setLogType] = useState(null) // Start as null, set after role check
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [sourceOpen, setSourceOpen] = useState(false)
  const [daysFilter, setDaysFilter] = useState(null) // null = all time, 1 = 24h, 7 = 7 days, etc

  // Determine user role and default log type
  useEffect(() => {
    const checkRole = async () => {
      try {
        const res = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
        })
        if (res.ok) {
          const data = await res.json()
          setUserRole(data.role)
          // Default: admins see system, supervisors see audit, agents see me
          let defaultType = 'me'
          if (data.role === 'admin') {
            defaultType = 'system'
          } else if (data.role === 'supervisor') {
            defaultType = 'audit'
          }
          setLogType(defaultType)
        }
      } catch (err) {
        console.error('Failed to check role:', err)
      }
    }
    checkRole()
  }, [])

  // Fetch logs
  const fetchLogs = useCallback(async () => {
    if (!logType) return
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('page', 1)
      params.set('per_page', 100)
      if (search) params.set('search', search)
      if (filter !== 'all' && logType === 'system') params.set('level', filter)
      if (sourceFilter && logType === 'system') params.set('source', sourceFilter)
      
      // Add days filter
      if (daysFilter) {
        params.set('days', daysFilter)
      }

      const endpoint = `/api/logs/${logType}`
      const res = await fetch(`${endpoint}?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Failed to load logs')
      }

      const data = await res.json()
      setLogs(data.logs || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [logType, search, filter, sourceFilter, daysFilter])

  useEffect(() => {
    fetchLogs()
  }, [logType, search, filter, sourceFilter, daysFilter, fetchLogs])

  const filtered = logs.filter(log => {
    // Only apply level filter for system logs
    if (logType === 'system') {
      if (filter === 'all') return true
      return log.level === filter
    }
    // For audit and me logs, show all
    return true
  })

  return (
    <div className="space-y-5 w-full max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Logs</h1>
        <p className="text-sm text-gray-500 mt-0.5">Full pipeline audit trail — webhooks, AI calls, API responses</p>
      </div>

      {/* Log type tabs */}
      {userRole && logType && (
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 w-fit">
          {userRole === 'admin' && (
            <button
              onClick={() => {
                setLogType('system')
                setFilter('all')
                setSourceFilter('')
              }}
              className={clsx(
                'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
                logType === 'system' ? 'bg-gray-900 text-white' : 'text-gray-600 hover:text-gray-900'
              )}
            >
              System
            </button>
          )}
          {(userRole === 'supervisor' || userRole === 'admin') && (
            <button
              onClick={() => {
                setLogType('audit')
                setFilter('all')
                setSourceFilter('')
              }}
              className={clsx(
                'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
                logType === 'audit' ? 'bg-gray-900 text-white' : 'text-gray-600 hover:text-gray-900'
              )}
            >
              Audit
            </button>
          )}
          <button
            onClick={() => {
              setLogType('me')
              setFilter('all')
              setSourceFilter('')
            }}
            className={clsx(
              'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
              logType === 'me' ? 'bg-gray-900 text-white' : 'text-gray-600 hover:text-gray-900'
            )}
          >
            My Logs
          </button>
        </div>
      )}

      {/* Filters — stack on mobile, row on sm+ */}
      {(logType === 'system' || logType === 'audit') && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
          {/* Level filter — only for system logs */}
          {logType === 'system' && (
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
          )}

          {/* Source filter dropdown — only for system logs */}
          {logType === 'system' && (
            <div className="relative shrink-0">
              <button
                onClick={() => setSourceOpen(!sourceOpen)}
                className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold text-gray-500 bg-white border border-gray-200 shadow-sm hover:text-gray-800 transition-colors whitespace-nowrap"
              >
                {sources.find(s => s.value === sourceFilter)?.label || 'All Sources'}
                <ChevronDown size={12} className={clsx('transition-transform', sourceOpen && 'rotate-180')} />
              </button>
              {sourceOpen && (
                <div className="absolute top-full mt-1 right-0 bg-white border border-gray-200 rounded-lg shadow-md z-10 min-w-max">
                  {sources.map(source => (
                    <button
                      key={source.value}
                      onClick={() => {
                        setSourceFilter(source.value)
                        setSourceOpen(false)
                      }}
                      className={clsx(
                        'block w-full text-left px-3 py-2 text-xs font-medium transition-colors first:rounded-t-lg last:rounded-b-lg',
                        sourceFilter === source.value
                          ? 'bg-brand-50 text-brand-600'
                          : 'text-gray-700 hover:bg-gray-50'
                      )}
                    >
                      {source.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Date filter presets — show for all log types */}
          <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm overflow-x-auto shrink-0">
            <button
              onClick={() => setDaysFilter(null)}
              className={clsx(
                'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
                daysFilter === null ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
              )}
            >
              All Time
            </button>
            <button
              onClick={() => setDaysFilter(1)}
              className={clsx(
                'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
                daysFilter === 1 ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
              )}
            >
              24 Hours
            </button>
            <button
              onClick={() => setDaysFilter(7)}
              className={clsx(
                'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
                daysFilter === 7 ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
              )}
            >
              7 Days
            </button>
            <button
              onClick={() => setDaysFilter(30)}
              className={clsx(
                'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
                daysFilter === 30 ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
              )}
            >
              30 Days
            </button>
          </div>

          <div className="relative flex-1 sm:max-w-xs ml-auto">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="input w-full pl-8 text-xs"
              placeholder="Search logs…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
      )}
      {logType === 'me' && (
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm overflow-x-auto w-fit">
          <button
            onClick={() => setDaysFilter(null)}
            className={clsx(
              'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
              daysFilter === null ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
            )}
          >
            All Time
          </button>
          <button
            onClick={() => setDaysFilter(1)}
            className={clsx(
              'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
              daysFilter === 1 ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
            )}
          >
            24 Hours
          </button>
          <button
            onClick={() => setDaysFilter(7)}
            className={clsx(
              'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
              daysFilter === 7 ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
            )}
          >
            7 Days
          </button>
          <button
            onClick={() => setDaysFilter(30)}
            className={clsx(
              'px-2.5 sm:px-3 py-1 rounded-md text-xs font-semibold whitespace-nowrap transition-colors',
              daysFilter === 30 ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
            )}
          >
            30 Days
          </button>
        </div>
      )}

      {/* Log entries */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-brand-500" />
          </div>
        ) : error ? (
          <div className="px-4 py-8 text-center text-xs text-red-600">{error}</div>
        ) : (
          <div className="divide-y divide-gray-50">
            {filtered.map(log => {
              const level = log.level || 'info'
              const cfg = levelConfig[level]
              const Icon = cfg.icon
              const createdAt = log.created_at ? new Date(log.created_at) : null
              const time = createdAt ? createdAt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '—'

              return (
                <div key={log.id} className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors">
                  <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 border', cfg.bg, cfg.border)}>
                    <Icon size={13} className={cfg.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-mono text-gray-400 font-semibold">{time}</span>
                      <span className={clsx('badge text-xs border', cfg.bg, cfg.color, cfg.border)}>{level}</span>
                      {log.source && <span className="text-xs font-mono text-brand-600 font-semibold">{log.source}</span>}
                    </div>
                    <p className="text-xs text-gray-700 leading-relaxed font-medium">{log.message || log.action || '—'}</p>
                    {log.user && (
                      <p className="text-xs text-gray-500 mt-1">by {log.user.full_name}</p>
                    )}
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
        )}
      </div>

      <p className="text-xs text-gray-400 text-center font-medium">
        Showing {filtered.length} entries
      </p>
    </div>
  )
}
