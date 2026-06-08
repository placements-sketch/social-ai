import { createContext, useState, useCallback } from 'react'
import { AlertCircle, X } from 'lucide-react'

export const ConfirmationContext = createContext()

export function ConfirmationProvider({ children }) {
  const [confirmations, setConfirmations] = useState([])

  const confirm = useCallback((options) => {
    return new Promise((resolve) => {
      const id = Date.now() + Math.random()
      const confirmation = {
        id,
        title: options.title || 'Are you sure?',
        message: options.message || 'This action cannot be undone.',
        confirmText: options.confirmText || 'Confirm',
        cancelText: options.cancelText || 'Cancel',
        isDangerous: options.isDangerous || false,
        onConfirm: () => {
          setConfirmations(prev => prev.filter(c => c.id !== id))
          resolve(true)
        },
        onCancel: () => {
          setConfirmations(prev => prev.filter(c => c.id !== id))
          resolve(false)
        },
      }
      setConfirmations(prev => [...prev, confirmation])
    })
  }, [])

  return (
    <ConfirmationContext.Provider value={{ confirm }}>
      {children}
      <div className="fixed inset-0 pointer-events-none z-50 flex items-center justify-center">
        {confirmations.map(confirmation => (
          <ConfirmationModal key={confirmation.id} {...confirmation} />
        ))}
      </div>
    </ConfirmationContext.Provider>
  )
}

function ConfirmationModal({
  title,
  message,
  confirmText,
  cancelText,
  isDangerous,
  onConfirm,
  onCancel,
}) {
  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onCancel} />
      <div className="relative z-50 pointer-events-auto">
        <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4">
          {/* Header */}
          <div className="flex items-start gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
              isDangerous ? 'bg-red-100' : 'bg-amber-100'
            }`}>
              <AlertCircle size={20} className={isDangerous ? 'text-red-600' : 'text-amber-600'} />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-bold text-gray-900">{title}</h2>
            </div>
            <button
              onClick={onCancel}
              className="btn-ghost p-1 shrink-0"
            >
              <X size={18} />
            </button>
          </div>

          {/* Message */}
          <p className="text-sm text-gray-600 leading-relaxed">{message}</p>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={onCancel}
              className="btn-ghost flex-1 text-sm"
            >
              {cancelText}
            </button>
            <button
              onClick={onConfirm}
              className={`flex-1 px-4 py-2 rounded-lg font-semibold text-sm transition-all text-white ${
                isDangerous
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-black hover:bg-gray-800'
              }`}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
