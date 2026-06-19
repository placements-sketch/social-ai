import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell, CheckCheck, Filter, Clock, AlertOctagon, AlertTriangle, Info,
  Radio, Package, UserPlus, UserCheck, Trash2, Users as UsersIcon,
  Shield, ShieldAlert, Zap, Bot, MessageSquare, CheckCircle,
  Settings as SettingsIcon,
} from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { fetchNotifications, markNotificationRead, markAllNotificationsRead } from '../api/notifications'
import { useTimeAgo } from '../hooks/useTimeAgo'

// Same mapping as TopBar so the icons stay consistent.
function notifVisuals(type, severity) {
  const sevColor = severity === 'urgent'
    ? { color: 'text-red-600', bg: 'bg-red-50' }
    : severity === 'warning'
      ? { color: 'text-amber-600', bg: 'bg-amber-50' }
      : null

  const typeMap = {
    assigned:                       { Icon: UserCheck,     color: 'text-brand-600', bg: 'bg-orange-50' },
    reassigned:                     { Icon: UserCheck,     color: 'text-brand-600', bg: 'bg-orange-50' },
    unassigned:                     { Icon: AlertTriangle, color: 'text-amber-500', bg: 'bg-amber-50'  },
    conversation_escalated:         { Icon: AlertOctagon,  color: 'text-red-600',   bg: 'bg-red-50'    },
    conversation_resolved:          { Icon: CheckCircle,   color: 'text-green-600', bg: 'bg-green-50'  },
    new_inbound_on_my_conversation: { Icon: MessageSquare, color: 'text-blue-600',  bg: 'bg-blue-50'   },
    channel_toggled:                { Icon: Radio,         color: 'text-purple-600',bg: 'bg-purple-50' },
    channel_test_failed:            { Icon: Radio,         color: 'text-red-600',   bg: 'bg-red-50'    },
    channel_token_expiring:         { Icon: Radio,         color: 'text-amber-600', bg: 'bg-amber-50'  },
    shopify_sync_completed:         { Icon: Package,       color: 'text-emerald-600', bg: 'bg-emerald-50' },
    shopify_sync_failed:            { Icon: Package,       color: 'text-red-600',   bg: 'bg-red-50'    },
    shopify_check_failed:           { Icon: Package,       color: 'text-red-600',   bg: 'bg-red-50'    },
    user_created:                   { Icon: UserPlus,      color: 'text-blue-600',  bg: 'bg-blue-50'   },
    user_updated:                   { Icon: UsersIcon,     color: 'text-gray-700',  bg: 'bg-gray-100'  },
    user_deleted:                   { Icon: Trash2,        color: 'text-red-600',   bg: 'bg-red-50'    },
    your_account_changed:           { Icon: ShieldAlert,   color: 'text-amber-600', bg: 'bg-amber-50'  },
    automation_rule_created:        { Icon: Zap,           color: 'text-brand-600', bg: 'bg-orange-50' },
    automation_rule_updated:        { Icon: Zap,           color: 'text-brand-600', bg: 'bg-orange-50' },
    automation_rule_deleted:        { Icon: Zap,           color: 'text-red-600',   bg: 'bg-red-50'    },
    automation_rule_toggled:        { Icon: Zap,           color: 'text-gray-600',  bg: 'bg-gray-100'  },
    ai_settings_changed:            { Icon: Bot,           color: 'text-brand-600', bg: 'bg-orange-50' },
    ai_settings_reset:              { Icon: Bot,           color: 'text-amber-600', bg: 'bg-amber-50'  },
    webhook_signature_failed:       { Icon: Shield,        color: 'text-red-600',   bg: 'bg-red-50'    },
  }
  const fallback = { Icon: Bell, color: 'text-gray-500', bg: 'bg-gray-50' }
  const base = typeMap[type] || fallback
  if (sevColor) return { Icon: base.Icon, ...sevColor }
  return base
}

// Group buckets by day (same logic as TopBar — keep them in sync visually)
function groupByDay(notifs) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1)
  const weekAgo = new Date(today); weekAgo.setDate(weekAgo.getDate() - 7)

  const groups = {
    today:     { label: 'Today',             notifs: [] },
    yesterday: { label: 'Yesterday',         notifs: [] },
    week:      { label: 'Earlier this week', notifs: [] },
    older:     { label: 'Older',             notifs: [] },
  }
  for (const n of notifs) {
    if (!n.created_at) { groups.older.notifs.push(n); continue }
    const c = new Date(n.created_at)
    if (c >= today) groups.today.notifs.push(n)
    else if (c >= yesterday) groups.yesterday.notifs.push(n)
    else if (c >= weekAgo) groups.week.notifs.push(n)
    else groups.older.notifs.push(n)
  }
  return Object.values(groups).filter(g => g.notifs.length > 0)
}

