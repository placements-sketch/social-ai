import { useState, useEffect, useCallback } from 'react'
import { Zap, Plus, Pencil, Trash2, GripVertical, X, Loader2 } from 'lucide-react'
import clsx from 'clsx'

export default function Automation() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [draggedId, setDraggedId] = useState(null)
  const [dragOverId, setDragOverId] = useState(null)
  
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
      const res = await fetch('/api/automation-rules', {
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
    try {
      const res = await fetch(`/api/automation-rules/${id}/toggle`, {
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
    if (!confirm('Delete this rule?')) return
    try {
      const res = await fetch(`/api/automation-rules/${id}`, {
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
      const res = await fetch('/api/automation-rules', {
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
    fetch('/api/automation-rules/reorder', {
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
    <div className="space-y-6 w-full max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Automation Rules</h1>
          <p className="text-sm text-gray-500 mt-0.5">Define how the AI handles specific scenarios</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="btn-primary flex items-center gap-1.5 text-xs py-1.5 px-2.5"
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
        <div className="flex items-center justify-center py-12">
          <Loader2 size={20} className="animate-spin text-brand-500" />
        </div>
      ) : (
        <div className="space-y-3">
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
                'card p-4 transition-all cursor-grab active:cursor-grabbing',
                draggedId === rule.id && 'opacity-40 scale-95',
                dragOverId === rule.id && draggedId !== rule.id && 'border-2 border-brand-400 bg-brand-50'
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <div className="flex items-center gap-2 shrink-0 self-center">
                    <GripVertical size={16} className="text-gray-400 hover:text-gray-600" />
                  </div>
                  <div className={clsx(
                    'w-8 h-8 rounded-xl flex items-center justify-center text-sm font-bold',
                    rule.enabled ? 'bg-brand-50 text-brand-600' : 'bg-gray-100 text-gray-400'
                  )}>
                    {i + 1}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2.5">
                      <Zap size={13} className={rule.enabled ? 'text-brand-500' : 'text-gray-400'} />
                      <span className="text-sm font-bold text-gray-900">{rule.name}</span>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-start gap-2">
                        <span className="text-xs font-bold text-gray-400 w-10 shrink-0 mt-1">IF</span>
                        <span className="text-xs text-gray-700 bg-gray-50 border border-gray-200 px-2.5 py-1.5 rounded-lg font-medium">{rule.trigger}</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="text-xs font-bold text-gray-400 w-10 shrink-0 mt-1">THEN</span>
                        <span className="text-xs text-brand-700 bg-brand-50 border border-brand-100 px-2.5 py-1.5 rounded-lg font-medium">{rule.action}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <button className="btn-ghost p-1.5" title="Edit"><Pencil size={13} /></button>
                  <button
                    onClick={() => deleteRule(rule.id)}
                    className="btn-ghost p-1.5 hover:text-red-500" title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                  <button
                    onClick={() => toggleRule(rule.id, rule.enabled)}
                    className={`relative inline-flex w-11 h-6 rounded-full transition-colors duration-200 ${rule.enabled ? 'bg-brand-500' : 'bg-gray-300'}`}
                  >
                    <span
                      className="absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-all duration-200"
                      style={{ transform: rule.enabled ? 'translateX(20px)' : 'translateX(0px)' }}
                    />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-brand-50 border border-brand-100 rounded-xl p-4">
        <p className="text-xs text-brand-700 leading-relaxed font-medium">
          <strong>Rules run in order</strong> — the first matching rule wins.
          Disabled rules are skipped entirely.
          Rules are evaluated after intent detection and before the AI generates a reply.
        </p>
      </div>

      {/* New Rule Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-lg max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-900">Create New Rule</h2>
              <button
                onClick={() => {
                  setShowModal(false)
                  setModalError(null)
                  setModalData({ name: '', trigger: '', action: '', enabled: true })
                }}
                className="btn-ghost p-1"
              >
                <X size={18} />
              </button>
            </div>

            {modalError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">
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

              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false)
                    setModalError(null)
                    setModalData({ name: '', trigger: '', action: '', enabled: true })
                  }}
                  className="btn-ghost flex-1 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary flex-1 text-xs flex items-center justify-center gap-1.5"
                >
                  {submitting ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
