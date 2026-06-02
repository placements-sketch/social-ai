import { useState, useEffect } from 'react'
import { Save, RotateCcw, Loader2, AlertCircle } from 'lucide-react'
import clsx from 'clsx'

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

export default function AISettings() {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  // Local form state
  const [formData, setFormData] = useState({
    tone: 'friendly',
    system_prompt: '',
    slider_formal: 40,
    slider_length: 50,
    slider_sales: 60,
    response_rules: {},
  })

  useEffect(() => {
    fetchSettings()
  }, [])

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/ai-settings', {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load settings')
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
      const res = await fetch('/api/ai-settings', {
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
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!window.confirm('Reset all settings to defaults? This cannot be undone.')) return
    setSaving(true)
    setError(null)
    try {
      const res = await fetch('/api/ai-settings/reset', {
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

  const toggleRule = (key) => {
    setFormData(prev => ({
      ...prev,
      response_rules: {
        ...prev.response_rules,
        [key]: !prev.response_rules[key],
      },
    }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-brand-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Settings</h1>
          <p className="text-xs text-gray-500 mt-0.5">Customize your AI assistant's personality and behavior</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleReset}
            disabled={saving}
            className="btn-ghost flex items-center gap-2 text-xs"
          >
            <RotateCcw size={14} /> Reset
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary flex items-center gap-2 text-xs"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Save
          </button>
        </div>
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
                'px-2 py-1.5 rounded-lg text-xs font-semibold border-2 transition-all',
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

        {[
          { key: 'slider_formal', label: 'Formality', left: 'Casual', right: 'Formal' },
          { key: 'slider_length', label: 'Response Length', left: 'Brief', right: 'Detailed' },
          { key: 'slider_sales', label: 'Sales Focus', left: 'Neutral', right: 'Salesy' },
        ].map(({ key, label, left, right }) => (
          <div key={key} className="space-y-2">
            <div className="flex items-end justify-between">
              <label className="text-xs font-semibold text-gray-900">{label}</label>
              <span className="text-sm font-bold text-gray-900">{formData[key]}%</span>
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

      {/* System Prompt */}
      <div className="card p-5 space-y-2">
        <div>
          <h2 className="text-sm font-bold text-gray-900">System Prompt</h2>
          <p className="text-xs text-gray-500 mt-0.5">Base instructions sent to Claude before each response</p>
        </div>
        <textarea
          value={formData.system_prompt}
          onChange={e => setFormData(prev => ({ ...prev, system_prompt: e.target.value }))}
          rows={8}
          className="input w-full resize-none font-mono text-xs leading-relaxed"
          placeholder="Enter system prompt..."
        />
        <div className="flex justify-between text-xs text-gray-400">
          <span>{formData.system_prompt.length} characters</span>
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
    </div>
  )
}
