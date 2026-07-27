import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Bot, Zap } from 'lucide-react'
import AISettings from './AISettings'
import Automation from './Automation'

const TABS = [
  { key: 'settings',   label: 'AI Settings',      Icon: Bot, Comp: AISettings },
  { key: 'automation', label: 'Automation Rules', Icon: Zap, Comp: Automation },
]

export default function AIAndAutomation() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('tab') === 'automation' ? 'automation' : 'settings'
  const [tab, setTab] = useState(initial)

  const select = (key) => {
    setTab(key)
    setParams(key === 'settings' ? {} : { tab: key }, { replace: true })
  }

  const Active = TABS.find(t => t.key === tab).Comp

  return (
    <div className="space-y-5 w-full max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI &amp; Automation</h1>
        <p className="text-sm text-gray-500 mt-0.5">Your assistant's behaviour and automated response rules.</p>
      </div>

      <div className="flex items-center gap-1 border-b border-gray-200">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => select(key)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === key ? 'border-brand-600 text-gray-900' : 'border-transparent text-gray-500 hover:text-gray-800'
            )}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <div><Active embedded /></div>
    </div>
  )
}