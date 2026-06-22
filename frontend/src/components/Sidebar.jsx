import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, MessageSquare, Package, Bot,
  Zap, Radio, BarChart2, ScrollText, Settings, Sparkles,
  ChevronLeft, ChevronRight, X, Users, UserCircle, Bell,
} from 'lucide-react'
import PresenceDot from './PresenceDot'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import szLogo from '../images/sz.png'

const allNav = [
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard',          roles: ['admin', 'agent', 'supervisor'], group: 'Core' },
  { to: '/messages',   icon: MessageSquare,   label: 'Messages',            roles: ['admin', 'agent', 'supervisor'], badge: 4, group: 'Core' },

  { to: '/customers',  icon: UserCircle,      label: 'Customer Profiling', roles: ['admin', 'supervisor'], group: 'Business' },
  { to: '/products',   icon: Package,         label: 'Products',            roles: ['admin', 'supervisor'], group: 'Business' },
  { to: '/analytics',  icon: BarChart2,       label: 'Analytics',           roles: ['admin', 'agent', 'supervisor'], group: 'Business' },

  { to: '/channels',   icon: Radio,           label: 'Channels',            roles: ['admin'], group: 'Setup' },
  { to: '/ai',         icon: Bot,             label: 'AI Settings',         roles: ['admin'], group: 'Setup' },
  { to: '/automation', icon: Zap,             label: 'Automation',          roles: ['admin'], group: 'Setup' },

  { to: '/logs',          icon: ScrollText,      label: 'Logs',          roles: ['admin', 'agent', 'supervisor'], group: 'System' },
  { to: '/notifications', icon: Bell,            label: 'Notifications', roles: ['admin', 'agent', 'supervisor'], group: 'System' },
  { to: '/users',         icon: Users,           label: 'Users',         roles: ['admin'], group: 'System' },
  { to: '/settings',      icon: Settings,        label: 'Settings',      roles: ['admin'], group: 'System' },
]

export default function Sidebar({ collapsed, onToggle, onClose, isMobile = false }) {
  const { user } = useAuth()
  const nav = allNav.filter(item => item.roles.includes(user?.role))

  return (
    <aside
      className={clsx(
        'h-full flex flex-col rounded-3xl transition-all duration-300 ease-in-out overflow-hidden',
        isMobile ? 'w-full' : (collapsed ? 'w-20' : 'w-60 lg:w-64'),
      )}
      style={{
        background: 'linear-gradient(180deg, #111111 0%, #0d0d0d 100%)',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        borderLeft: '2px solid #ff5900',
        minHeight: 0,
        maxHeight: '100vh',
      }}
    >
      {/* ── Header: logo + close/collapse button ── */}
      <div
        className={clsx(
          'flex items-center shrink-0 h-11 lg:h-16 px-3 pt-2 lg:pt-5',
          isMobile ? 'justify-between' : (collapsed ? 'md:justify-center md:px-0 justify-between' : 'justify-between')
        )}
      >
        <div className="flex items-center gap-2.5">
          <img src={szLogo} alt="Shop Zetu" className="w-8 h-8 lg:w-9 lg:h-9 shrink-0" />
          <div className={clsx(isMobile ? 'block' : (collapsed ? 'md:hidden' : 'block'))}>
            <p className="text-sm font-bold text-white leading-tight tracking-tight">Shop Zetu</p>
            <p className="text-[10px] text-gray-400 mt-0.5">Social AI</p>
          </div>
        </div>

        <button
          onClick={onClose}
          className={clsx(isMobile ? 'block' : 'md:hidden', 'text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors')}
          aria-label="Close menu"
        >
          <X size={18} />
        </button>

        {!isMobile && (
          <button
            onClick={onToggle}
            className={clsx(
              'hidden md:flex text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5',
              collapsed && 'md:hidden'
            )}
            title="Collapse sidebar"
          >
            <ChevronLeft size={16} />
          </button>
        )}
      </div>

      {/* ── Nav links ── */}
      <nav
        className={clsx(
          'flex-1 min-h-0 py-1 lg:py-5 overflow-hidden',
          isMobile ? 'px-2.5' : (collapsed ? 'md:px-2 px-3' : 'px-3')
        )}
      >
        {['Core', 'Business', 'Setup', 'System'].map((groupName, idx) => {
          const groupItems = nav.filter(item => item.group === groupName)
          if (groupItems.length === 0) return null

          return (
            <div key={groupName} className={idx === 0 ? '' : 'mt-1 lg:mt-3'}>
              {idx > 0 && (
                <div className="mb-1 lg:mb-3 px-3">
                  <div className="h-px bg-gradient-to-r from-transparent via-gray-700 to-transparent" />
                </div>
              )}

              {!collapsed && !isMobile && (
                <p className="text-[10px] lg:text-xs font-semibold text-gray-300 uppercase tracking-widest px-3 mb-0.5 lg:mb-1.5">
                  {groupName}
                </p>
              )}

              <div className="space-y-0 lg:space-y-1">
                {groupItems.map(({ to, icon: Icon, label, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    title={isMobile ? undefined : (collapsed ? label : undefined)}
                    className={({ isActive }) =>
                      clsx(
                        'relative flex items-center rounded-xl text-sm font-medium transition-all duration-200 ease-in-out',
                        isMobile
                          ? 'gap-2.5 px-2.5 py-1'
                          : (collapsed
                              ? 'md:justify-center md:w-10 md:h-10 md:mx-auto md:px-0 gap-3 px-3 py-2'
                              : 'gap-3 px-3 py-1.5 lg:py-2'),
                        isActive
                          ? 'bg-brand-600 text-white shadow-lg'
                          : 'text-gray-400 hover:text-white hover:bg-white/5'
                      )
                    }
                  >
                    <Icon className="shrink-0 w-[16px] h-[16px] lg:w-[18px] lg:h-[18px]" />

                    <span className={clsx('flex-1 truncate', !isMobile && collapsed && 'md:hidden')}>
                      {label}
                    </span>

                    {badge && (
                      <span
                        className={clsx(
                          'w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0',
                          isMobile ? 'ml-auto' : (collapsed ? 'md:absolute md:top-1 md:right-1 md:w-4 md:h-4 md:text-[8px] hidden md:flex' : 'ml-auto')
                        )}
                      >
                        {badge}
                      </span>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          )
        })}
      </nav>

      {/* ── Footer: user info + desktop expand button ── */}
      <div
        className={clsx(
          'shrink-0',
          isMobile ? 'px-4 py-3' : (collapsed ? 'md:px-2 md:py-3 px-4 py-3' : 'px-4 py-3 lg:py-4')
        )}
      >
        {!isMobile && (
          <div className={clsx('flex-col items-center gap-2', collapsed ? 'md:flex hidden' : 'hidden')}>
            <div className="relative">
              <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
                {user?.full_name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 rounded-full border-2 border-[#0d0d0d]">
                <PresenceDot status={user?.presence || 'online'} size="md" />
              </span>
            </div>
            <button
              onClick={onToggle}
              className="text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5"
              title="Expand sidebar"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}

        <div className={clsx('flex items-center gap-2.5', isMobile ? 'flex' : (collapsed ? 'md:hidden flex' : 'flex'))}>
          <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
            {user?.full_name?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-white truncate">{user?.full_name || 'User'}</p>
            <p className="text-[11px] text-gray-500 truncate capitalize">{user?.role || 'user'}</p>
          </div>
          <PresenceDot status={user?.presence || 'online'} />
        </div>
      </div>
    </aside>
  )
}