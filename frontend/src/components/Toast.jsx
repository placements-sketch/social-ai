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

  const showToast = useCallback((toast) => {
    const id = Math.random().toString(36).slice(2)
    const sev = toast.severity || 'info'
    setToasts(prev => {
      // If we're at the cap, drop the oldest first
      const trimmed = prev.length >= MAX_VISIBLE_TOASTS
        ? prev.slice(prev.length - MAX_VISIBLE_TOASTS + 1)
        : prev
      return [...trimmed, { id, severity: sev, ...toast }]
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
  const styling = sev === 'urgent'
    ? { Icon: AlertOctagon, iconBg: 'bg-red-50', iconColor: 'text-red-600', border: 'border-red-200' }
    : sev === 'warning'
      ? { Icon: AlertTriangle, iconBg: 'bg-amber-50', iconColor: 'text-amber-600', border: 'border-amber-200' }
      : { Icon: Bell, iconBg: 'bg-brand-50', iconColor: 'text-brand-600', border: 'border-gray-200' }

  return (
    <div
      className={clsx(
        'pointer-events-auto bg-white rounded-xl shadow-2xl',
        'w-80 max-w-[calc(100vw-2rem)] overflow-hidden border',
        styling.border,
        'transition-all duration-300 ease-out',
        visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0',
      )}
    >
      <div className="flex items-start gap-3 p-4">
        <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center shrink-0', styling.iconBg)}>
          <styling.Icon size={16} className={styling.iconColor} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-gray-900">{toast.title}</p>
          {toast.body && (
            <p className="text-xs text-gray-600 mt-0.5 leading-snug">{toast.body}</p>
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