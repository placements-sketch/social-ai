import { useEffect, useState, useCallback, createContext, useContext } from 'react'
import { Bell, AlertOctagon, AlertTriangle, X } from 'lucide-react'
import clsx from 'clsx'

const ToastContext = createContext(null)

// Max concurrent toasts. Older ones get pushed out when a new one arrives.
const MAX_VISIBLE_TOASTS = 3

// How long each toast stays before auto-dismissing.
const AUTO_DISMISS_MS = 6000

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const showToast = useCallback((toast, legacySeverity) => {
    const id = Math.random().toString(36).slice(2)

    // Accepts showToast('text'), showToast('text', 'error') and the object
    // form. A string used to fall straight into the spread below, where
    // {...'hello'} becomes {0:'h',1:'e',…} — `title` ended up undefined and the
    // toast rendered as an empty card. Silent, because nothing threw: you got a
    // notification-shaped box with no words in it.
    const t = typeof toast === 'string'
      ? { title: toast, severity: legacySeverity }
      : (toast || {})

    // Callers reach for success/error; the design has three levels. Mapped
    // rather than ignored, so an unrecognised name can't quietly become 'info'
    // and strip the colour off a failure.
    const sev = ({
      success: 'info', info: 'info',
      warning: 'warning', warn: 'warning',
      error: 'urgent', danger: 'urgent', urgent: 'urgent',
    })[t.severity] || 'info'

    setToasts(prev => {
      // If we're at the cap, drop the oldest first
      const trimmed = prev.length >= MAX_VISIBLE_TOASTS
        ? prev.slice(prev.length - MAX_VISIBLE_TOASTS + 1)
        : prev
      return [...trimmed, { ...t, id, severity: sev }]
    })
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, AUTO_DISMISS_MS)
  }, [])

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => (
          <ToastCard key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastCard({ toast, onDismiss }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    requestAnimationFrame(() => setVisible(true))
  }, [])

  // Visual treatment per severity
  const sev = toast.severity || 'info'
  // Severity is carried by the icon and a 3px accent bar down the left edge,
  // not by ringing the whole card in colour. A full bright border reads as a
  // much heavier line than the 1px it is, and it competes with the text it is
  // supposed to be framing.
  const styling = sev === 'urgent'
    ? { Icon: AlertOctagon, iconBg: 'bg-red-50', iconColor: 'text-red-600', accent: 'bg-red-500' }
    : sev === 'warning'
      ? { Icon: AlertTriangle, iconBg: 'bg-amber-50', iconColor: 'text-amber-600', accent: 'bg-amber-500' }
      : { Icon: Bell, iconBg: 'bg-brand-50', iconColor: 'text-brand-600', accent: 'bg-brand-500' }

  return (
    <div
      className={clsx(
        'pointer-events-auto bg-white rounded-xl shadow-2xl relative',
        'w-80 max-w-[calc(100vw-2rem)] overflow-hidden border border-gray-200',
        'transition-all duration-300 ease-out',
        visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0',
      )}
    >
      <span className={clsx('absolute left-0 top-0 bottom-0 w-[3px]', styling.accent)} />
      <div className="flex items-start gap-3 p-4 pl-5">
        <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0', styling.iconBg)}>
          <styling.Icon size={16} className={styling.iconColor} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-gray-900">{toast.title}</p>
          {toast.body && (
            <p className="text-xs text-gray-700 mt-0.5 leading-snug">{toast.body}</p>
          )}
        </div>
        <button
          onClick={onDismiss}
          className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors shrink-0"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}