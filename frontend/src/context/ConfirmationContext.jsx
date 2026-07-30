import { createContext, useState, useCallback, useEffect, useRef } from 'react'
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
        // No default claim about reversibility. The old default said "This
        // action cannot be undone", which is false for most things it guards —
        // disabling the AI, re-opening a conversation, editing a reply are all
        // reversible. A dialog that cries wolf gets clicked through.
        message: options.message || '',
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

  // Only the newest dialog is shown. Rendering the whole stack gave each one
  // its own backdrop, so two at once double-darkened the page and both were
  // clickable — you could dismiss the one underneath.
  const top = confirmations[confirmations.length - 1]

  return (
    <ConfirmationContext.Provider value={{ confirm }}>
      {children}
      {top && <ConfirmationModal key={top.id} {...top} />}
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
  const cancelRef = useRef(null)
  const panelRef = useRef(null)

  useEffect(() => {
    // Escape cancels, matching the image lightbox and every other overlay in
    // the app. Without it the only way out was the mouse.
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); onCancel() }
    }
    document.addEventListener('keydown', onKey)

    // Focus the SAFE action, never the destructive one. Focus used to stay on
    // whatever was behind the dialog, so a stray Enter hit the button the user
    // had just clicked rather than the dialog — and screen readers were never
    // told a dialog had opened at all.
    const previously = document.activeElement
    cancelRef.current?.focus()

    // The page behind must not scroll while a decision is pending.
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      if (previously instanceof HTMLElement) previously.focus()
    }
  }, [onCancel])

  // Keep Tab inside the dialog. A focus ring that wanders off behind the
  // backdrop lets someone activate a control they cannot see.
  const onKeyDownTrap = (e) => {
    if (e.key !== 'Tab') return
    const focusable = panelRef.current?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    if (!focusable?.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40 fade-in" onClick={onCancel} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={message ? 'confirm-message' : undefined}
        onKeyDown={onKeyDownTrap}
        className="relative glass glass-modal pop-in rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4"
      >
        {/* Header */}
        <div className="flex items-start gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
            isDangerous ? 'bg-red-100' : 'bg-amber-100'
          }`}>
            <AlertCircle size={20} className={isDangerous ? 'text-red-600' : 'text-amber-600'} />
          </div>
          <div className="flex-1 min-w-0">
            <h2 id="confirm-title" className="text-lg font-bold text-gray-900">{title}</h2>
          </div>
          <button
            onClick={onCancel}
            aria-label={cancelText}
            className="btn-ghost p-1 shrink-0"
          >
            <X size={18} />
          </button>
        </div>

        {/* Message */}
        {message && (
          <p id="confirm-message" className="text-sm text-gray-600 leading-relaxed">{message}</p>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            ref={cancelRef}
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
  )
}
