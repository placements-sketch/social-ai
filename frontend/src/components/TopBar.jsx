import { useState, useEffect, useRef } from 'react'
import { useToast } from './Toast'
import {
  Bell, RefreshCw, Menu, LogOut, User, MessageSquare,
  AlertTriangle, CheckCircle, X, CheckCheck,
  Radio, RefreshCw as Sync, Users as UsersIcon, Shield,
  Zap, Bot, Trash2, UserPlus, UserCheck, Package,
  AlertOctagon, Settings as SettingsIcon, ShieldAlert,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ModalPortal } from '../context/ModalPortal'
import { fetchNotifications, markNotificationRead, markAllNotificationsRead } from '../api/notifications'
import { useTimeAgo } from '../hooks/useTimeAgo'
import clsx from 'clsx'

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
    const created = new Date(n.created_at)
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
    assigned:                       { Icon: UserCheck,     color: 'text-brand-600', bg: 'bg-orange-50' },
    reassigned:                     { Icon: UserCheck,     color: 'text-brand-600', bg: 'bg-orange-50' },
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
    automation_rule_created: { Icon: Zap, color: 'text-brand-600', bg: 'bg-orange-50' },
    automation_rule_updated: { Icon: Zap, color: 'text-brand-600', bg: 'bg-orange-50' },
    automation_rule_deleted: { Icon: Zap, color: 'text-red-600',   bg: 'bg-red-50'    },
    automation_rule_toggled: { Icon: Zap, color: 'text-gray-600',  bg: 'bg-gray-100'  },

    // AI Settings
    ai_settings_changed: { Icon: Bot, color: 'text-brand-600',  bg: 'bg-orange-50' },
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

export default function TopBar({ onMenuClick }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const now = new Date().toLocaleString('en-KE', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

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

        // Only on ACTUAL login (first load after component mount), mark all as seen so they don't pop in
        if (isFirstLoadRef.current) {
          newList.forEach(n => seenIdsRef.current.add(n.id))
          isFirstLoadRef.current = false
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
            console.log('[Toast] Showing urgent notification:', n.title)
            showToast({
              title: n.title,
              body: n.body,
              severity: n.severity,
            })
          }
        })
      } catch (err) {
        console.error('[Toast] Failed to load notifications:', err)
      }
    }

    load()
    const timer = setInterval(() => load(), 5000) // Poll every 5 seconds
    return () => { clearInterval(timer) }
  }, [showToast])

  // Poll the conversations list every 10s and pop a toast for new inbound DMs.
  // Track previous unread_count per conversation to detect TRUE new inbound.
  const prevUnreadRef = useRef(new Map())
  const isFirstMsgLoadRef = useRef(true)

  useEffect(() => {
    let cancelled = false

    const loadMessages = async () => {
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
          prevUnreadRef.current.set(c.id, curr)
        }
      } catch (err) {
        console.error('[Toast] Failed to poll messages:', err)
      }
    }

    loadMessages()
    const timer = setInterval(loadMessages, 5000)
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
    <header className="h-14 shrink-0 flex items-center justify-between px-4 md:px-6" style={{ backgroundColor: 'rgba(255, 255, 255, 0.8)', backdropFilter: 'blur(8px)', borderBottom: '1px solid rgba(255, 255, 255, 0.2)' }}>
      <div className="flex items-center gap-3">
        {/* Hamburger */}
        <button
          onClick={onMenuClick}
          className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200/60 transition-colors"
          title="Toggle sidebar"
          aria-label="Toggle sidebar"
        >
          <Menu size={18} />
        </button>

        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500" style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} />
          <span className="hidden sm:block text-xs text-gray-400 font-normal tracking-wide">
            All systems operational
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1 md:gap-2">
        {/* Date */}
        <span className="hidden md:block text-xs text-gray-400 font-normal mr-2">{now}</span>

        <button className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200/60 transition-colors" title="Refresh">
          <RefreshCw size={16} />
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
                <button onClick={() => { navigate('/logs'); setShowNotifications(false) }} className="w-full text-xs font-semibold text-brand-600 hover:text-brand-700 py-1.5 transition-colors">
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
                  <button onClick={() => { setShowUserMenu(false); navigate('/settings') }} className="w-full flex items-center gap-2.5 px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 transition-colors">
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