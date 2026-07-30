import { useState, useEffect, useRef } from 'react'
import { useToast } from './Toast'
import {
  Bell, Menu, LogOut, User, MessageSquare,
  AlertTriangle, CheckCircle, X, CheckCheck,
  Radio, Users as UsersIcon, Shield,
  Zap, Bot, Trash2, UserPlus, UserCheck, Package,
  AlertOctagon, Settings as SettingsIcon, ShieldAlert,
  Sun, Moon,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { ModalPortal } from '../context/ModalPortal'
import { fetchNotifications, markNotificationRead, markAllNotificationsRead } from '../api/notifications'
import { useTimeAgo } from '../hooks/useTimeAgo'
import clsx from 'clsx'
import { parseBackendTime } from '../utils/time'

// Group notifications by day for the modal display.
// Returns: [{ label: 'Today', notifs: [...] }, { label: 'Yesterday', notifs: [...] }, ...]
function groupNotifsByDay(notifs) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const weekAgo = new Date(today)
  weekAgo.setDate(weekAgo.getDate() - 7)

  const groups = {
    today: { label: 'Today', notifs: [] },
    yesterday: { label: 'Yesterday', notifs: [] },
    week: { label: 'Earlier this week', notifs: [] },
    older: { label: 'Older', notifs: [] },
  }

  for (const n of notifs) {
    if (!n.created_at) {
      groups.older.notifs.push(n)
      continue
    }
    const created = parseBackendTime(n.created_at)
    // `return false` here used to abandon the whole function on a single
    // unparseable timestamp, handing the caller a boolean where it expected
    // an array — one malformed row blanked the entire notifications list.
    // Treat it the same as a missing date: file it under Older and carry on.
    if (!created) {
      groups.older.notifs.push(n)
      continue
    }
    if (created >= today) groups.today.notifs.push(n)
    else if (created >= yesterday) groups.yesterday.notifs.push(n)
    else if (created >= weekAgo) groups.week.notifs.push(n)
    else groups.older.notifs.push(n)
  }

  return Object.values(groups).filter(g => g.notifs.length > 0)
}

