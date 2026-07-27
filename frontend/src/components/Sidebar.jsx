import { NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, MessageSquare, Package, Bot,
  Zap, BarChart2, ScrollText, Settings, Sparkles,
  ChevronLeft, ChevronRight, ChevronDown, X, Users, UserCircle, Bell,
} from 'lucide-react'
import PresenceDot from './PresenceDot'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import szLogo from '../images/sz.png'

const allNav = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', roles: ['admin', 'agent', 'supervisor'], group: 'Core' },
  { to: '/messages',  icon: MessageSquare,   label: 'Messages',  roles: ['admin', 'agent', 'supervisor'], group: 'Core' },

  { to: '/customers', icon: UserCircle, label: 'Customer Profiling', roles: ['admin', 'supervisor'], group: 'Business',
    children: [
      { to: '/customers/config', label: 'Profiling Config', roles: ['admin', 'supervisor'] },
    ] },
  { to: '/products',  icon: Package,   label: 'Products',  roles: ['admin', 'supervisor'], group: 'Business' },
  { to: '/analytics', icon: BarChart2, label: 'Analytics', roles: ['admin', 'agent', 'supervisor'], group: 'Business' },

  { to: '/ai', icon: Bot, label: 'AI & Automation', roles: ['admin'], group: 'Admin',
    children: [
      { to: '/ai?tab=automation', label: 'Automation Rules', roles: ['admin'] },
    ] },
  { to: '/users',    icon: Users,    label: 'Users',    roles: ['admin'], group: 'Admin' },
  { to: '/settings', icon: Settings, label: 'Settings', roles: ['admin'], group: 'Admin',
    children: [
      { to: '/settings?tab=channels', label: 'Channels', roles: ['admin'] },
    ] },

  { to: '/notifications', icon: Bell, label: 'Activity', roles: ['admin', 'agent', 'supervisor'], group: 'System',
    children: [
      { to: '/logs', label: 'System Logs', roles: ['admin', 'agent', 'supervisor'] },
    ] },
]

const GROUPS = ['Core', 'Business', 'Admin', 'System']

