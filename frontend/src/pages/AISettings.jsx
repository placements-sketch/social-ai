import { useState, useEffect, useContext } from 'react'
import { Save, RotateCcw, Loader2, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const TONES = ['friendly', 'luxury', 'gen_z', 'minimalist', 'bold_sales']

const TONE_LABELS = {
  friendly: 'Friendly',
  luxury: 'Luxury',
  gen_z: 'Gen Z',
  minimalist: 'Minimalist',
  bold_sales: 'Bold & Sales',
}

const RESPONSE_RULES = [
  { key: 'auto_greet', label: 'Auto-greet new conversations' },
  { key: 'mention_delivery_in_kenya', label: 'Mention nationwide delivery in Kenya' },
  { key: 'use_emoji', label: 'Use emojis in responses' },
  { key: 'always_offer_alternatives_when_out_of_stock', label: 'Suggest alternatives when product is out of stock' },
]

export default function AISettings({ embedded = false }) {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)
  const { confirm } = useContext(ConfirmationContext)

  // Local form state
  const [formData, setFormData] = useState({
    tone: 'friendly',
    system_prompt: '',
    slider_formal: 40,
    slider_length: 50,
    slider_sales: 60,
    response_rules: {},
  })

  // A copy of what the server last gave us. Everything below compares against
  // this to know whether there are unsaved edits — the page previously had no
  // idea, so Save was always live and leaving with unsaved changes was silent.
  const [saved, setSaved] = useState(null)

  useEffect(() => {
    fetchSettings()
  }, [])

  const dirty = saved != null && JSON.stringify(saved) !== JSON.stringify(formData)

  // Name the fields that differ, so the save bar can say what it will write
  // rather than just that something changed.
  const changedFields = (() => {
    if (!saved) return []
    const names = {
      tone: 'brand tone', system_prompt: 'system prompt',
      slider_formal: 'formality', slider_length: 'response length',
      slider_sales: 'sales focus', response_rules: 'response rules',
    }
    return Object.keys(names).filter(
      (k) => JSON.stringify(saved[k]) !== JSON.stringify(formData[k])
    ).map((k) => names[k])
  })()

  // Leaving with unsaved edits should cost a confirmation, not a shrug.
  useEffect(() => {
    if (!dirty) return
    const warn = (e) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/ai-settings`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load settings')
      const data = await res.json()
      setSettings(data.settings)
      const loaded = {
        tone: data.settings.tone,
        system_prompt: data.settings.system_prompt,
        slider_formal: data.settings.slider_formal,
        slider_length: data.settings.slider_length,
        slider_sales: data.settings.slider_sales,
        response_rules: data.settings.response_rules || {},
      }
      setFormData(loaded)
      setSaved(loaded)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/ai-settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify(formData),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Failed to save settings')
      }
      const data = await res.json()
      setSettings(data.settings)
      // Re-baseline, or the save bar never goes away: the dirty check compares
      // formData against the last saved snapshot, and a successful write makes
      // formData the new truth.
      setSaved(formData)
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    const confirmed = await confirm({
      title: 'Reset all settings?',
      message: 'All AI settings will be reset to their default values. This action cannot be undone.',
      confirmText: 'Reset',
      cancelText: 'Cancel',
      isDangerous: true,
    })

    if (!confirmed) return

    setSaving(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/ai-settings/reset`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to reset settings')
      const data = await res.json()
      setSettings(data.settings)
      setFormData({
        tone: data.settings.tone,
        system_prompt: data.settings.system_prompt,
        slider_formal: data.settings.slider_formal,
        slider_length: data.settings.slider_length,
        slider_sales: data.settings.slider_sales,
        response_rules: data.settings.response_rules || {},
      })
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const toggleRule = async (key) => {
    const newValue = !formData.response_rules[key]
    const confirmed = await confirm({
      title: newValue ? 'Enable rule?' : 'Disable rule?',
      message: `This response rule will be ${newValue ? 'enabled' : 'disabled'} for all conversations.`,
      confirmText: newValue ? 'Enable' : 'Disable',
      cancelText: 'Cancel',
    })

    if (!confirmed) return

    setFormData(prev => ({
      ...prev,
      response_rules: {
        ...prev.response_rules,
        [key]: newValue,
      },
    }))
  }

  if (loading) {
    return (
      <div className={clsx('space-y-6 w-full', !embedded && 'max-w-4xl mx-auto')}>
        <SkeletonHeader />
        <div className="space-y-4">
          <div className="card p-5 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i}>
                <div className="h-4 bg-gray-200 rounded w-1/4 mb-2 animate-pulse" />
                <div className="h-10 bg-gray-100 rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={clsx('space-y-6 w-full', !embedded && 'max-w-4xl mx-auto')}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          {!embedded && <h1 className="text-2xl font-bold text-gray-900">AI Settings</h1>}
          {!embedded && <p className="text-sm text-gray-500 mt-1">Customize your AI assistant's personality and behavior</p>}
        </div>
        {/* Save has moved to a bar that appears when there is something to
            save. It used to sit up here, so you edited four sections below it
            and scrolled back to the top to commit — and Reset sat immediately
            beside it at equal weight, one click from wiping the configuration.
            Reset now lives at the foot of the page with the other irreversible
            things. */}
        {dirty && (
          <span className="text-[12px] font-semibold text-amber-600 whitespace-nowrap">
            Unsaved changes
          </span>
        )}
      </div>

      {/* Alert messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex gap-2 text-xs">
          <AlertCircle size={16} className="text-red-600 shrink-0 mt-0.5" />
          <p className="text-red-700 font-medium">{error}</p>
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3 flex gap-2 text-xs">
          <div className="w-2 h-2 rounded-full bg-green-500 mt-1 shrink-0" />
          <p className="text-green-700 font-medium">Settings saved successfully</p>
        </div>
      )}

      {/* Brand Tone */}
      <div className="card p-5 space-y-3">
        <h2 className="text-sm font-bold text-gray-900">Brand Tone</h2>
        <p className="text-xs text-gray-500">Choose the primary personality for your AI assistant</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {TONES.map(tone => (
            <button
              key={tone}
              onClick={() => setFormData(prev => ({ ...prev, tone }))}
              className={clsx(
                'px-2 py-1.5 rounded-lg text-xs font-semibold border transition-all',
                formData.tone === tone
                  ? 'bg-brand-50 border-brand-500 text-brand-600'
                  : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
              )}
            >
              {TONE_LABELS[tone]}
            </button>
          ))}
        </div>
      </div>

      {/* Personality Sliders */}
      <div className="card p-5 space-y-4">
        <h2 className="text-sm font-bold text-gray-900">Personality Sliders</h2>

        {/* A bare "50%" says nothing about what the assistant will actually do.
            Each slider now reads back its own position in words. */}
        {[
          { key: 'slider_formal', label: 'Formality', left: 'Casual', right: 'Formal',
            says: (v) => v < 33 ? 'Chatty and informal' : v > 66 ? 'Polished and professional' : 'Warm but businesslike' },
          { key: 'slider_length', label: 'Response length', left: 'Brief', right: 'Detailed',
            says: (v) => v < 33 ? 'Short, to the point' : v > 66 ? 'Full explanations' : 'A sentence or two' },
          { key: 'slider_sales', label: 'Sales focus', left: 'Neutral', right: 'Salesy',
            says: (v) => v < 33 ? 'Answers only, no pitching' : v > 66 ? 'Actively suggests products' : 'Mentions products when relevant' },
        ].map(({ key, label, left, right, says }) => (
          <div key={key} className="space-y-2">
            <div className="flex items-end justify-between gap-3">
              <label className="text-xs font-semibold text-gray-900">{label}</label>
              <span className="text-[12px] text-gray-500 text-right">{says(formData[key])}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-10">{left}</span>
              <input
                type="range"
                min="0"
                max="100"
                value={formData[key]}
                onChange={e => setFormData(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                className="flex-1 h-1.5 rounded-full appearance-none bg-gray-200 accent-brand-500 cursor-pointer"
              />
              <span className="text-xs text-gray-500 w-10 text-right">{right}</span>
            </div>
          </div>
        ))}
      </div>

      {/* System Prompt.
          This is the most powerful control in the product — it governs every
          reply the assistant sends to every customer on every channel — and it
          was presented as a plain textarea with a character count, visually
          identical to the tone picker above it. The amber edge and the warning
          are the only thing separating "make it a bit friendlier" from "change
          what the business says to people". */}
      <div className="card p-5 space-y-2 border-l-2 border-l-amber-400">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-gray-900">System prompt</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              The standing instructions sent before every reply, on every channel.
            </p>
          </div>
          <span className="text-[11px] font-bold uppercase tracking-wide text-amber-600 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 shrink-0">
            Affects every reply
          </span>
        </div>
        <textarea
          value={formData.system_prompt}
          onChange={e => setFormData(prev => ({ ...prev, system_prompt: e.target.value }))}
          rows={8}
          className="input w-full resize-none font-mono text-xs leading-relaxed"
          placeholder="Enter system prompt..."
        />
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="text-gray-400">{formData.system_prompt.length} characters</span>
          {formData.system_prompt.trim().length === 0 && (
            <span className="text-amber-600 font-semibold">
              Empty — the assistant will reply with no standing instructions
            </span>
          )}
        </div>
      </div>

      {/* Response Rules */}
      <div className="card p-5 space-y-3">
        <h2 className="text-sm font-bold text-gray-900">Response Rules</h2>
        <div className="space-y-2">
          {RESPONSE_RULES.map(rule => (
            <div key={rule.key} className="flex items-center justify-between gap-3 py-1.5 px-2 rounded hover:bg-gray-50 transition-colors">
              <span className="text-xs text-gray-700 font-medium">{rule.label}</span>
              <button
                onClick={() => toggleRule(rule.key)}
                className={clsx(
                  'relative inline-flex w-10 h-6 rounded-full transition-colors duration-200 shrink-0',
                  formData.response_rules[rule.key] ? 'bg-brand-500' : 'bg-gray-300'
                )}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform duration-200"
                  style={{ transform: formData.response_rules[rule.key] ? 'translateX(16px)' : 'translateX(0px)' }}
                />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Irreversible things live together, at the end, away from Save. */}
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-bold text-red-800">Reset to defaults</p>
          <p className="text-[12px] text-red-700 mt-0.5 leading-relaxed">
            Discards your tone, sliders, system prompt and response rules, and puts
            the assistant back to how it shipped. There is no undo.
          </p>
        </div>
        <button
          onClick={handleReset}
          disabled={saving}
          className="shrink-0 text-[12px] font-bold px-3 py-1.5 rounded-lg border border-red-300 text-red-700 hover:bg-red-100 transition-colors disabled:opacity-50"
        >
          <RotateCcw size={12} className="inline mr-1 -mt-px" /> Reset
        </button>
      </div>

      {/* Save bar. Appears only when there is something to save, names what
          changed, and stays in reach wherever you are on the page. */}
      {dirty && (
        <div className="sticky bottom-4 z-20">
          <div className="card glass-modal rounded-xl px-4 py-3 flex items-center justify-between gap-4 shadow-2xl">
            <div className="min-w-0">
              <p className="text-xs font-bold text-gray-900">Unsaved changes</p>
              <p className="text-[12px] text-gray-500 truncate">
                {changedFields.length ? changedFields.join(', ') : 'settings'}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => setFormData(saved)}
                disabled={saving}
                className="text-[12px] font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-600 hover:text-gray-900 disabled:opacity-50"
              >
                Discard
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn-primary flex items-center gap-1.5 text-xs px-4 py-2 disabled:opacity-50"
              >
                {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                Save changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
