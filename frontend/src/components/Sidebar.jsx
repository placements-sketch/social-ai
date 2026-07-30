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
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard', roles: ['admin', 'agent', 'supervisor'], group: 'Core' },
  { to: '/messages',   icon: MessageSquare,   label: 'Inbox',  roles: ['admin', 'agent', 'supervisor'], group: 'Core' },

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

export default function Sidebar({ collapsed, onToggle, onClose, isMobile = false }) {
  const { user } = useAuth()
  const location = useLocation()
  const nav = allNav.filter(item => item.roles.includes(user?.role))

  // Which parent menus are manually open. Unset = auto (open when a child
  // route is active), so landing on /customers/config shows it expanded.
  const [openMenus, setOpenMenus] = useState({})

  // Live badge for Messages. Counted server-side: this used to pull 100 full
  // conversation records every 15s (~24 KB a poll) just to call .length on a
  // filter, and capped silently at MAX_PER_PAGE — past 100 conversations the
  // badge would under-report forever. /conversations/counts is 49 bytes and
  // has no ceiling.
  const [messagesBadge, setMessagesBadge] = useState(0)
  useEffect(() => {
    let cancelled = false
    const isAgent = user?.role === 'agent'
    const load = async () => {
      try {
        const { getConversationCounts } = await import('../api/messages')
        const counts = await getConversationCounts()
        if (cancelled) return
        // Agents: conversations waiting on a person — the AI handles the rest.
        // Admins / supervisors: unread. Both exclude resolved, server-side.
        setMessagesBadge(isAgent ? (counts.needs_human || 0) : (counts.unread || 0))
      } catch { /* silent — a badge should never crash the sidebar */ }
    }
    load()
    const timer = setInterval(load, 15000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [user?.role])

  return (
    <aside
      className={clsx(
        'h-full flex flex-col rounded-3xl transition-all duration-300 ease-in-out overflow-hidden',
        isMobile ? 'w-full' : (collapsed ? 'w-20' : 'w-60 lg:w-64'),
      )}
      style={{
        background: 'linear-gradient(180deg, #111111 0%, #0d0d0d 100%)',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        borderLeft: '1px solid #c7ea46',
        minHeight: 0,
        maxHeight: '100vh',
      }}
    >
      {/* ── Header: logo + the ONE collapse control ──
          There used to be three controls for this single action: the TopBar
          hamburger, a ChevronLeft here (expanded only), and a ChevronRight
          down in the FOOTER (collapsed only) — so the arrow appeared to jump
          from the top of the sidebar to the bottom when you collapsed it.
          Now: one button, always in the header, in the same place, with the
          chevron flipping to show direction. The TopBar hamburger is mobile-
          only. */}
      <div
        className={clsx(
          'flex shrink-0 px-4 pt-4 lg:pt-5',
          isMobile
            ? 'items-center justify-between h-14 lg:h-16'
            : (collapsed
                // Stacked when narrow — there isn't room for logo and button
                // side by side at 80px, but it stays in the header either way.
                ? 'md:flex-col md:items-center md:gap-3 md:px-0 items-center justify-between h-auto md:pb-1'
                : 'items-center justify-between h-14 lg:h-16')
        )}
      >
        <div className="flex items-center gap-2.5">
          <img src={szLogo} alt="Shop Zetu" className="w-8 h-8 lg:w-9 lg:h-9 shrink-0" />
          <div className={clsx(isMobile ? 'block' : (collapsed ? 'md:hidden' : 'block'))}>
            <p className="text-sm font-bold text-white leading-tight tracking-tight">Shop Zetu</p>
            <p className="text-[11px] text-gray-400 mt-0.5">Social AI</p>
          </div>
        </div>

        <button
          onClick={onClose}
          className={clsx(isMobile ? 'block' : 'md:hidden', 'text-gray-300 hover:text-white p-1 rounded-lg hover:bg-white/5 transition-colors')}
          aria-label="Close menu"
        >
          <X size={18} />
        </button>

        {!isMobile && (
          <button
            onClick={onToggle}
            className="hidden md:flex items-center justify-center w-8 h-8 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        )}
      </div>

      {/* ── Nav links ── */}
      <nav
        className={clsx(
          'flex-1 min-h-0 py-4 lg:py-5 overflow-y-auto overflow-x-hidden hide-scrollbar',
          isMobile ? 'px-3' : (collapsed ? 'md:px-2 px-3' : 'px-3')
        )}
      >
        {['Core', 'Business', 'Admin', 'System'].map((groupName, idx) => {
          const groupItems = nav.filter(item => item.group === groupName)
          if (groupItems.length === 0) return null

          return (
            <div key={groupName} className={idx === 0 ? '' : 'mt-2 lg:mt-3'}>
              {idx > 0 && (
                <div className="mb-2 lg:mb-3 px-3">
                  <div className="h-px bg-gradient-to-r from-transparent via-gray-700 to-transparent" />
                </div>
              )}

              {!collapsed && (
                <p className="text-[11px] font-bold text-gray-400 uppercase tracking-wider px-3 mb-1.5 lg:mb-2">
                  {groupName}
                </p>
              )}

              <div className="space-y-0.5 lg:space-y-1">
                {groupItems.map(({ to, icon: Icon, label, badge, children }) => {
                  const liveBadge = to === '/messages' ? messagesBadge : badge
                  const kids = (children || []).filter(c => c.roles.includes(user?.role))
                  const kidsOpen = openMenus[to] ?? kids.some(c => location.pathname === c.to)
                  const showKids = kids.length > 0 && kidsOpen && (isMobile || !collapsed)
                  return (
                  <div key={to}>
                  <NavLink
                    to={to}
                    title={isMobile ? undefined : (collapsed ? label : undefined)}
                    className={({ isActive }) =>
                      clsx(
                        'relative flex items-center rounded-xl text-sm font-medium transition-all duration-200 ease-in-out',
                        isMobile
                          ? 'gap-3 px-3 py-2'
                          : (collapsed
                              ? 'md:justify-center md:w-10 md:h-10 md:mx-auto md:px-0 gap-3 px-3 py-2'
                              : 'gap-3 px-3 py-1.5 lg:py-2'),
                        // gray-400 on a near-black panel read as disabled.
                        // gray-300 keeps the hierarchy against an active item
                        // without the whole menu looking switched off.
                        isActive
                          ? 'bg-brand-600 text-white shadow-lg'
                          : 'text-gray-300 hover:text-white hover:bg-white/10'
                      )
                    }
                  >
                    <Icon className="shrink-0 w-[16px] h-[16px] lg:w-[18px] lg:h-[18px]" />

                    <span className={clsx('flex-1 truncate', !isMobile && collapsed && 'md:hidden')}>
                      {label}
                    </span>

                    {liveBadge > 0 && (
                      <span
                        className={clsx(
                          'w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center shrink-0',
                          isMobile ? 'ml-auto' : (collapsed ? 'md:absolute md:top-1 md:right-1 md:w-4 md:h-4 md:text-[8px] hidden md:flex' : 'ml-auto')
                        )}
                      >
                        {liveBadge > 99 ? '99+' : liveBadge}
                      </span>
                    )}

                    {kids.length > 0 && (isMobile || !collapsed) && (
                      <span
                        role="button"
                        onClick={(e) => {
                          e.preventDefault(); e.stopPropagation()
                          setOpenMenus(m => ({ ...m, [to]: !kidsOpen }))
                        }}
                        className="ml-auto p-0.5 rounded hover:bg-white/10 shrink-0"
                      >
                        <ChevronDown
                          size={14}
                          className={clsx('transition-transform', kidsOpen && 'rotate-180')}
                        />
                      </span>
                    )}
                  </NavLink>

                  {/* Children were 13px in gray-500 — two steps dimmer AND
                      smaller than their parent, which pushed them past
                      "secondary" into "unreadable". Now 14px in gray-300,
                      one clear step below the parent and nothing more. */}
                  {showKids && (
                    <div className="mt-1 mb-1 ml-[1.4rem] pl-3 border-l border-white/[0.12] space-y-0.5">
                      {kids.map(kid => (
                        <NavLink
                          key={kid.to}
                          to={kid.to}
                          className={({ isActive }) =>
                            clsx(
                              'relative block rounded-lg pl-3 pr-3 py-2 text-sm transition-colors',
                              'before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2',
                              'before:h-1.5 before:w-1.5 before:rounded-full before:transition-colors',
                              isActive
                                ? 'text-white font-semibold bg-white/[0.06] before:bg-brand-500'
                                : 'text-gray-300 hover:text-white hover:bg-white/[0.06] before:bg-white/30 hover:before:bg-brand-500'
                            )
                          }
                        >
                          {kid.label}
                        </NavLink>
                      ))}
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

      {/* ── Footer: user info + desktop expand button ── */}
      <div
        className={clsx(
          'shrink-0',
          isMobile ? 'px-4 py-3' : (collapsed ? 'md:px-2 md:py-3 px-4 py-3' : 'px-4 py-3 lg:py-4')
        )}
      >
        {/* Collapsed: just the avatar. The expand button that used to live
            here has moved to the header, where the collapse button already
            was — one control, one location. */}
        {!isMobile && (
          <div className={clsx('flex-col items-center', collapsed ? 'md:flex hidden' : 'hidden')}>
            <div className="relative" title={`${user?.full_name || 'User'} · ${user?.role || ''}`}>
              <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white">
                {user?.full_name?.charAt(0).toUpperCase() || 'U'}
              </div>
              <PresenceDot
                status={user?.presence || 'online'}
                size="md"
                className="absolute bottom-0 right-0 ring-1 ring-[#0d0d0d]"
              />
            </div>
          </div>
        )}

        <div className={clsx('flex items-center gap-2.5', isMobile ? 'flex' : (collapsed ? 'md:hidden flex' : 'flex'))}>
          <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
            {user?.full_name?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-semibold text-white truncate">{user?.full_name || 'User'}</p>
            <p className="text-[11px] text-gray-400 truncate capitalize">{user?.role || 'user'}</p>
          </div>
          <PresenceDot status={user?.presence || 'online'} />
        </div>
      </div>
    </aside>
  )
}