export default function Sidebar({ collapsed, onToggle, onClose, isMobile = false }) {
  const { user } = useAuth()
  const location = useLocation()
  const nav = allNav.filter(item => item.roles.includes(user?.role))
  const [openMenus, setOpenMenus] = useState({})
  const [messagesBadge, setMessagesBadge] = useState(0)

  // Live unread badge for Messages.
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const { listConversations } = await import('../api/messages')
        const data = await listConversations({ page: 1, per_page: 50 })
        if (!alive) return
        const n = (data.conversations || []).filter(
          c => (c.unread_count || 0) > 0 || c.status === 'human_override'
        ).length
        setMessagesBadge(n)
      } catch { /* silent */ }
    }
    load()
    const t = setInterval(load, 15000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  const isChildActive = (kids) =>
    kids.some(c => location.pathname + location.search === c.to || location.pathname === c.to.split('?')[0] && c.to.includes('?') && location.search === '?' + c.to.split('?')[1])

  // treat the icon-only rail as "expanded" on mobile always
  const showLabels = isMobile || !collapsed

  return (
    <aside
      className="flex flex-col h-full w-full rounded-2xl overflow-hidden border border-white/[0.06]"
      style={{ background: 'linear-gradient(180deg, #161616 0%, #0b0b0b 100%)' }}
    >
      {/* ── Header ── */}
      <div className={clsx(
        'flex items-center gap-2.5 shrink-0 border-b border-white/[0.06]',
        showLabels ? 'px-4 py-4' : 'md:px-2 md:py-4 px-4 py-4 md:justify-center'
      )}>
        <img src={szLogo} alt="Shop Zetu" className="w-8 h-8 rounded-lg shrink-0 object-cover" />
        <div className={clsx('flex-1 min-w-0', showLabels ? 'block' : 'md:hidden block')}>
          <p className="text-sm font-bold text-white leading-tight tracking-tight truncate">Shop Zetu</p>
          <p className="text-[10px] text-gray-500 mt-0.5 tracking-wide">Social AI</p>
        </div>

        <button
          onClick={onClose}
          className={clsx(isMobile ? 'block' : 'md:hidden block',
            'text-gray-500 hover:text-white p-1 rounded-lg hover:bg-white/[0.06] transition-colors')}
          aria-label="Close menu"
        >
          <X size={18} />
        </button>

        {!isMobile && !collapsed && (
          <button
            onClick={onToggle}
            className="hidden md:flex text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/[0.06]"
            title="Collapse"
          >
            <ChevronLeft size={16} />
          </button>
        )}
      </div>

      {/* ── Nav ── */}
      <nav className={clsx(
        'flex-1 min-h-0 overflow-y-auto overflow-x-hidden hide-scrollbar py-4',
        showLabels ? 'px-3' : 'md:px-2 px-3'
      )}>
        {GROUPS.map((groupName, gi) => {
          const items = nav.filter(i => i.group === groupName)
          if (!items.length) return null

          return (
            <div key={groupName} className={gi === 0 ? '' : 'mt-6'}>
              {showLabels ? (
                <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-[0.14em] px-3 mb-2">
                  {groupName}
                </p>
              ) : (
                gi > 0 && <div className="mx-auto w-5 h-px bg-white/[0.07] mb-3 mt-1" />
              )}

              <div className="space-y-0.5">
                {items.map(({ to, icon: Icon, label, children }) => {
                  const liveBadge = to === '/messages' ? messagesBadge : 0
                  const kids = (children || []).filter(c => c.roles.includes(user?.role))
                  const childActive = kids.length > 0 && isChildActive(kids)
                  const kidsOpen = openMenus[to] ?? childActive
                  const showKids = kids.length > 0 && kidsOpen && showLabels

                  return (
                    <div key={to}>
                      <NavLink
                        to={to}
                        end={to === '/ai' || to === '/settings' || to === '/notifications'}
                        title={!showLabels ? label : undefined}
                        className={({ isActive }) => clsx(
                          'group relative flex items-center rounded-lg text-sm transition-all duration-150',
                          showLabels ? 'gap-3 pl-3 pr-2 py-2' : 'md:justify-center md:px-0 md:py-2.5 gap-3 pl-3 pr-2 py-2',
                          (isActive || (childActive && !kidsOpen))
                            ? 'bg-white/[0.05] text-white font-semibold'
                            : 'text-gray-400 hover:text-gray-100 hover:bg-white/[0.03] font-medium'
                        )}
                      >
                        {({ isActive }) => (
                          <>
                            {/* active edge marker — the one accent */}
                            <span className={clsx(
                              'absolute left-0 top-1/2 -translate-y-1/2 w-[3px] rounded-r-full bg-brand-500 transition-all duration-200',
                              isActive ? 'h-5 opacity-100' : 'h-0 opacity-0'
                            )} />

                            <Icon size={18} className="shrink-0" />

                            {showLabels && <span className="flex-1 truncate">{label}</span>}

                            {showLabels && liveBadge > 0 && (
                              <span className="shrink-0 min-w-[18px] h-[18px] px-1 rounded-full bg-brand-500 text-white text-[10px] font-bold flex items-center justify-center">
                                {liveBadge > 99 ? '99+' : liveBadge}
                              </span>
                            )}

                            {showLabels && kids.length > 0 && (
                              <span
                                role="button"
                                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpenMenus(m => ({ ...m, [to]: !kidsOpen })) }}
                                className="shrink-0 p-0.5 -mr-0.5 rounded text-gray-500 hover:text-gray-200 hover:bg-white/[0.06]"
                              >
                                <ChevronDown size={14} className={clsx('transition-transform duration-200', kidsOpen && 'rotate-180')} />
                              </span>
                            )}

                            {/* collapsed badge dot */}
                            {!showLabels && liveBadge > 0 && (
                              <span className="md:absolute md:top-1.5 md:right-1.5 w-2 h-2 rounded-full bg-brand-500 hidden md:block" />
                            )}
                          </>
                        )}
                      </NavLink>

                      {/* ── children: one continuous rail, quiet indented links ── */}
                      {showKids && (
                        <div className="relative mt-0.5 mb-1 ml-[1.55rem]">
                          <span className="absolute left-0 top-1 bottom-1 w-px bg-white/[0.08]" />
                          {kids.map(kid => {
                            const active = location.pathname + location.search === kid.to
                              || location.pathname === kid.to.split('?')[0]
                            return (
                              <NavLink
                                key={kid.to}
                                to={kid.to}
                                className={clsx(
                                  'relative block pl-4 pr-3 py-1.5 text-[13px] rounded-r-lg transition-colors duration-150',
                                  active
                                    ? 'text-white font-medium'
                                    : 'text-gray-500 hover:text-gray-200'
                                )}
                              >
                                {/* rail segment lights up for the active child */}
                                <span className={clsx(
                                  'absolute left-0 top-1/2 -translate-y-1/2 w-px transition-all duration-200',
                                  active ? 'h-5 bg-brand-500' : 'h-0 bg-transparent'
                                )} />
                                {kid.label}
                              </NavLink>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </nav>

      {/* ── Footer ── */}
      <div className={clsx(
        'shrink-0 border-t border-white/[0.06]',
        showLabels ? 'px-3 py-3' : 'md:px-2 md:py-3 px-3 py-3'
      )}>
        {!showLabels ? (
          <div className="hidden md:flex flex-col items-center gap-2">
            <div className="relative">
              <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
                {user?.full_name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <PresenceDot status={user?.presence || 'online'} size="md" className="absolute -bottom-0.5 -right-0.5 ring-2 ring-[#0b0b0b]" />
            </div>
            <button onClick={onToggle} className="text-gray-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/[0.06]" title="Expand">
              <ChevronRight size={14} />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-white/[0.03] transition-colors">
            <div className="relative shrink-0">
              <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
                {user?.full_name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <PresenceDot status={user?.presence || 'online'} className="absolute -bottom-0.5 -right-0.5 ring-2 ring-[#0b0b0b]" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-white truncate">{user?.full_name || 'User'}</p>
              <p className="text-[11px] text-gray-500 truncate capitalize">{user?.role || 'user'}</p>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}