// Icon + color mapping per notification type.
// Covers every type emitted by the backend (Phase 2 event coverage).
function notifVisuals(type, severity) {
  // Severity overrides color for urgent/warning regardless of type
  const sevColor = severity === 'urgent'
    ? { color: 'text-red-600', bg: 'bg-red-50' }
    : severity === 'warning'
      ? { color: 'text-amber-600', bg: 'bg-amber-50' }
      : null  // info uses type-specific color

  const typeMap = {
    // Conversation / messaging
    assigned:                       { Icon: UserCheck,     color: 'text-brand-600', bg: 'bg-brand-50' },
    reassigned:                     { Icon: UserCheck,     color: 'text-brand-600', bg: 'bg-brand-50' },
    unassigned:                     { Icon: AlertTriangle, color: 'text-amber-500', bg: 'bg-amber-50'  },
    conversation_escalated:         { Icon: AlertOctagon,  color: 'text-red-600',   bg: 'bg-red-50'    },
    conversation_resolved:          { Icon: CheckCircle,   color: 'text-green-600', bg: 'bg-green-50'  },
    new_inbound_on_my_conversation: { Icon: MessageSquare, color: 'text-blue-600',  bg: 'bg-blue-50'   },

    // Channels
    channel_toggled:           { Icon: Radio,    color: 'text-purple-600', bg: 'bg-purple-50' },
    channel_test_failed:       { Icon: Radio,    color: 'text-red-600',    bg: 'bg-red-50'    },
    channel_token_expiring:    { Icon: Radio,    color: 'text-amber-600',  bg: 'bg-amber-50'  },

    // Shopify
    shopify_sync_completed: { Icon: Package, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    shopify_sync_failed:    { Icon: Package, color: 'text-red-600',     bg: 'bg-red-50'     },
    shopify_check_failed:   { Icon: Package, color: 'text-red-600',     bg: 'bg-red-50'     },

    // Users
    user_created:          { Icon: UserPlus,   color: 'text-blue-600',  bg: 'bg-blue-50'  },
    user_updated:          { Icon: UsersIcon,  color: 'text-gray-700',  bg: 'bg-gray-100' },
    user_deleted:          { Icon: Trash2,     color: 'text-red-600',   bg: 'bg-red-50'   },
    your_account_changed:  { Icon: ShieldAlert,color: 'text-amber-600', bg: 'bg-amber-50' },

    // Automation
    automation_rule_created: { Icon: Zap, color: 'text-brand-600', bg: 'bg-brand-50' },
    automation_rule_updated: { Icon: Zap, color: 'text-brand-600', bg: 'bg-brand-50' },
    automation_rule_deleted: { Icon: Zap, color: 'text-red-600',   bg: 'bg-red-50'    },
    automation_rule_toggled: { Icon: Zap, color: 'text-gray-600',  bg: 'bg-gray-100'  },

    // AI Settings
    ai_settings_changed: { Icon: Bot, color: 'text-brand-600',  bg: 'bg-brand-50' },
    ai_settings_reset:   { Icon: Bot, color: 'text-amber-600',  bg: 'bg-amber-50'  },

    // Security
    webhook_signature_failed: { Icon: Shield, color: 'text-red-600', bg: 'bg-red-50' },
  }

  const fallback = { Icon: Bell, color: 'text-gray-500', bg: 'bg-gray-50' }
  const base = typeMap[type] || fallback

  // Apply severity tint to bg only — keep the type's icon and natural color for info notifications,
  // but for urgent/warning we override entirely so the user notices.
  if (sevColor) {
    return { Icon: base.Icon, ...sevColor }
  }
  return base
}

// Separate component for notification item to use the useTimeAgo hook
function NotificationItem({ notif, Icon, color, bg, onClickNotif }) {
  const timeAgoStr = useTimeAgo(notif.created_at)
  const created = parseBackendTime(notif.created_at)
  return (
    <button
      onClick={() => onClickNotif(notif)}
      className={clsx(
        'w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors',
        !notif.read && 'bg-blue-50/30'
      )}
    >
      <div className="flex items-start gap-3">
        <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5', bg)}>
          <Icon size={16} className={color} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-bold text-gray-900">{notif.title}</p>
            {!notif.read && (
              <span className={clsx(
                'w-2 h-2 rounded-full shrink-0 mt-1',
                notif.severity === 'urgent' ? 'bg-red-500'
                  : notif.severity === 'warning' ? 'bg-amber-500'
                  : 'bg-blue-500'
              )} />
            )}
          </div>
          {notif.body && (
            <p className="text-xs text-gray-600 mt-0.5 leading-snug">{notif.body}</p>
          )}
          <p className="text-xs text-gray-400 mt-1.5 font-medium">{timeAgoStr}</p>
        </div>
      </div>
    </button>
  )
}

// Bell poll interval. Real push (SSE/WebSocket) is deliberately NOT used: the
// app runs gunicorn sync workers (2 x 4 threads = 8 concurrent slots), and an
// SSE stream holds a thread for its whole lifetime — 8 open tabs would leave
// zero capacity for webhooks or page loads. Combined with fetch-on-focus
// below, 20s polling gives near-instant perceived latency at no risk.
const NOTIFICATION_POLL_MS = 20000

// Which urgent notifications have already been announced as a toast.
// Kept in localStorage because the refs below reset on every page load —
// without this the catch-up toast re-fires on every refresh.
const TOASTED_KEY = 'toastedNotificationIds'

function alreadyToasted() {
  try { return new Set(JSON.parse(localStorage.getItem(TOASTED_KEY) || '[]')) }
  catch { return new Set() }
}

function markToasted(ids) {
  if (!ids.length) return
  try {
    const prev = JSON.parse(localStorage.getItem(TOASTED_KEY) || '[]')
    localStorage.setItem(TOASTED_KEY, JSON.stringify([...prev, ...ids].slice(-200)))
  } catch { /* quota or parse — non-fatal */ }
}

export default function TopBar({ onMenuClick }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const { user, logout } = useAuth()
  const { toggleTheme, isDark } = useTheme()
  const navigate = useNavigate()

  const API_BASE = import.meta.env.VITE_API_BASE || '/api'
  const [health, setHealth] = useState({ status: 'operational' })
  const [clockTick, setClockTick] = useState(0)

  // This was `const now = new Date()...` in the render body: computed once and
  // then frozen until something else re-rendered the bar, so the clock could
  // sit minutes or hours behind. Tick it every 30s instead.
  useEffect(() => {
    const id = setInterval(() => setClockTick(t => t + 1), 30000)
    return () => clearInterval(id)
  }, [])

  // Rendered in the BUSINESS timezone, not the viewer's. The Dashboard buckets
  // "Today" and "This week" by Nairobi days, so a browser-local clock beside
  // those figures would disagree for anyone working from another country.
  const now = (() => {
    void clockTick   // re-evaluate on tick
    const opts = {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }
    try {
      return new Date().toLocaleString('en-KE',
        health.timezone ? { ...opts, timeZone: health.timezone } : opts)
    } catch {
      return new Date().toLocaleString('en-KE', opts)   // unknown zone → viewer's
    }
  })()
  const [showHealth, setShowHealth] = useState(false)

  useEffect(() => {
    let active = true
    const loadHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
        })
        if (!res.ok) throw new Error('bad status')
        const data = await res.json()
        if (active) setHealth(data)
      } catch {
        if (active) setHealth({ status: 'unreachable' })
      }
    }
    loadHealth()
    const id = setInterval(loadHealth, 60000)   // re-check every minute
    return () => { active = false; clearInterval(id) }
  }, [])

  const HEALTH = {
    operational: { dot: 'bg-green-500', label: 'All systems operational' },
    degraded:    { dot: 'bg-amber-500', label: 'Running with warnings' },
    critical:    { dot: 'bg-red-500',   label: 'System issues detected' },
    unreachable: { dot: 'bg-gray-400',  label: "Can't reach the server" },
  }
  const hStatus = HEALTH[health.status] || HEALTH.operational
  // The API also gates the issue DETAIL, so this is defence in depth rather
  // than the only check — an agent hitting /api/health directly gets an empty
  // issues array regardless.
  const canSeeHealth = user?.role === 'admin' || user?.role === 'supervisor'

  // Load notifications on mount + poll every 10 seconds
  const { showToast } = useToast()
  const seenIdsRef = useRef(new Set())
  const isFirstLoadRef = useRef(true)

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchNotifications({ limit: 20 })

        const newList = data.notifications || []
        setNotifications(newList)
        setUnreadCount(data.unread_count || 0)

        // On login: don't pop the whole backlog, but DO surface URGENT unread
        // items (e.g. escalations assigned while the agent was away) as a single
        // catch-up toast. General unread stays silent — toasting it would fire on
        // every refresh and be noisy (you can sit on 20+ unread).
        if (isFirstLoadRef.current) {
          newList.forEach(n => seenIdsRef.current.add(n.id))
          isFirstLoadRef.current = false

          const announced = alreadyToasted()
          const unreadUrgent = newList.filter(
            n => !n.read && n.severity === 'urgent' &&
                 !announced.has(n.id) &&
                 !(n.actor_id && user?.id && n.actor_id === user.id)
          )
          if (unreadUrgent.length === 1) {
            showToast({
              title: unreadUrgent[0].title,
              body: unreadUrgent[0].body,
              severity: 'urgent',
            })
          } else if (unreadUrgent.length > 1) {
            showToast({
              title: `${unreadUrgent.length} items need your attention`,
              body: 'Open notifications to review escalations assigned to you.',
              severity: 'urgent',
            })
          }
          markToasted(unreadUrgent.map(n => n.id))
          return
        }

        // On subsequent polls: show toasts for truly NEW notifications,
        // but ONLY if urgent + unread + not where current user is the actor.
        // Info and warning notifications go silently to the bell.
        newList.forEach(n => {
          if (seenIdsRef.current.has(n.id)) return
          seenIdsRef.current.add(n.id)

          const isUrgent = n.severity === 'urgent'
          const isUnread = !n.read
          const isMyOwnAction = n.actor_id && user?.id && n.actor_id === user.id

          if (isUrgent && isUnread && !isMyOwnAction) {
            showToast({
              title: n.title,
              body: n.body,
              severity: n.severity,
            })
            markToasted([n.id])
          }
        })
      } catch (err) {
        console.error('[Toast] Failed to load notifications:', err)
      }
    }

    load()
    // Was every 5 SECONDS. Between this, the conversation poll below, the
    // sidebar badge and the Dashboard's own timers, a single open tab was
    // making ~29 requests a minute — a real contributor to running the
    // database connection pool dry. 20s is the standard for a bell.
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, NOTIFICATION_POLL_MS)

    // Fetch the moment the tab is looked at again. This is what makes coming
    // back from lunch feel instant: the interval alone would leave you staring
    // at stale counts for up to 20s at exactly the moment you're most likely
    // to have missed something. Cheap, because it only fires on a real
    // focus/visibility change, not on a timer.
    const onWake = () => { if (document.visibilityState === 'visible') load() }
    document.addEventListener('visibilitychange', onWake)
    window.addEventListener('focus', onWake)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onWake)
      window.removeEventListener('focus', onWake)
    }
  }, [showToast])

  // Poll the conversations list every 10s and pop a toast for new inbound DMs.
  // Track previous unread_count per conversation to detect TRUE new inbound.
  const prevUnreadRef = useRef(new Map())
  const isFirstMsgLoadRef = useRef(true)
  const msgPollRunningRef = useRef(false)   // stops overlapping poll runs

  useEffect(() => {
    let cancelled = false

    const loadMessages = async () => {
      // This body awaits several times; without a guard the 5s interval kicks
      // off a second run that re-reads stale unread counts and re-toasts.
      if (msgPollRunningRef.current) return
      msgPollRunningRef.current = true
      try {
        const { listConversations } = await import('../api/messages')
        const data = await listConversations({ channel: 'all', page: 1, per_page: 20 })
        if (cancelled) return

        const convs = data.conversations || []

        // First load: seed the unread map, don't pop anything.
        if (isFirstMsgLoadRef.current) {
          convs.forEach(c => prevUnreadRef.current.set(c.id, c.unread_count || 0))
          isFirstMsgLoadRef.current = false
          return
        }

        // For each conversation, toast only if unread_count INCREASED.
        // That can only happen on a real new inbound — outbound replies
        // reset/don't change unread.
        for (const c of convs) {
          const prev = prevUnreadRef.current.get(c.id) ?? 0
          const curr = c.unread_count || 0
          // Record BEFORE the awaits below — otherwise a concurrent run sees
          // the old value and fires a duplicate toast for the same message.
          prevUnreadRef.current.set(c.id, curr)
          if (curr > prev) {
            // Fetch the conv to get the actual latest INBOUND message
            // (lastMessage on the list reflects the most recent message
            // overall, which is usually the AI's outbound reply).
            try {
              const { getConversation } = await import('../api/messages')
              const detail = await getConversation(c.id)
              const msgs = detail.conversation?.messages || []
              const lastInbound = [...msgs].reverse().find(m => m.from === 'user')
              showToast({
                title: `New message from ${c.handle || 'customer'}`,
                body: lastInbound?.text || c.lastMessage || '',
                severity: 'urgent',
              })
            } catch {
              // Fallback to lastMessage on error
              showToast({
                title: `New message from ${c.handle || 'customer'}`,
                body: c.lastMessage || '',
                severity: 'urgent',
              })
            }
          }
          }
      } catch (err) {
        console.error('[Toast] Failed to poll messages:', err)
      } finally {
        msgPollRunningRef.current = false
      }
    }

    loadMessages()
    // Also slowed and visibility-gated: this pulls 20 full conversation
    // records each time, purely to spot an unread count going up.
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') loadMessages()
    }, 30000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [showToast])

  const handleClickNotif = async (n) => {
    // Optimistic mark-as-read
    if (!n.read) {
      setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, read: true } : x))
      setUnreadCount(c => Math.max(0, c - 1))
      try { await markNotificationRead(n.id) } catch { /* ignore */ }
    }
    // Navigate to the relevant conversation if applicable
    if (n.resource_type === 'conversation' && n.resource_id) {
      navigate(`/messages?conversation=${n.resource_id}`)
      setShowNotifications(false)
    }
  }

  const handleMarkAllRead = async () => {
    setNotifications(prev => prev.map(x => ({ ...x, read: true })))
    setUnreadCount(0)
    try { await markAllNotificationsRead() } catch { /* ignore */ }
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-4 md:px-6" style={{ backgroundColor: 'var(--topbar-bg)', backdropFilter: 'blur(20px) saturate(180%)', borderBottom: '1px solid var(--topbar-line)' }}>
      <div className="flex items-center gap-3">
        {/* Hamburger — MOBILE ONLY, where it opens the drawer. On desktop it
            duplicated the sidebar's own collapse button, so the same action
            had two controls in two places. The sidebar owns that job now. */}
        <button
          onClick={onMenuClick}
          className="md:hidden p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200/60 transition-colors"
          title="Open menu"
          aria-label="Open menu"
        >
          <Menu size={18} />
        </button>

        {/* Admin + supervisor only. An agent can't act on a failed Shopify
            sync or a database connection error, so "System issues detected"
            gave them alarm without agency — and the detail panel behind it
            listed raw log text down to database hostnames. Their equivalent
            is the Dashboard's "Needs Attention" panel, which is scoped to
            work they own. Matches the gating on /api/alerts. */}
        {canSeeHealth && (
          <button
            onClick={() => setShowHealth(s => !s)}
            className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-gray-200/60 transition-colors"
            title="System status — click for details"
          >
            <span className={clsx('w-1.5 h-1.5 rounded-full', hStatus.dot)} style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} />
            <span className="hidden sm:block text-xs text-gray-400 font-normal tracking-wide">
              {hStatus.label}
            </span>
          </button>
        )}

        {showHealth && (
          <ModalPortal>
            <div className="fixed inset-0 z-40" onClick={() => setShowHealth(false)} />
            <div className="fixed left-4 top-16 w-[26rem] max-w-[calc(100vw-2rem)] bg-white rounded-xl shadow-2xl border border-gray-200 z-50 overflow-hidden flex flex-col max-h-[520px]">
              <div className="flex items-start justify-between px-4 py-3 border-b border-gray-100 bg-gray-50 shrink-0">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">{hStatus.label}</h3>
                  <p className="text-xs text-gray-500 mt-0.5 tabular-nums">
                    {health.errors || 0} errors · {health.warnings || 0} warnings · {health.failed_jobs || 0} failed jobs (last hour)
                  </p>
                </div>
                <button onClick={() => setShowHealth(false)} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
                  <X size={16} />
                </button>
              </div>
              <div className="overflow-y-auto flex-1 divide-y divide-gray-50">
                {!(health.issues || []).length ? (
                  <div className="px-4 py-8 text-center">
                    <CheckCircle size={26} className="text-green-400 mx-auto mb-2" />
                    <p className="text-xs text-gray-500">Nothing wrong in the last hour.</p>
                  </div>
                ) : (
                  health.issues.map((iss, i) => (
                    <div key={i} className="px-4 py-2.5 flex items-start gap-2.5">
                      <span className={clsx('w-1.5 h-1.5 rounded-full mt-1.5 shrink-0',
                        iss.level === 'error' || iss.level === 'critical' ? 'bg-red-500' : 'bg-amber-500')} />
                      <div className="min-w-0 flex-1">
                        <p className="text-[11px] font-bold text-gray-700 font-mono truncate">{iss.source}</p>
                        <p className="text-xs text-gray-600 mt-0.5 leading-snug break-words">{iss.message}</p>
                        {iss.at && (
                          <p className="text-[10px] text-gray-400 mt-1">
                            {new Date(iss.at + 'Z').toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })}
                          </p>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </ModalPortal>
        )}
      </div>

      <div className="flex items-center gap-1 md:gap-2">
        {/* Date */}
        <span className="hidden md:block text-xs text-gray-400 font-normal mr-2">{now}</span>

        <button
          onClick={toggleTheme}
          className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200/60 transition-colors"
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {/* Notifications */}
        <button
          className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200/60 transition-colors relative"
          title="Notifications"
          onClick={() => setShowNotifications(!showNotifications)}
        >
          <Bell size={16} />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-red-500" style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} />
          )}
        </button>

        {/* Notifications Dropdown */}
        {showNotifications && (
          <ModalPortal>
            <div className="fixed inset-0 z-40" onClick={() => setShowNotifications(false)} />
            <div className="fixed right-4 top-16 w-96 max-w-[calc(100vw-2rem)] bg-white rounded-xl shadow-2xl border border-gray-200 z-50 overflow-hidden flex flex-col max-h-[600px]">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50 shrink-0">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Notifications</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  {unreadCount > 0 && (
                    <button
                      onClick={handleMarkAllRead}
                      className="text-xs text-gray-500 hover:text-gray-900 inline-flex items-center gap-1 px-2 py-1 rounded transition-colors"
                      title="Mark all read"
                    >
                      <CheckCheck size={12} /> All read
                    </button>
                  )}
                  <button onClick={() => setShowNotifications(false)} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                    <X size={16} />
                  </button>
                </div>
              </div>
              <div className="overflow-y-auto flex-1">
                {notifications.length === 0 ? (
                  <div className="px-4 py-10 text-center">
                    <Bell size={28} className="text-gray-300 mx-auto mb-2" />
                    <p className="text-xs text-gray-500">No notifications yet</p>
                  </div>
                ) : (
                  groupNotifsByDay(notifications).map(group => (
                    <div key={group.label}>
                      <div className="px-4 py-2 bg-gray-50/50 border-b border-gray-100 sticky top-0 z-10">
                        <p className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                          {group.label}
                        </p>
                      </div>
                      {group.notifs.map(notif => {
                        const { Icon, color, bg } = notifVisuals(notif.type, notif.severity)
                        return (
                          <NotificationItem
                            key={notif.id}
                            notif={notif}
                            Icon={Icon}
                            color={color}
                            bg={bg}
                            onClickNotif={handleClickNotif}
                          />
                        )
                      })}
                    </div>
                  ))
                )}
              </div>
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50 shrink-0">
                <button onClick={() => { navigate('/notifications'); setShowNotifications(false) }} className="w-full text-xs font-semibold text-brand-600 hover:text-brand-700 py-1.5 transition-colors">
                  View all notifications →
                </button>
              </div>
            </div>
          </ModalPortal>
        )}

        {/* User menu */}
        <div className="relative ml-1">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center justify-center w-8 h-8 rounded-full bg-black hover:bg-gray-800 transition-colors"
          >
            <div className="text-white text-xs font-medium">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
            </div>
          </button>

          {showUserMenu && (
            <ModalPortal>
              <div className="fixed right-4 top-16 w-52 bg-white rounded-xl shadow-lg border border-gray-200 z-50 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
                  <p className="text-xs font-bold text-gray-900">{user?.full_name}</p>
                  <p className="text-[11px] text-gray-500 mt-0.5">{user?.email}</p>
                  <span className="inline-block mt-1.5 text-[10px] font-semibold bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded capitalize">{user?.role}</span>
                </div>
                <div className="py-1">
                  <button onClick={() => { setShowUserMenu(false); navigate('/profile') }} className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 transition-colors">
                    <User size={14} />
                    Profile Settings
                  </button>
                  <button onClick={() => { setShowUserMenu(false); handleLogout() }} className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs text-red-600 hover:bg-red-50 transition-colors">
                    <LogOut size={14} />
                    Sign Out
                  </button>
                </div>
              </div>
            </ModalPortal>
          )}
        </div>
      </div>
    </header>
  )
}