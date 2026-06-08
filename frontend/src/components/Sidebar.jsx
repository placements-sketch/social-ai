import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, MessageSquare, Package, Bot,
  Zap, Radio, BarChart2, ScrollText, Settings, Sparkles,
  ChevronLeft, ChevronRight, X, Users,
} from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'

const allNav = [
  // All users can access these
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard',   roles: ['admin', 'agent', 'supervisor'] },
  { to: '/messages',   icon: MessageSquare,   label: 'Messages',    roles: ['admin', 'agent', 'supervisor'], badge: 4 },
  { to: '/products',   icon: Package,         label: 'Products',    roles: ['admin', 'supervisor'] },
  { to: '/analytics',  icon: BarChart2,       label: 'Analytics',   roles: ['admin', 'agent', 'supervisor'] },
  { to: '/logs',       icon: ScrollText,      label: 'Logs',        roles: ['admin', 'agent', 'supervisor'] },

  // Admin only
  { to: '/ai',         icon: Bot,             label: 'AI Settings', roles: ['admin'] },
  { to: '/automation', icon: Zap,             label: 'Automation',  roles: ['admin'] },
  { to: '/channels',   icon: Radio,           label: 'Channels',    roles: ['admin'] },
  { to: '/users',      icon: Users,           label: 'Users',       roles: ['admin'] },
  { to: '/settings',   icon: Settings,        label: 'Settings',    roles: ['admin'] },
]

export default function Sidebar({ collapsed, onToggle, onClose }) {
  const { user } = useAuth()

  // Filter nav items based on user role
  const nav = allNav.filter(item => item.roles.includes(user?.role))

  return (
    <aside className={clsx(
      'h-full flex flex-col bg-black border-r border-gray-800 transition-all duration-300 ease-in-out',
      // Mobile: always full-width drawer (w-64)
      // Desktop: w-64 expanded, w-20 collapsed
      'w-64',
      collapsed && 'md:w-20',
    )}>

      {/* ── Header: logo + close/collapse button ── */}
      <div className={clsx(
        'flex items-center border-b border-gray-800 h-16 shrink-0',
        collapsed ? 'md:justify-center md:px-0 px-4 justify-between' : 'justify-between px-4'
      )}>
        {/* Logo — always show on mobile, hide text when desktop-collapsed */}
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center shrink-0">
            <Sparkles size={16} className="text-white" />
          </div>
          <div className={clsx(collapsed && 'md:hidden')}>
            <p className="text-sm font-bold text-white leading-none tracking-tight">Social AI</p>
            <p className="text-[10px] text-gray-500 mt-0.5">Dashboard</p>
          </div>
        </div>

        {/* Mobile: X close button */}
        <button
          onClick={onClose}
          className="md:hidden text-gray-400 hover:text-gray-200 p-1 rounded-lg hover:bg-gray-900 transition-colors"
          aria-label="Close menu"
        >
          <X size={18} />
        </button>

        {/* Desktop: collapse chevron (hidden when collapsed — shown in footer instead) */}
        <button
          onClick={onToggle}
          className={clsx(
            'hidden md:flex text-gray-400 hover:text-gray-200 transition-colors p-1 rounded-lg hover:bg-gray-900',
            collapsed && 'md:hidden'
          )}
          title="Collapse sidebar"
        >
          <ChevronLeft size={16} />
        </button>
      </div>

      {/* ── Nav links ── */}
      <nav className={clsx(
        'flex-1 py-4 space-y-1 overflow-y-auto overflow-x-hidden',
        collapsed ? 'md:px-2 px-3' : 'px-3'
      )}>
        {nav.map(({ to, icon: Icon, label, badge }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              clsx(
                'relative flex items-center rounded-lg text-sm font-medium transition-all duration-150',
                // Desktop collapsed: icon only
                collapsed ? 'md:justify-center md:w-10 md:h-10 md:mx-auto md:px-0 gap-3 px-3 py-2.5' : 'gap-3 px-3 py-2.5',
                isActive
                  ? 'bg-brand-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900'
              )
            }
          >
            <Icon size={18} className="shrink-0" />

            {/* Label: always show on mobile, hide on desktop when collapsed */}
            <span className={clsx('flex-1 truncate', collapsed && 'md:hidden')}>
              {label}
            </span>

            {/* Badge: message count circle like WhatsApp */}
            {badge && (
              <span className={clsx(
                'w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0',
                collapsed ? 'md:absolute md:top-1 md:right-1 md:w-4 md:h-4 md:text-[8px] hidden md:flex' : 'ml-auto'
              )}>
                {badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Footer: user info + desktop expand button ── */}
      <div className={clsx(
        'border-t border-gray-800 shrink-0',
        collapsed ? 'md:px-2 md:py-3 px-4 py-4' : 'px-4 py-4'
      )}>
        {/* Desktop collapsed: avatar + expand */}
        <div className={clsx('flex-col items-center gap-2', collapsed ? 'md:flex hidden' : 'hidden')}>
          <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
            {user?.full_name?.charAt(0).toUpperCase() || 'U'}
          </div>
          <button
            onClick={onToggle}
            className="text-gray-400 hover:text-gray-200 transition-colors p-1 rounded-lg hover:bg-gray-900"
            title="Expand sidebar"
          >
            <ChevronRight size={14} />
          </button>
        </div>

        {/* Expanded (mobile always, desktop when not collapsed) */}
        <div className={clsx('flex items-center gap-2.5', collapsed ? 'md:hidden flex' : 'flex')}>
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
