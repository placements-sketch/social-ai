import { useState, useEffect, useRef } from 'react'
import { useToast } from './Toast'
import { Bell, RefreshCw, Menu, LogOut, User, MessageSquare, AlertTriangle, CheckCircle, X, CheckCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ModalPortal } from '../context/ModalPortal'
import { fetchNotifications, markNotificationRead, markAllNotificationsRead } from '../api/notifications'
import { useTimeAgo } from '../hooks/useTimeAgo'
import clsx from 'clsx'

// Icon + color mapping per notification type
function notifVisuals(type) {
  switch (type) {
    case 'assigned':
    case 'reassigned':
      return { Icon: MessageSquare, color: 'text-brand-600', bg: 'bg-orange-50' }
    case 'unassigned':
      return { Icon: AlertTriangle, color: 'text-amber-500', bg: 'bg-amber-50' }
    default:
      return { Icon: CheckCircle, color: 'text-gray-500', bg: 'bg-gray-50' }
  }
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
            {!notif.read && <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 mt-1" />}
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

        // On subsequent polls: show toasts for truly NEW notifications only
        newList.forEach(n => {
          if (!seenIdsRef.current.has(n.id)) {
            console.log('[Toast] Showing new notification:', n.title, n.body)
            showToast({ title: n.title, body: n.body })
            seenIdsRef.current.add(n.id)
          }
        })
      } catch (err) {
        console.error('[Toast] Failed to load notifications:', err)
      }
    }

    load()
    const timer = setInterval(() => load(), 10000) // Poll every 10 seconds
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
        convs.forEach(c => {
          const prev = prevUnreadRef.current.get(c.id) ?? 0
          const curr = c.unread_count || 0
          if (curr > prev) {
            showToast({
              title: `New message from ${c.handle || 'customer'}`,
              body: c.lastMessage || '',
            })
          }
          prevUnreadRef.current.set(c.id, curr)
        })
      } catch (err) {
        console.error('[Toast] Failed to poll messages:', err)
      }
    }

    loadMessages()
    const timer = setInterval(loadMessages, 10000)
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
                  notifications.map((notif) => {
                    const { Icon, color, bg } = notifVisuals(notif.type)
                    return <NotificationItem key={notif.id} notif={notif} Icon={Icon} color={color} bg={bg} onClickNotif={handleClickNotif} />
                  })
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