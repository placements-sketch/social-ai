import { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'

export default function Layout() {
  // On mobile: sidebar starts closed. On desktop: starts open.
  const [mobileOpen, setMobileOpen]   = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(false)

  const location = useLocation()

  // Close mobile drawer whenever the route changes
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Close mobile drawer on resize to desktop
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 768) setMobileOpen(false)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-white">

      {/* ── Mobile backdrop — sits behind drawer, closes it on tap ── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/10 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar ──
          Mobile:  fixed overlay, slides in/out, z-30 (above backdrop)
          Desktop: normal flow, collapsible
      ── */}
      <div
        className={[
          // Mobile: fixed drawer
          'fixed inset-y-0 left-0 z-30 md:static md:z-auto',
          // Mobile open/close
          'transition-transform duration-300 ease-in-out',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
          // Desktop: always visible, no translate
          'md:translate-x-0',
        ].join(' ')}
      >
        <Sidebar
          collapsed={desktopCollapsed}
          onToggle={() => setDesktopCollapsed(c => !c)}
          onClose={() => setMobileOpen(false)}
        />
      </div>

      {/* ── Main content — always full width on mobile ── */}
      <div className="flex flex-col flex-1 overflow-hidden min-w-0 w-full">
        <TopBar
          onMenuClick={() => {
            if (window.innerWidth < 768) {
              setMobileOpen(o => !o)
            } else {
              setDesktopCollapsed(c => !c)
            }
          }}
        />
        <main className="flex-1 overflow-y-auto p-4 md:p-8 w-full bg-white">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
