import { useState } from 'react'
import { automationRules } from '../data/mock'
import { Zap, Plus, Pencil, Trash2 } from 'lucide-react'
import clsx from 'clsx'

export default function Automation() {
  const [rules, setRules] = useState(automationRules)

  const toggleRule = (id) => {
    setRules(prev => prev.map(r => r.id === id ? { ...r, enabled: !r.enabled } : r))
  }

  return (
    <div className="space-y-6 w-full max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Automation Rules</h1>
          <p className="text-sm text-gray-500 mt-0.5">Define how the AI handles specific scenarios</p>
        </div>
        <button className="btn-primary flex items-center gap-2">
          <Plus size={14} /> New Rule
        </button>
      </div>

      <div className="space-y-3">
        {rules.map((rule, i) => (
          <div
            key={rule.id}
            className={clsx(
              'card p-4 transition-all',
              !rule.enabled && 'opacity-50'
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <div className={clsx(
                  'w-8 h-8 rounded-xl flex items-center justify-center text-sm font-bold shrink-0 mt-0.5',
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
                <button className="btn-ghost p-1.5 hover:text-red-500" title="Delete"><Trash2 size={13} /></button>
                <button
                  onClick={() => toggleRule(rule.id)}
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

      <div className="bg-brand-50 border border-brand-100 rounded-xl p-4">
        <p className="text-xs text-brand-700 leading-relaxed font-medium">
          <strong>Rules run in order</strong> — the first matching rule wins.
          Disabled rules are skipped entirely.
          Rules are evaluated after intent detection and before the AI generates a reply.
        </p>
      </div>
    </div>
  )
}
