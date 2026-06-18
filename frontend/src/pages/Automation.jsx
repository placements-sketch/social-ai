import { useState, useEffect, useCallback, useContext } from 'react'
import { Zap, Plus, Pencil, Trash2, GripVertical, X, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'
import { ModalPortal } from '../context/ModalPortal'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export default function Automation() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [draggedId, setDraggedId] = useState(null)
  const [dragOverId, setDragOverId] = useState(null)
  const { confirm } = useContext(ConfirmationContext)
  
  // Modal state
  const [showModal, setShowModal] = useState(false)
  const [modalData, setModalData] = useState({ name: '', trigger: '', action: '', enabled: true })
  const [submitting, setSubmitting] = useState(false)
  const [modalError, setModalError] = useState(null)

  // Fetch rules
  const fetchRules = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/automation-rules`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load rules')
      const data = await res.json()
      setRules(data.rules || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchRules()
  }, [fetchRules])

  const toggleRule = async (id, currentEnabled) => {
    const confirmed = await confirm({
      title: currentEnabled ? 'Disable Rule?' : 'Enable Rule?',
      message: currentEnabled
        ? 'This automation rule will be skipped during evaluation.'
        : 'This automation rule will be active again.',
      confirmText: currentEnabled ? 'Disable' : 'Enable',
      cancelText: 'Cancel',
    })

    if (!confirmed) return

    try {
      const res = await fetch(`${API_BASE}/automation-rules/${id}/toggle`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to toggle rule')
      const data = await res.json()
      setRules(prev => prev.map(r => r.id === id ? data.rule : r))
    } catch (err) {
      console.error('Toggle failed:', err)
    }
  }

  const deleteRule = async (id) => {
    const confirmed = await confirm({
      title: 'Delete Rule?',
      message: 'This automation rule will be permanently deleted. This action cannot be undone.',
      confirmText: 'Delete',
      cancelText: 'Cancel',
      isDangerous: true,
    })

    if (!confirmed) return

    try {
      const res = await fetch(`${API_BASE}/automation-rules/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to delete rule')
      setRules(prev => prev.filter(r => r.id !== id))
    } catch (err) {
      console.error('Delete failed:', err)
    }
  }

  const createRule = async (e) => {
    e.preventDefault()
    if (!modalData.name.trim() || !modalData.trigger.trim() || !modalData.action.trim()) {
      setModalError('All fields are required')
      return
    }

    setSubmitting(true)
    setModalError(null)
    try {
      const res = await fetch(`${API_BASE}/automation-rules`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify(modalData),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Failed to create rule')
      }
      const data = await res.json()
      setRules(prev => [...prev, data.rule])
      setShowModal(false)
      setModalData({ name: '', trigger: '', action: '', enabled: true })
    } catch (err) {
      setModalError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDragStart = (e, ruleId) => {
    setDraggedId(ruleId)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/html', e.currentTarget)
  }

  const handleDragOver = (e, ruleId) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverId(ruleId)
  }

  const handleDragLeave = () => {
    setDragOverId(null)
  }

  const handleDrop = (e, targetId) => {
    e.preventDefault()
    setDragOverId(null)

    if (!draggedId || draggedId === targetId) {
      setDraggedId(null)
      return
    }

    const draggedIndex = rules.findIndex(r => r.id === draggedId)
    const targetIndex = rules.findIndex(r => r.id === targetId)

    if (draggedIndex === -1 || targetIndex === -1) {
      setDraggedId(null)
      return
    }

    const newRules = [...rules]
    const [draggedRule] = newRules.splice(draggedIndex, 1)
    newRules.splice(targetIndex, 0, draggedRule)

    setRules(newRules)
    setDraggedId(null)

    // Send reorder to backend
    const order = newRules.map(r => r.id)
    fetch(`${API_BASE}/automation-rules/reorder`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('authToken')}`,
      },
      body: JSON.stringify({ order }),
    }).catch(err => console.error('Reorder failed:', err))
  }

  const handleDragEnd = () => {
    setDraggedId(null)
    setDragOverId(null)
  }

  return (
    <div className="space-y-4 sm:space-y-6 w-full max-w-4xl mx-auto">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Automation Rules</h1>
          <p className="text-sm text-gray-500 mt-0.5">Define how the AI handles specific scenarios</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="btn-primary flex items-center gap-1.5 text-xs py-2 px-3 sm:py-1.5 sm:px-2.5 w-full sm:w-auto justify-center sm:justify-start shrink-0"
        >
          <Plus size={13} /> New Rule
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-4 sm:space-y-6">
          <SkeletonList count={4} />
        </div>
      ) : (
        <div className="space-y-2 sm:space-y-3">
          {rules.map((rule, i) => (
            <div
              key={rule.id}
              draggable
              onDragStart={(e) => handleDragStart(e, rule.id)}
              onDragOver={(e) => handleDragOver(e, rule.id)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, rule.id)}
              onDragEnd={handleDragEnd}
              className={clsx(
                'card p-2 sm:p-4 transition-all cursor-grab active:cursor-grabbing',
                draggedId === rule.id && 'opacity-40 scale-95',
                dragOverId === rule.id && draggedId !== rule.id && 'border-2 border-brand-400 bg-brand-50'
              )}
            >
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-3">
                <div className="flex items-start gap-2 sm:gap-3 flex-1 min-w-0 w-full">
                  <div className="flex items-center gap-2 shrink-0 self-start sm:self-center mt-1 sm:mt-0">
                    <GripVertical size={14} className="text-gray-400 hover:text-gray-600 hidden sm:block" />
                  </div>
                  <div className={clsx(
                    'w-6 h-6 sm:w-8 sm:h-8 rounded-xl flex items-center justify-center text-xs sm:text-sm font-bold shrink-0',
                    rule.enabled ? 'bg-brand-50 text-brand-600' : 'bg-gray-100 text-gray-400'
                  )}>
                    {i + 1}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-2 mb-2 sm:mb-2.5">
                      <Zap size={12} className={`${rule.enabled ? 'text-brand-500' : 'text-gray-400'} shrink-0 mt-0.5`} />
                      <span className="text-xs sm:text-sm font-bold text-gray-900 break-words">{rule.name}</span>
                    </div>

                    <div className="space-y-1.5 sm:space-y-2">
                      <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-2">
                        <span className="text-xs font-bold text-gray-400 shrink-0">IF</span>
                        <span className="text-xs text-gray-700 bg-gray-50 border border-gray-200 px-2 sm:px-2.5 py-1 sm:py-1.5 rounded-lg font-medium break-words">{rule.trigger}</span>
                      </div>
                      <div className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-2">
                        <span className="text-xs font-bold text-gray-400 shrink-0">THEN</span>
                        <span className="text-xs text-brand-700 bg-brand-50 border border-brand-100 px-2 sm:px-2.5 py-1 sm:py-1.5 rounded-lg font-medium break-words">{rule.action}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0 w-full sm:w-auto justify-end">
                  <button className="btn-ghost p-1.5 text-xs sm:text-sm" title="Edit"><Pencil size={13} /></button>
                  <button
                    onClick={() => deleteRule(rule.id)}
                    className="btn-ghost p-1.5 hover:text-red-500 text-xs sm:text-sm" title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                  <button
                    onClick={() => toggleRule(rule.id, rule.enabled)}
                    className={`relative inline-flex w-10 sm:w-11 h-5 sm:h-6 rounded-full transition-colors duration-200 shrink-0 ${rule.enabled ? 'bg-brand-500' : 'bg-gray-300'}`}
                  >
                    <span
                      className="absolute top-0.5 sm:top-1 left-0.5 sm:left-1 w-4 h-4 rounded-full bg-white shadow transition-all duration-200"
                      style={{ transform: rule.enabled ? 'translateX(18px)' : 'translateX(0px)' }}
                    />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-brand-50 border border-brand-100 rounded-xl p-3 sm:p-4">
        <p className="text-xs text-brand-700 leading-relaxed font-medium">
          <strong>Rules run in order</strong> — the first matching rule wins.
          Disabled rules are skipped entirely.
          Rules are evaluated after intent detection and before the AI generates a reply.
        </p>
      </div>

      {/* New Rule Modal */}
      {showModal && (
        <ModalPortal>
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
            <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4">
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900">Create New Rule</h2>
                <p className="text-xs text-gray-500 mt-0.5">Define a new automation rule for your AI</p>
              </div>
              <button
                onClick={() => {
                  setShowModal(false)
                  setModalError(null)
                  setModalData({ name: '', trigger: '', action: '', enabled: true })
                }}
                className="btn-ghost p-1 shrink-0"
              >
                <X size={18} />
              </button>
            </div>

            {modalError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600 font-medium">
                {modalError}
              </div>
            )}

            <form onSubmit={createRule} className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">Rule Name</label>
                <input
                  type="text"
                  placeholder="e.g., Price Reply"
                  value={modalData.name}
                  onChange={(e) => setModalData(prev => ({ ...prev, name: e.target.value }))}
                  className="input w-full text-xs"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">IF Trigger</label>
                <input
                  type="text"
                  placeholder="e.g., Message contains: 'price'"
                  value={modalData.trigger}
                  onChange={(e) => setModalData(prev => ({ ...prev, trigger: e.target.value }))}
                  className="input w-full text-xs"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 block mb-1.5">THEN Action</label>
                <input
                  type="text"
                  placeholder="e.g., Always include price from Shopify in reply"
                  value={modalData.action}
                  onChange={(e) => setModalData(prev => ({ ...prev, action: e.target.value }))}
                  className="input w-full text-xs"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false)
                    setModalError(null)
                    setModalData({ name: '', trigger: '', action: '', enabled: true })
                  }}
                  className="btn-ghost flex-1 text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2 rounded-lg font-semibold text-sm transition-all text-white bg-black hover:bg-gray-800 disabled:opacity-50 flex items-center justify-center gap-1.5"
                >
                  {submitting ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
        </ModalPortal>
      )}
    </div>
  )
}
