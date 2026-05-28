import { useState } from 'react'
import { Save, Bot } from 'lucide-react'

const tones = ['Luxury', 'Friendly', 'Gen Z', 'Minimalist', 'Bold & Sales-Driven']

const toggleRules = [
  { id: 'no_invent_stock',  label: 'Never invent stock levels',                  default: true  },
  { id: 'shopify_first',    label: 'Always check Shopify first for stock',        default: true  },
  { id: 'include_price',    label: 'Include price in product replies',            default: true  },
  { id: 'hide_errors',      label: "Don't mention system errors to customers",    default: true  },
  { id: 'use_emojis',       label: 'Use emojis in replies',                       default: true  },
  { id: 'suggest_similar',  label: 'Suggest similar products when out of stock',  default: true  },
  { id: 'ask_order_number', label: 'Always ask for order number on order queries',default: true  },
  { id: 'notify_oos',       label: 'Offer restock notification for OOS items',    default: false },
]

export default function AISettings() {
  const [selectedTone, setSelectedTone] = useState('Friendly')
  const [formalSlider, setFormalSlider] = useState(40)
  const [lengthSlider, setLengthSlider] = useState(50)
  const [salesSlider, setSalesSlider]   = useState(60)
  const [toggles, setToggles] = useState(
    Object.fromEntries(toggleRules.map(r => [r.id, r.default]))
  )
  const [systemPrompt, setSystemPrompt] = useState(
`You are a friendly, professional customer support agent for a fashion & beauty brand based in Nairobi, Kenya.

You help customers with product inquiries, pricing, stock availability, and order status.

Rules:
- Always check Shopify for stock levels before confirming availability
- Never guess or invent stock quantities
- Keep replies concise (2–4 sentences)
- Be warm, on-brand, and helpful
- If you don't know something, say so honestly and offer to find out`
  )

  const toggle = (id) => setToggles(prev => ({ ...prev, [id]: !prev[id] }))

  return (
    <div className="space-y-6 w-full max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Settings</h1>
          <p className="text-sm text-gray-500 mt-0.5">Define your brand voice and AI behaviour</p>
        </div>
        <button className="btn-primary flex items-center gap-2">
          <Save size={14} /> Save Changes
        </button>
      </div>

      {/* Brand tone */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-brand-500" />
          <h2 className="text-sm font-bold text-gray-900">Brand Tone</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {tones.map(tone => (
            <button
              key={tone}
              onClick={() => setSelectedTone(tone)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold border transition-colors ${
                selectedTone === tone
                  ? 'bg-brand-500 border-brand-500 text-white shadow-sm'
                  : 'border-gray-200 text-gray-600 hover:border-brand-300 hover:text-brand-600'
              }`}
            >
              {tone}
            </button>
          ))}
        </div>
      </div>

      {/* Personality sliders */}
      <div className="card p-5 space-y-5">
        <h2 className="text-sm font-bold text-gray-900">Personality Sliders</h2>
        {[
          { label: 'Tone',   leftLabel: 'Formal',       rightLabel: 'Casual',          value: formalSlider, set: setFormalSlider },
          { label: 'Length', leftLabel: 'Short replies', rightLabel: 'Detailed replies', value: lengthSlider, set: setLengthSlider },
          { label: 'Sales',  leftLabel: 'Neutral',       rightLabel: 'Salesy',           value: salesSlider,  set: setSalesSlider  },
        ].map(({ label, leftLabel, rightLabel, value, set }) => (
          <div key={label}>
            <div className="flex justify-between text-xs font-semibold text-gray-400 mb-2">
              <span>{leftLabel}</span>
              <span className="text-brand-500">{label}</span>
              <span>{rightLabel}</span>
            </div>
            <input
              type="range" min="0" max="100" value={value}
              onChange={e => set(Number(e.target.value))}
              className="w-full h-2 rounded-full appearance-none bg-gray-200 accent-brand-500 cursor-pointer"
            />
          </div>
        ))}
      </div>

      {/* System prompt */}
      <div className="card p-5 space-y-3">
        <div>
          <h2 className="text-sm font-bold text-gray-900">System Prompt</h2>
          <p className="text-xs text-gray-500 mt-0.5">Sent to the AI before every conversation</p>
        </div>
        <textarea
          value={systemPrompt}
          onChange={e => setSystemPrompt(e.target.value)}
          rows={8}
          className="input w-full resize-none font-mono text-xs leading-relaxed"
        />
        <p className="text-xs text-gray-400">{systemPrompt.length} characters</p>
      </div>

      {/* Response rules */}
      <div className="card p-5 space-y-4">
        <h2 className="text-sm font-bold text-gray-900">Response Rules</h2>
        <div className="space-y-3">
          {toggleRules.map(rule => (
            <div key={rule.id} className="flex items-center justify-between gap-3 py-1">
              <span className="text-sm text-gray-700 font-medium leading-snug">{rule.label}</span>
              <button
                onClick={() => toggle(rule.id)}
                className={`relative inline-flex w-11 h-6 rounded-full transition-colors duration-200 ${
                  toggles[rule.id] ? 'bg-brand-500' : 'bg-gray-300'
                }`}
              >
                <span
                  className="absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-all duration-200"
                  style={{ transform: toggles[rule.id] ? 'translateX(20px)' : 'translateX(0px)' }}
                />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
