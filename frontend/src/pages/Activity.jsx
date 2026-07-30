import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Bell, ScrollText } from 'lucide-react'
import Notifications from './Notifications'
import Logs from './Logs'
import { useAuth } from '../context/AuthContext'

// System Logs is admin-only. Raw pipeline logs are engineering output — an
// agent or supervisor can act on none of it, and it leaks internals (database
// hostnames, IPs, stack traces). Anything they DO need reaches them as a
// notification instead.
const ALL_TABS = [
  { key: 'notifications', label: 'Notifications', Icon: Bell,       Comp: Notifications, roles: ['admin', 'supervisor', 'agent'] },
  { key: 'logs',          label: 'System Logs',   Icon: ScrollText, Comp: Logs,          roles: ['admin'] },
]

export default function Activity() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const TABS = ALL_TABS.filter(t => t.roles.includes(user?.role))
  const wanted = params.get('tab') === 'logs' ? 'logs' : 'notifications'
  // A non-admin landing on ?tab=logs (an old link, a bookmark) falls back to
  // notifications rather than hitting a tab that isn't there.
  const initial = TABS.some(t => t.key === wanted) ? wanted : 'notifications'
  const [tab, setTab] = useState(initial)

  const select = (key) => {
    setTab(key)
    setParams(key === 'notifications' ? {} : { tab: key }, { replace: true })
  }

  const Active = (TABS.find(t => t.key === tab) || TABS[0]).Comp

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
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b -mb-px transition-colors',
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