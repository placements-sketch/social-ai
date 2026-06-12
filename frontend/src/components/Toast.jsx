import { useEffect, useState, useCallback, createContext, useContext } from 'react'
import { Bell, X } from 'lucide-react'
import clsx from 'clsx'

const ToastContext = createContext(null)

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const showToast = useCallback((toast) => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, ...toast }])
    // Auto-dismiss after 6 seconds
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 6000)
  }, [])

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {/* Toast container — top right, stacked */}
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
    // Slide-in on mount
    requestAnimationFrame(() => setVisible(true))
  }, [])

  return (
    <div
      className={clsx(
        'pointer-events-auto bg-white border border-gray-200 rounded-xl shadow-2xl',
        'w-80 max-w-[calc(100vw-2rem)] overflow-hidden',
        'transition-all duration-300 ease-out',
        visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0',
      )}
    >
      <div className="flex items-start gap-3 p-4">
        <div className="w-8 h-8 rounded-lg bg-brand-50 flex items-center justify-center shrink-0">
          <Bell size={16} className="text-brand-600" />
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