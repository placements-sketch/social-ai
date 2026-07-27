import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import clsx from 'clsx'
import { Settings as SettingsIcon, Radio } from 'lucide-react'
import Settings from './Settings'
import Channels from './Channels'

const TABS = [
  { key: 'settings', label: 'General',  Icon: SettingsIcon, Comp: Settings },
  { key: 'channels', label: 'Channels', Icon: Radio,        Comp: Channels },
]

export default function SettingsAndChannels() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('tab') === 'channels' ? 'channels' : 'settings'
  const [tab, setTab] = useState(initial)

  const select = (key) => {
    setTab(key)
    setParams(key === 'settings' ? {} : { tab: key }, { replace: true })
  }

  const Active = TABS.find(t => t.key === tab).Comp

  return (
    <div className="space-y-5 w-full">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">Organisation configuration and connected channels.</p>
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