function NotificationRow({ notif, onClick }) {
  const timeAgo = useTimeAgo(notif.created_at)
  const { Icon, color, bg } = notifVisuals(notif.type, notif.severity)

  const dotColor =
    notif.severity === 'urgent' ? 'bg-red-500'
    : notif.severity === 'warning' ? 'bg-amber-500'
    : 'bg-blue-500'

  return (
    <button
      onClick={() => onClick(notif)}
      className={clsx(
        'w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors',
        !notif.read && 'bg-blue-50/30'
      )}
    >
      <div className="flex items-start gap-3">
        <div className={clsx('w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5', bg)}>
          <Icon size={16} className={color} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-bold text-gray-900">{notif.title}</p>
            {!notif.read && <span className={clsx('w-2 h-2 rounded-full shrink-0 mt-1.5', dotColor)} />}
          </div>
          {notif.body && (
            <p className="text-xs text-gray-600 mt-1 leading-snug">{notif.body}</p>
          )}
          <div className="flex items-center gap-2 mt-2">
            <span className="text-[10px] text-gray-400 font-medium">{timeAgo}</span>
            <span className="text-[10px] text-gray-300">·</span>
            <span className="text-[10px] text-gray-500 font-medium capitalize">
              {(notif.type || '').replace(/_/g, ' ')}
            </span>
            {notif.severity && notif.severity !== 'info' && (
              <>
                <span className="text-[10px] text-gray-300">·</span>
                <span className={clsx(
                  'text-[10px] font-bold uppercase',
                  notif.severity === 'urgent' ? 'text-red-600' : 'text-amber-600'
                )}>
                  {notif.severity}
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

export default function Notifications() {
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [unreadCount, setUnreadCount] = useState(0)
  const navigate = useNavigate()

  // Filters
  const [readFilter, setReadFilter] = useState('all')          // 'all' | 'unread' | 'read'
  const [severityFilter, setSeverityFilter] = useState('all') // 'all' | 'urgent' | 'warning' | 'info'
  const [daysFilter, setDaysFilter] = useState(7)             // 7 | 14 | 30

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchNotifications({ limit: 100, days: daysFilter })
      setNotifications(data.notifications || [])
      setUnreadCount(data.unread_count || 0)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [daysFilter])

  useEffect(() => {
    load()
  }, [load])

  // Apply read + severity filters client-side
  const filtered = useMemo(() => {
    return notifications.filter(n => {
      if (readFilter === 'unread' && n.read) return false
      if (readFilter === 'read' && !n.read) return false
      if (severityFilter !== 'all' && (n.severity || 'info') !== severityFilter) return false
      return true
    })
  }, [notifications, readFilter, severityFilter])

  const grouped = useMemo(() => groupByDay(filtered), [filtered])

  const handleClick = async (n) => {
    if (!n.read) {
      setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, read: true } : x))
      setUnreadCount(c => Math.max(0, c - 1))
      try { await markNotificationRead(n.id) } catch { /* ignore */ }
    }
    if (n.resource_type === 'conversation' && n.resource_id) {
      navigate(`/messages?conversation=${n.resource_id}`)
    }
  }

  const handleMarkAllRead = async () => {
    setNotifications(prev => prev.map(x => ({ ...x, read: true })))
    setUnreadCount(0)
    try { await markAllNotificationsRead() } catch { /* ignore */ }
  }

  if (loading) {
    return (
      <div className="space-y-6 w-full">
        <SkeletonHeader />
        <SkeletonList count={6} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
            <span className="text-gray-300 mx-1.5">·</span>
            <span>showing {filtered.length} of {notifications.length}</span>
          </p>
        </div>
        {unreadCount > 0 && (
          <button
            onClick={handleMarkAllRead}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-800 transition-colors"
          >
            <CheckCheck size={14} /> Mark all read
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        {/* Read filter */}
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm shrink-0">
          {[
            { key: 'all',    label: 'All' },
            { key: 'unread', label: 'Unread' },
            { key: 'read',   label: 'Read' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setReadFilter(key)}
              className={clsx(
                'px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
                readFilter === key ? 'bg-black text-white' : 'text-gray-600 hover:text-gray-900'
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Severity filter */}
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm shrink-0">
          {[
            { key: 'all',     label: 'Any',     Icon: Filter },
            { key: 'urgent',  label: 'Urgent',  Icon: AlertOctagon },
            { key: 'warning', label: 'Warning', Icon: AlertTriangle },
            { key: 'info',    label: 'Info',    Icon: Info },
          ].map(({ key, label, Icon }) => (
            <button
              key={key}
              onClick={() => setSeverityFilter(key)}
              className={clsx(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors',
                severityFilter === key ? 'bg-black text-white' : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <Icon size={12} /> {label}
            </button>
          ))}
        </div>

        {/* Days filter */}
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 shadow-sm shrink-0">
          {[
            { key: 7,  label: '7 days'  },
            { key: 14, label: '14 days' },
            { key: 30, label: '30 days' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setDaysFilter(key)}
              className={clsx(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors whitespace-nowrap',
                daysFilter === key ? 'bg-black text-white' : 'text-gray-600 hover:text-gray-900'
              )}
            >
              <Clock size={12} /> {label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="bg-white border border-gray-100 rounded-2xl overflow-hidden shadow-sm">
        {grouped.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <Bell size={36} className="text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500 font-medium">
              {notifications.length === 0
                ? 'No notifications in this time window'
                : 'No notifications match these filters'}
            </p>
            {notifications.length > 0 && (
              <button
                onClick={() => { setReadFilter('all'); setSeverityFilter('all') }}
                className="mt-3 text-xs text-brand-600 hover:text-brand-700 font-semibold"
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          grouped.map(group => (
            <div key={group.label}>
              <div className="px-4 py-2 bg-gray-50/50 border-b border-gray-100">
                <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                  {group.label}
                </p>
              </div>
              {group.notifs.map(notif => (
                <NotificationRow key={notif.id} notif={notif} onClick={handleClick} />
              ))}
            </div>
          ))
        )}
      </div>

      <div className="bg-brand-50 border border-brand-100 rounded-xl p-3">
        <p className="text-xs text-brand-700 leading-relaxed font-medium">
          <strong>Tip:</strong> Notifications auto-prune after 7 days by default.
          Switch the time window above to see older items.
        </p>
      </div>
    </div>
  )
}