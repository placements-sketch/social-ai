import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, MessageSquare, Package, Bot,
  Zap, Radio, BarChart2, ScrollText, Settings, Sparkles,
  ChevronLeft, ChevronRight, X, Users, UserCircle,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'

const allNav = [
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard',          roles: ['admin', 'agent', 'supervisor'], group: 'Core' },
  { to: '/messages',   icon: MessageSquare,   label: 'Messages',            roles: ['admin', 'agent', 'supervisor'], badge: 4, group: 'Core' },
  
  { to: '/customers',  icon: UserCircle,      label: 'Customer Profiling', roles: ['admin', 'supervisor'], group: 'Business' },
  { to: '/products',   icon: Package,         label: 'Products',            roles: ['admin', 'supervisor'], group: 'Business' },
  { to: '/analytics',  icon: BarChart2,       label: 'Analytics',           roles: ['admin', 'agent', 'supervisor'], group: 'Business' },
  
  { to: '/channels',   icon: Radio,           label: 'Channels',            roles: ['admin'], group: 'Setup' },
  { to: '/ai',         icon: Bot,             label: 'AI Settings',         roles: ['admin'], group: 'Setup' },
  { to: '/automation', icon: Zap,             label: 'Automation',          roles: ['admin'], group: 'Setup' },
  
  { to: '/logs',       icon: ScrollText,      label: 'Logs',                roles: ['admin', 'agent', 'supervisor'], group: 'System' },
  { to: '/users',      icon: Users,           label: 'Users',               roles: ['admin'], group: 'System' },
  { to: '/settings',   icon: Settings,        label: 'Settings',            roles: ['admin'], group: 'System' },
]

export default function Sidebar({ collapsed, onToggle, onClose, isMobile = false }) {
  const { user } = useAuth()

  // Filter nav items based on user role
  const nav = allNav.filter(item => item.roles.includes(user?.role))

  return (
    <aside className={clsx(
      'h-full flex flex-col rounded-3xl transition-all duration-300 ease-in-out overflow-hidden',
      isMobile ? 'w-full' : (collapsed ? 'w-20' : 'w-64'),
    )}
    style={{
      background: 'linear-gradient(180deg, #111111 0%, #0d0d0d 100%)',
      boxShadow: 'none',
      borderTop: '1px solid rgba(255,255,255,0.06)',
      borderLeft: '2px solid #ff5900',
    }}
    >

      {/* ── Header: logo + close/collapse button ── */}
      <div className={clsx(
        'flex items-center h-16 shrink-0 pt-5',
        isMobile ? 'justify-between px-4' : (collapsed ? 'md:justify-center md:px-0 px-4 justify-between' : 'justify-between px-4')
      )}>
        {/* Logo — always show on mobile, hide text when desktop-collapsed */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
            <Sparkles size={16} className="text-white" />
          </div>
          <div className={clsx(isMobile ? 'block' : (collapsed ? 'md:hidden' : 'block'))}>
            <p className="text-sm font-bold text-white leading-none tracking-tight">Social AI</p>
            <p className="text-[10px] text-gray-500 mt-0.5">Dashboard</p>
          </div>
        </div>

        {/* Mobile: X close button */}
        <button
          onClick={onClose}
          className={clsx(isMobile ? 'block' : 'md:hidden', 'text-gray-400 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors')}
          aria-label="Close menu"
        >
          <X size={18} />
        </button>

        {/* Desktop: collapse chevron (not on mobile) */}
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
      <nav className={clsx(
        'flex-1 py-2 space-y-3',
        isMobile ? 'px-3' : (collapsed ? 'md:px-2 px-3' : 'px-3')
      )}>
        {/* Group navigation items */}
        {['Core', 'Business', 'Setup', 'System'].map((groupName, idx) => {
          const groupItems = nav.filter(item => item.group === groupName)
          if (groupItems.length === 0) return null

          return (
            <div key={groupName} className={idx === 0 ? 'pt-2' : ''}>
              {/* Separator line (except before first group) */}
              {idx > 0 && (
                <div className="my-3 px-3">
                  <div className="h-px bg-gradient-to-r from-transparent via-gray-700 to-transparent" />
                </div>
              )}
              
              {/* Group label - hide when collapsed on desktop */}
              {!collapsed && (
                <p className="text-xs font-semibold text-gray-200 uppercase tracking-widest px-3 py-1 mt-1">
                  {groupName}
                </p>
              )}
              
              {/* Group items */}
              <div className="space-y-1">
                {groupItems.map(({ to, icon: Icon, label, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    title={isMobile ? undefined : (collapsed ? label : undefined)}
                    className={({ isActive }) =>
                      clsx(
                        'relative flex items-center rounded-xl text-sm font-medium transition-all duration-200 ease-in-out',
                        isMobile ? 'gap-3 px-3 py-2' : (collapsed ? 'md:justify-center md:w-10 md:h-10 md:mx-auto md:px-0 gap-3 px-3 py-2' : 'gap-3 px-3 py-2'),
                        isActive
                          ? 'bg-brand-600 text-white shadow-lg'
                          : 'text-gray-400 hover:text-white hover:bg-white/5'
                      )
                    }
                  >
                    <Icon size={18} className="shrink-0" />

                    {/* Label: always show on mobile, hide on desktop when collapsed */}
                    <span className={clsx('flex-1 truncate', !isMobile && collapsed && 'md:hidden')}>
                      {label}
                    </span>

                    {/* Badge: message count circle like WhatsApp */}
                    {badge && (
                      <span className={clsx(
                        'w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0',
                        isMobile ? 'ml-auto' : (collapsed ? 'md:absolute md:top-1 md:right-1 md:w-4 md:h-4 md:text-[8px] hidden md:flex' : 'ml-auto')
                      )}>
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
      <div className={clsx(
        'shrink-0',
        isMobile ? 'px-4 py-4' : (collapsed ? 'md:px-2 md:py-3 px-4 py-4' : 'px-4 py-4')
      )}>
        {/* Desktop collapsed: avatar + expand (not on mobile) */}
        {!isMobile && (
          <div className={clsx('flex-col items-center gap-2', collapsed ? 'md:flex hidden' : 'hidden')}>
            <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
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

        {/* Expanded (mobile always, desktop when not collapsed) */}
        <div className={clsx('flex items-center gap-2.5', isMobile ? 'flex' : (collapsed ? 'md:hidden flex' : 'flex'))}>
          <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
            {user?.full_name?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-white truncate">{user?.full_name || 'User'}</p>
            <p className="text-xs text-gray-500 truncate capitalize">{user?.role || 'user'}</p>
          </div>
          <div className="w-2 h-2 rounded-full bg-green-500 shrink-0" style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} title="Online" />
        </div>
      </div>
    </aside>
  )
}
