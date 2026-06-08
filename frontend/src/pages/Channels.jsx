import { useState, useEffect, useContext } from 'react'
import { Instagram, Smartphone, MessageCircle, CheckCircle, AlertTriangle, ExternalLink, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'

// Facebook icon component
const FacebookIcon = ({ size = 22, className = '' }) => (
  <span
    className={`inline-flex items-center justify-center font-black text-white rounded-lg ${className}`}
    style={{ width: size, height: size, fontSize: size * 0.65, background: '#1877F2', borderRadius: 6 }}
  >
    f
  </span>
)

// TikTok icon component
const TikTokIcon = ({ size = 22, className = '' }) => (
  <span
    className={`inline-flex items-center justify-center font-black text-white rounded-lg ${className}`}
    style={{ width: size, height: size, fontSize: size * 0.65, background: '#000000', borderRadius: 6 }}
  >
    ♪
  </span>
)

// Map channel keys to display names and icons
const channelConfig = {
  'instagram_dm': {
    name: 'Instagram DMs',
    Icon: ({ size }) => <Instagram size={size} className="text-pink-500" />,
    color: 'from-pink-50 to-pink-50',
    accent: 'pink',
  },
  'instagram_comment': {
    name: 'Instagram Comments',
    Icon: ({ size }) => <MessageCircle size={size} className="text-pink-500" />,
    color: 'from-pink-50 to-pink-50',
    accent: 'pink',
  },
  'whatsapp': {
    name: 'WhatsApp',
    Icon: ({ size }) => <Smartphone size={size} className="text-green-600" />,
    color: 'from-green-50 to-green-50',
    accent: 'green',
  },
  'facebook_dm': {
    name: 'Facebook Messenger',
    Icon: ({ size }) => <FacebookIcon size={size} />,
    color: 'from-blue-50 to-blue-50',
    accent: 'blue',
  },
  'facebook_comment': {
    name: 'Facebook Post Comments',
    Icon: ({ size }) => <FacebookIcon size={size} />,
    color: 'from-blue-50 to-blue-50',
    accent: 'blue',
  },
  'tiktok_dm': {
    name: 'TikTok DMs',
    Icon: ({ size }) => <TikTokIcon size={size} />,
    color: 'from-gray-50 to-gray-50',
    accent: 'gray',
  },
  'tiktok_comment': {
    name: 'TikTok Comments',
    Icon: ({ size }) => <TikTokIcon size={size} />,
    color: 'from-gray-50 to-gray-50',
    accent: 'gray',
  },
}

const getStatusColor = (connected, enabled) => {
  if (!connected) return 'text-red-600 bg-red-50 border-red-200'
  if (!enabled) return 'text-amber-600 bg-amber-50 border-amber-200'
  return 'text-green-600 bg-green-50 border-green-200'
}

const getStatusIcon = (connected) => {
  return connected ? <CheckCircle size={14} /> : <AlertTriangle size={14} />
}

const getStatusLabel = (connected, enabled) => {
  if (!connected) return 'Disconnected'
  if (!enabled) return 'Disabled'
  return 'Active'
}

// Channel Card Component
const ChannelCard = ({ ch, config, testingChannelId, testResults, onToggle, onTest }) => {
  const testResult = testResults[ch.id]
  const statusColor = getStatusColor(ch.connected, ch.enabled)

  return (
    <div className="group relative bg-white rounded-2xl border border-gray-200/50 overflow-hidden hover:border-gray-300 hover:shadow-xl transition-all duration-300">
      {/* Gradient top accent */}
      <div className={clsx('h-1.5 w-full', {
        'bg-gradient-to-r from-pink-500 to-pink-400': config.accent === 'pink',
        'bg-gradient-to-r from-green-500 to-green-400': config.accent === 'green',
        'bg-gradient-to-r from-blue-500 to-blue-400': config.accent === 'blue',
        'bg-gradient-to-r from-gray-400 to-gray-300': config.accent === 'gray',
      })} />

      <div className="p-4 space-y-3">
        {/* Header with icon and name */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br flex-shrink-0', {
              'from-pink-100 to-pink-50': config.accent === 'pink',
              'from-green-100 to-green-50': config.accent === 'green',
              'from-blue-100 to-blue-50': config.accent === 'blue',
              'from-gray-100 to-gray-50': config.accent === 'gray',
            })}>
              <config.Icon size={20} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-gray-900">{config.name}</h3>
              <p className="text-xs text-gray-400 mt-0.5">{ch.display_name}</p>
            </div>
          </div>
          
          {/* Status badge */}
          <div className={clsx('flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium flex-shrink-0', statusColor)}>
            {getStatusIcon(ch.connected)}
            <span className="hidden sm:inline">{getStatusLabel(ch.connected, ch.enabled)}</span>
          </div>
        </div>

        {/* Status details grid - more minimal */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-gradient-to-br from-gray-50 to-gray-30 rounded-lg px-2 py-1.5 border border-gray-100/50 text-xs">
            <p className="text-gray-500 font-medium text-[11px]">Account</p>
            <p className="text-gray-900 font-semibold text-xs">{ch.connected ? 'Connected' : 'Pending'}</p>
          </div>
          <div className="bg-gradient-to-br from-gray-50 to-gray-30 rounded-lg px-2 py-1.5 border border-gray-100/50 text-xs">
            <p className="text-gray-500 font-medium text-[11px]">Webhook</p>
            <p className="text-gray-900 font-semibold text-xs">{ch.connected ? 'Active' : 'Inactive'}</p>
          </div>
          <div className="bg-gradient-to-br from-gray-50 to-gray-30 rounded-lg px-2 py-1.5 border border-gray-100/50 text-xs">
            <p className="text-gray-500 font-medium text-[11px]">Messages</p>
            <p className="text-gray-900 font-semibold text-xs">{ch.message_count || 0}</p>
          </div>
          <div className="bg-gradient-to-br from-gray-50 to-gray-30 rounded-lg px-2 py-1.5 border border-gray-100/50 text-xs">
            <p className="text-gray-500 font-medium text-[11px]">Unread</p>
            <p className={clsx('font-semibold text-xs', ch.unread_count > 0 ? 'text-amber-600' : 'text-gray-900')}>
              {ch.unread_count || 0}
            </p>
          </div>
        </div>

        {/* Test result */}
        {testResult && (
          <div className={clsx(
            'text-xs px-2.5 py-1.5 rounded-lg border text-[11px]',
            testResult.ok
              ? 'bg-green-50/50 text-green-700 border-green-200/50'
              : 'bg-red-50/50 text-red-700 border-red-200/50'
          )}>
            {testResult.message}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-0.5">
          <button
            onClick={() => onTest(ch.id)}
            disabled={testingChannelId === ch.id}
            className="flex-1 flex items-center justify-center gap-1 px-2.5 py-1.5 bg-gray-50/50 hover:bg-gray-100 text-gray-700 text-xs font-medium rounded-lg border border-gray-200/50 transition-colors disabled:opacity-50 hover:border-gray-300"
            title="Test connection"
          >
            {testingChannelId === ch.id ? (
              <>
                <Loader2 size={11} className="animate-spin" />
                <span className="hidden sm:inline">Test</span>
              </>
            ) : (
              <>
                <ExternalLink size={11} />
                <span className="hidden sm:inline">Test</span>
              </>
            )}
          </button>
          <button
            onClick={() => onToggle(ch.id, ch.enabled)}
            className={clsx(
              'relative inline-flex w-11 h-6 rounded-full transition-colors duration-200 shrink-0',
              ch.enabled ? 'bg-black' : 'bg-gray-300'
            )}
            title={ch.enabled ? 'Disable channel' : 'Enable channel'}
          >
            <span
              className="absolute top-1 w-4 h-4 rounded-full bg-white shadow-sm transition-all duration-300"
              style={{ 
                left: ch.enabled ? 'calc(100% - 1.25rem)' : '0.25rem',
              }}
            />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Channels() {
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [publicBaseUrl, setPublicBaseUrl] = useState('')
  const [testingChannelId, setTestingChannelId] = useState(null)
  const [testResults, setTestResults] = useState({})
  const { confirm } = useContext(ConfirmationContext)

  // Fetch channels from backend
  useEffect(() => {
    const fetchChannels = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch('/api/channels', {
          headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
        })
        if (!res.ok) throw new Error('Failed to load channels')
        const data = await res.json()
        setChannels(data.channels || [])
        setPublicBaseUrl(data.public_base_url || '')
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    fetchChannels()
  }, [])

  const toggleChannel = async (id, currentEnabled) => {
    const confirmed = await confirm({
      title: currentEnabled ? 'Disable Channel?' : 'Enable Channel?',
      message: currentEnabled 
        ? 'This channel will stop receiving messages. You can re-enable it anytime.'
        : 'This channel will start receiving messages again.',
      confirmText: currentEnabled ? 'Disable' : 'Enable',
      cancelText: 'Cancel',
      isDangerous: currentEnabled,
    })

    if (!confirmed) return

    try {
      const res = await fetch(`/api/channels/${id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify({ enabled: !currentEnabled }),
      })
      if (!res.ok) throw new Error('Failed to toggle channel')
      const data = await res.json()
      setChannels(prev => prev.map(ch => ch.id === id ? data.channel : ch))
    } catch (err) {
      console.error('Toggle failed:', err)
    }
  }

  const testConnection = async (id) => {
    setTestingChannelId(id)
    try {
      const res = await fetch(`/api/channels/${id}/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error('Failed to test channel')
      const data = await res.json()
      setTestResults(prev => ({ ...prev, [id]: data }))
    } catch (err) {
      console.error('Test failed:', err)
      setTestResults(prev => ({ ...prev, [id]: { ok: false, message: err.message } }))
    } finally {
      setTestingChannelId(null)
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
  }

  if (loading) {
    return (
      <div className="space-y-6 w-full">
        <SkeletonHeader />
        <SkeletonList count={3} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-600">
        {error}
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full max-w-6xl mx-auto">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-gray-900">Channels</h1>
        <p className="text-sm text-gray-500">Manage your connected platforms and monitor real-time status</p>
      </div>

      {/* Channels grid - organized by platform */}
      <div className="space-y-8">
        {/* Instagram Row */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-1 h-6 bg-gradient-to-b from-pink-500 to-pink-400 rounded-full" />
            <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">Instagram</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {channels.filter(ch => ch.channel.startsWith('instagram')).map(ch => (
              <ChannelCard key={ch.id} ch={ch} config={channelConfig[ch.channel]} 
                testingChannelId={testingChannelId} testResults={testResults}
                onToggle={toggleChannel} onTest={testConnection} />
            ))}
          </div>
        </section>

        {/* Facebook Row */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-1 h-6 bg-gradient-to-b from-blue-500 to-blue-400 rounded-full" />
            <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">Facebook</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {channels.filter(ch => ch.channel.startsWith('facebook')).map(ch => (
              <ChannelCard key={ch.id} ch={ch} config={channelConfig[ch.channel]} 
                testingChannelId={testingChannelId} testResults={testResults}
                onToggle={toggleChannel} onTest={testConnection} />
            ))}
          </div>
        </section>

        {/* TikTok Row */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-1 h-6 bg-gradient-to-b from-gray-400 to-gray-300 rounded-full" />
            <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">TikTok</h2>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {channels.filter(ch => ch.channel.startsWith('tiktok')).map(ch => (
              <ChannelCard key={ch.id} ch={ch} config={channelConfig[ch.channel]} 
                testingChannelId={testingChannelId} testResults={testResults}
                onToggle={toggleChannel} onTest={testConnection} />
            ))}
          </div>
        </section>

        {/* WhatsApp - Full width */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-1 h-6 bg-gradient-to-b from-green-500 to-green-400 rounded-full" />
            <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">WhatsApp</h2>
          </div>
          <div className="grid grid-cols-1 gap-4">
            {channels.filter(ch => ch.channel === 'whatsapp').map(ch => (
              <ChannelCard key={ch.id} ch={ch} config={channelConfig[ch.channel]} 
                testingChannelId={testingChannelId} testResults={testResults}
                onToggle={toggleChannel} onTest={testConnection} />
            ))}
          </div>
        </section>
      </div>

      {/* Webhook URLs section */}
      {publicBaseUrl && (
        <section className="pt-2">
          <div className="border border-gray-200 rounded-lg p-5 space-y-4">
            <div>
              <h2 className="text-sm font-bold text-gray-900">Webhook URLs</h2>
              <p className="text-xs text-gray-500 mt-1">Register these in your respective Developer Consoles</p>
            </div>

            <div className="space-y-3">
              {channels.map(ch => (
                <div key={ch.id} className="flex items-start justify-between gap-4 pb-3 border-b border-gray-100 last:border-0 last:pb-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-500 font-medium mb-1.5">{channelConfig[ch.channel]?.name || ch.display_name}</p>
                    <p className="text-xs font-mono text-brand-600 break-all">{ch.webhook_url}</p>
                  </div>
                  <button
                    onClick={() => copyToClipboard(ch.webhook_url)}
                    className="text-xs font-semibold text-gray-600 hover:text-gray-900 whitespace-nowrap transition-colors flex-shrink-0 py-0.5"
                  >
                    Copy
                  </button>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
