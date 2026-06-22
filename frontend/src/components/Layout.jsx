import { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import ScrollToTop from './ScrollToTop'
import clsx from 'clsx'

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false) // Mobile: closed by default
  const [desktopCollapsed, setDesktopCollapsed] = useState(true) // Desktop: collapsed by default

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
    <div style={{ 
      display: 'flex', 
      height: '100vh', 
      overflow: 'hidden', 
      backgroundColor: '#ffffff',
      width: '100%',
      maxWidth: '100vw',
    }}>

      {/* ── Mobile backdrop ── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/20 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Desktop sidebar container (collapsible) ── */}
      <div 
        className="hidden md:flex flex-col gap-2 p-2 lg:gap-3 lg:p-3 bg-transparent shrink-0"
        style={{ minWidth: 0, height: '100vh' }}
      >
        <Sidebar
          collapsed={desktopCollapsed}
          onToggle={() => setDesktopCollapsed(c => !c)}
          onClose={() => setMobileOpen(false)}
          isMobile={false}
        />
      </div>

      {/* ── Mobile sidebar overlay (floating, full height with padding) ── */}
      {mobileOpen && (
        <>
          <div
            className="fixed inset-0 z-20 bg-black/20"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div
            style={{ 
              top: '12px',
              left: '12px',
              bottom: '12px',
              width: 'calc(100% - 24px)',
              maxWidth: '280px',
              display: 'flex',
              flexDirection: 'column',
              pointerEvents: 'none',
              position: 'fixed',
              zIndex: 30
            }}
          >
            <div style={{ pointerEvents: 'auto', height: '100%', display: 'flex' }}>
              <Sidebar
                collapsed={false}
                onToggle={() => {}}
                onClose={() => setMobileOpen(false)}
                isMobile={true}
              />
            </div>
          </div>
        </>
      )}

      {/* ── Main content ── */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', minWidth: 0, width: '100%', backgroundColor: 'transparent' }}>
        <TopBar
          onMenuClick={() => {
            if (window.innerWidth < 768) {
              setMobileOpen(o => !o)
            } else {
              setDesktopCollapsed(c => !c)
            }
          }}
        />
        <main className={clsx(
          "flex-1 w-full min-w-0 bg-transparent relative",
          location.pathname === '/messages'
            ? "overflow-hidden p-0"
            : "overflow-y-auto overflow-x-hidden px-4 py-3 md:px-6 md:py-4 lg:px-8 lg:py-5"
        )}>
          <Outlet />
        </main>
      </div>

      <ScrollToTop />
    </div>
  )
}
