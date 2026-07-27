import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Bell, ScrollText } from 'lucide-react'
import Notifications from './Notifications'
import Logs from './Logs'

const TABS = [
  { key: 'notifications', label: 'Notifications', Icon: Bell,       Comp: Notifications },
  { key: 'logs',          label: 'System Logs',   Icon: ScrollText, Comp: Logs },
]

export default function Activity() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('tab') === 'logs' ? 'logs' : 'notifications'
  const [tab, setTab] = useState(initial)

  const select = (key) => {
    setTab(key)
    setParams(key === 'notifications' ? {} : { tab: key }, { replace: true })
  }

  const Active = TABS.find(t => t.key === tab).Comp

  return (
    <div className="space-y-5 w-full max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Activity</h1>
        <p className="text-sm text-gray-500 mt-0.5">Notifications and system event logs.</p>
      </div>

      <div className="flex items-center gap-1 border-b border-gray-200">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => select(key)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === key
                ? 'border-brand-600 text-gray-900'
                : 'border-transparent text-gray-500 hover:text-gray-800'
            )}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <div>
        <Active embedded />
      </div>
    </div>
  )
}