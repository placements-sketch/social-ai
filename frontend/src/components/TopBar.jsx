import { useState } from 'react'
import { Bell, RefreshCw, Menu, LogOut, User, MessageSquare, AlertTriangle, CheckCircle, Zap, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ModalPortal } from '../context/ModalPortal'
import clsx from 'clsx'

export default function TopBar({ onMenuClick }) {
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [showNotifications, setShowNotifications] = useState(false)
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const now = new Date().toLocaleString('en-KE', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

  // Dummy notifications data
  const notifications = [
    {
      id: 1,
      type: 'message',
      title: '4 new messages',
      description: 'Instagram DM from @sarah_k asking about pricing',
      icon: MessageSquare,
      color: 'text-pink-500',
      bg: 'bg-pink-50',
      time: '2 min ago',
      read: false,
    },
    {
      id: 2,
      type: 'message',
      title: '2 new messages',
      description: 'WhatsApp from +254 700 123 456 about product availability',
      icon: MessageSquare,
      color: 'text-green-500',
      bg: 'bg-green-50',
      time: '5 min ago',
      read: false,
    },
    {
      id: 3,
      type: 'alert',
      title: 'Webhook warning',
      description: 'Instagram webhook response time elevated (2.8s)',
      icon: AlertTriangle,
      color: 'text-amber-500',
      bg: 'bg-amber-50',
      time: '12 min ago',
      read: false,
    },
    {
      id: 4,
      type: 'success',
      title: 'Automation rule triggered',
      description: 'Rule "Out of Stock Reply" matched 3 messages',
      icon: CheckCircle,
      color: 'text-green-600',
      bg: 'bg-green-50',
      time: '18 min ago',
      read: true,
    },
    {
      id: 5,
      type: 'alert',
      title: 'API error',
      description: 'Shopify sync failed: Connection timeout',
      icon: AlertTriangle,
      color: 'text-red-500',
      bg: 'bg-red-50',
      time: '25 min ago',
      read: true,
    },
  ]

  const unreadCount = notifications.filter(n => !n.read).length
  const messageCount = notifications.filter(n => n.type === 'message' && !n.read).length

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
          <span className="hidden sm:block text-xs text-gray-400 font-medium tracking-wide">
            All systems operational
          </span>
        </div>
      </div>

      <div className="flex items-center gap-1 md:gap-2">
        {/* Date */}
        <span className="hidden md:block text-xs text-gray-400 font-medium mr-2">{now}</span>

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
                  {unreadCount > 0 && <p className="text-xs text-gray-500 mt-0.5">{unreadCount} unread</p>}
                </div>
                <button onClick={() => setShowNotifications(false)} className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                  <X size={16} />
                </button>
              </div>
              <div className="overflow-y-auto flex-1">
                {notifications.map((notif) => {
                  const Icon = notif.icon
                  return (
                    <div key={notif.id} className={clsx('px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer', !notif.read && 'bg-blue-50/30')}>
                      <div className="flex items-start gap-3">
                        <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5', notif.bg)}>
                          <Icon size={16} className={notif.color} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-xs font-bold text-gray-900">{notif.title}</p>
                            {!notif.read && <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 mt-1" />}
                          </div>
                          <p className="text-xs text-gray-600 mt-0.5 leading-snug">{notif.description}</p>
                          <p className="text-xs text-gray-400 mt-1.5 font-medium">{notif.time}</p>
                        </div>
                      </div>
                    </div>
                  )
                })}
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
            <div className="text-white text-xs font-semibold">
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
