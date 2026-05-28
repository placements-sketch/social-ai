import { useState } from 'react'
import { Bell, RefreshCw, Menu, LogOut, User, MessageSquare, AlertTriangle, CheckCircle, Zap, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
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
    <header className="h-16 shrink-0 flex items-center justify-between px-4 md:px-8 border-b border-gray-200 bg-white">
      <div className="flex items-center gap-3 md:gap-4">
        {/* Hamburger — toggles mobile drawer or desktop collapse */}
        <button
          onClick={onMenuClick}
          className="btn-ghost p-2"
          title="Toggle sidebar"
          aria-label="Toggle sidebar"
        >
          <Menu size={20} />
        </button>

        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          {/* Hide status text on very small screens */}
          <span className="hidden sm:block text-xs text-gray-500 font-medium">
            All systems operational
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 md:gap-3">
        {/* Hide date on mobile */}
        <span className="hidden md:block text-xs text-gray-400 font-medium">{now}</span>

        <button className="btn-ghost p-2" title="Refresh">
          <RefreshCw size={18} />
        </button>

        <button className="btn-ghost p-2 relative" title="Notifications" onClick={() => setShowNotifications(!showNotifications)}>
          <Bell size={18} />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          )}
        </button>

        {/* Notifications Dropdown */}
        {showNotifications && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-30"
              onClick={() => setShowNotifications(false)}
            />
            
            {/* Dropdown Panel */}
            <div className="fixed right-4 top-20 w-96 max-w-[calc(100vw-2rem)] bg-white rounded-xl shadow-2xl border border-gray-200 z-40 overflow-hidden flex flex-col max-h-[600px]">
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50 shrink-0">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Notifications</h3>
                  {unreadCount > 0 && (
                    <p className="text-xs text-gray-500 mt-0.5">{unreadCount} unread</p>
                  )}
                </div>
                <button
                  onClick={() => setShowNotifications(false)}
                  className="btn-ghost p-1"
                  title="Close"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Notifications List */}
              <div className="overflow-y-auto flex-1">
                {notifications.map((notif) => {
                  const Icon = notif.icon
                  return (
                    <div
                      key={notif.id}
                      className={clsx(
                        'px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors cursor-pointer',
                        !notif.read && 'bg-blue-50/30'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5', notif.bg)}>
                          <Icon size={16} className={notif.color} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-xs font-bold text-gray-900">{notif.title}</p>
                            {!notif.read && (
                              <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 mt-1" />
                            )}
                          </div>
                          <p className="text-xs text-gray-600 mt-0.5 leading-snug">{notif.description}</p>
                          <p className="text-xs text-gray-400 mt-1.5 font-medium">{notif.time}</p>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Footer */}
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50 shrink-0">
                <button
                  onClick={() => {
                    navigate('/logs')
                    setShowNotifications(false)
                  }}
                  className="w-full text-xs font-semibold text-brand-600 hover:text-brand-700 py-1.5 transition-colors"
                >
                  View all notifications →
                </button>
              </div>
            </div>
          </>
        )}

        {/* User Profile Menu */}
        <div className="relative ml-2">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition"
            title="User menu"
          >
            <div className="w-8 h-8 rounded-full bg-gray-900 flex items-center justify-center text-white text-xs font-semibold">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <span className="hidden sm:block text-xs font-medium text-gray-700 max-w-[100px] truncate">
              {user?.full_name || 'User'}
            </span>
          </button>

          {/* Dropdown Menu */}
          {showUserMenu && (
            <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 z-50">
              <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-sm font-semibold text-gray-900">{user?.full_name}</p>
                <p className="text-xs text-gray-500">{user?.email}</p>
                <p className="text-xs text-gray-400 mt-1 capitalize">
                  Role: <span className="font-medium text-gray-900">{user?.role}</span>
                </p>
              </div>

              <div className="py-2">
                <button
                  onClick={() => {
                    setShowUserMenu(false)
                    navigate('/settings')
                  }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition"
                >
                  <User size={16} />
                  Profile Settings
                </button>

                <button
                  onClick={() => {
                    setShowUserMenu(false)
                    handleLogout()
                  }}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition"
                >
                  <LogOut size={16} />
                  Logout
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
