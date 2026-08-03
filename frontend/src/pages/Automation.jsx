import { useState, useEffect, useCallback, useContext } from 'react'
import { Zap, Plus, Pencil, Trash2, GripVertical, X, Loader2, Check } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'
import { ModalPortal } from '../context/ModalPortal'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export default function Automation({ embedded = false }) {
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

  // Edit modal state
  const [showEditModal, setShowEditModal] = useState(false)
  const [editData, setEditData] = useState({ id: null, name: '', trigger: '', action: '' })
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState(null)
  const [editSuccess, setEditSuccess] = useState(false)

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
      title: currentEnabled ? 'Disable rule?' : 'Enable rule?',
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
      title: 'Delete rule?',
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

  const openEditModal = (rule) => {
    setEditData({
      id: rule.id,
      name: rule.name,
      trigger: rule.trigger,
      action: rule.action,
    })
    setEditError(null)
    setEditSuccess(false)
    setShowEditModal(true)
  }

  const closeEditModal = () => {
    setShowEditModal(false)
    setEditError(null)
    setEditSuccess(false)
    setEditData({ id: null, name: '', trigger: '', action: '' })
  }

  const updateRule = async (e) => {
    e.preventDefault()
    setEditError(null)
    setEditSuccess(false)

    if (!editData.name.trim() || !editData.trigger.trim() || !editData.action.trim()) {
      setEditError('All fields are required')
      return
    }

    setEditSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/automation-rules/${editData.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify({
          name: editData.name.trim(),
          trigger: editData.trigger.trim(),
          action: editData.action.trim(),
        }),
      })

      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to update rule')

      setEditSuccess(true)
      setRules(prev => prev.map(r => r.id === editData.id ? data.rule : r))

      setTimeout(() => {
        closeEditModal()
      }, 1200)
    } catch (err) {
      setEditError(err.message)
    } finally {
      setEditSubmitting(false)
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

  // Position in the sequence that will actually be evaluated. Disabled rules
  // are skipped at runtime, so they take no number.
  const runOrder = {}
  rules.filter(r => r.enabled).forEach((r, idx) => { runOrder[r.id] = idx + 1 })

  return (
    /* When embedded in the AI & Automation tabs the parent already provides
       the page title and the width constraint, so repeating them here stacked
       two headings on top of each other — "AI & Automation" above the tab bar,
       "Automation Rules" immediately below it — and nested one max-width inside
       an identical one. AISettings already guarded its own title this way;
       this file did not. */
    <div className={clsx('space-y-4 sm:space-y-6 w-full', !embedded && 'max-w-4xl mx-auto')}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-0">
        <div>
          {!embedded && <h1 className="text-2xl font-bold text-gray-900">Automation Rules</h1>}
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

      {/* Moved above the list. It used to sit underneath, so you read five
          rules without knowing that only the first matching one runs — which
          is the single most important thing about this page. */}
      <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
        <p className="text-xs text-gray-600 leading-relaxed">
          <span className="font-bold text-gray-800">Only the first matching rule runs.</span>{' '}
          They are checked top to bottom, after the message's intent is worked out and
          before the AI writes anything. Drag to reorder. Disabled rules are skipped
          entirely.
        </p>
      </div>

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
                'card p-2 sm:p-4 transition-all',
                // Only the grip is grabbable. The whole card was cursor-grab,
                // so hovering anywhere — including over Edit and Delete —
                // suggested you were about to drag something.
                draggedId === rule.id && 'opacity-40 scale-95',
                dragOverId === rule.id && draggedId !== rule.id && 'ring-1 ring-brand-400',
                // A disabled rule should look disabled, not merely have a grey
                // number. It never runs; the row should say so at a glance.
                !rule.enabled && 'opacity-55'
              )}
            >
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-3">
                <div className="flex items-start gap-2 sm:gap-3 flex-1 min-w-0 w-full">
                  <div className="flex items-center gap-2 shrink-0 self-start sm:self-center mt-1 sm:mt-0">
                    <GripVertical size={14} className="text-gray-400 hover:text-gray-600 hidden sm:block cursor-grab active:cursor-grabbing" />
                  </div>
                  {/* Numbered by the order it will actually be CHECKED, not by
                      its position in the list. With rule 2 disabled the old
                      badges read 1,2,3,4 — implying four things run, when the
                      second never fires. A disabled rule gets a dash instead of
                      a number it does not own. */}
                  <div className={clsx(
                    'w-6 h-6 sm:w-8 sm:h-8 rounded-xl flex items-center justify-center text-xs sm:text-sm font-bold shrink-0',
                    rule.enabled ? 'bg-brand-50 text-brand-600' : 'bg-gray-100 text-gray-400'
                  )}
                  title={rule.enabled
                    ? `Checked ${runOrder[rule.id]}${runOrder[rule.id] === 1 ? 'st' : runOrder[rule.id] === 2 ? 'nd' : runOrder[rule.id] === 3 ? 'rd' : 'th'}`
                    : 'Disabled — never checked'}>
                    {rule.enabled ? runOrder[rule.id] : '—'}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-2 mb-2 sm:mb-2.5">
                      <Zap size={12} className={`${rule.enabled ? 'text-brand-500' : 'text-gray-400'} shrink-0 mt-0.5`} />
                      <span className="text-xs sm:text-sm font-bold text-gray-900 break-words">{rule.name}</span>
                      {/* Enabled and runnable are different things. Several
                          rules here are switched On but reference an action or
                          trigger that no code executes, so they sat looking
                          active while doing nothing. The server decides this —
                          the UI just reports it. */}
                      {rule.execution && !rule.execution.runnable && (
                        <span title={rule.execution.reason}
                              className="shrink-0 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200">
                          Never runs
                        </span>
                      )}
                      {rule.execution?.no_op && (
                        <span title={rule.execution.reason}
                              className="shrink-0 inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-md bg-gray-100 text-gray-500 border border-gray-200">
                          No effect
                        </span>
                      )}
                    </div>
                    {rule.execution && (!rule.execution.runnable || rule.execution.no_op) && (
                      <p className="text-[11px] text-amber-700 mb-2 pl-5">{rule.execution.reason}</p>
                    )}

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
                  <button
                    onClick={() => openEditModal(rule)}
                    className="btn-ghost p-1.5 text-xs sm:text-sm hover:text-gray-700"
                    title="Edit rule"
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    onClick={() => deleteRule(rule.id)}
                    className="btn-ghost p-1.5 hover:text-red-500 text-xs sm:text-sm" title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                  <span className={clsx('text-[10px] font-bold uppercase tracking-wide hidden sm:inline',
                    rule.enabled ? 'text-gray-400' : 'text-gray-400')}>
                    {rule.enabled ? 'On' : 'Off'}
                  </span>
                  <button
                    onClick={() => toggleRule(rule.id, rule.enabled)}
                    aria-label={rule.enabled ? `Disable ${rule.name}` : `Enable ${rule.name}`}
                    title={rule.enabled ? 'Disable this rule' : 'Enable this rule'}
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


      {/* New Rule Modal */}
      {showModal && (
        <ModalPortal>
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 fade-in">
            <div className="glass pop-in rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4">
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

      {/* Edit Rule Modal */}
      {showEditModal && (
        <ModalPortal>
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 fade-in">
            <div className="glass pop-in rounded-2xl shadow-2xl max-w-sm w-screen mx-4 p-6 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <h2 className="text-lg font-bold text-gray-900">Edit Rule</h2>
                  <p className="text-xs text-gray-500 mt-0.5">Update trigger or action</p>
                </div>
                <button onClick={closeEditModal} className="btn-ghost p-1 shrink-0">
                  <X size={18} />
                </button>
              </div>

              {editError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600 font-medium">
                  {editError}
                </div>
              )}

              {editSuccess && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700 font-medium flex items-center gap-2">
                  <Check size={14} className="shrink-0" /> Rule updated successfully!
                </div>
              )}

              <form onSubmit={updateRule} className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">Rule Name</label>
                  <input
                    type="text"
                    value={editData.name}
                    onChange={(e) => setEditData(prev => ({ ...prev, name: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">IF Trigger</label>
                  <input
                    type="text"
                    value={editData.trigger}
                    onChange={(e) => setEditData(prev => ({ ...prev, trigger: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1.5">THEN Action</label>
                  <input
                    type="text"
                    value={editData.action}
                    onChange={(e) => setEditData(prev => ({ ...prev, action: e.target.value }))}
                    className="input w-full text-xs"
                    disabled={editSuccess}
                  />
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    type="button"
                    onClick={closeEditModal}
                    className="btn-ghost flex-1 text-sm"
                    disabled={editSubmitting || editSuccess}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editSubmitting || editSuccess}
                    className="flex-1 px-4 py-2 rounded-lg font-semibold text-sm transition-all text-white bg-black hover:bg-gray-800 disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    {editSubmitting ? (
                      <>
                        <Loader2 size={13} className="animate-spin" /> Saving...
                      </>
                    ) : editSuccess ? (
                      <>
                        <Check size={13} /> Saved!
                      </>
                    ) : (
                      <>
                        <Check size={13} /> Save
                      </>
                    )}
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
