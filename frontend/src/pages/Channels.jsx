import { useState, useEffect } from 'react'
import { Instagram, Smartphone, MessageCircle, CheckCircle, AlertTriangle, ExternalLink, Loader2 } from 'lucide-react'
import clsx from 'clsx'

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
    iconBg: 'bg-pink-50',
    accountLabel: 'Instagram Account',
    accountValue: '@yourbrand',
  },
  'instagram_comment': {
    name: 'Instagram Comments',
    Icon: ({ size }) => <MessageCircle size={size} className="text-pink-500" />,
    iconBg: 'bg-pink-50',
    accountLabel: 'Instagram Account',
    accountValue: '@yourbrand',
  },
  'whatsapp': {
    name: 'WhatsApp',
    Icon: ({ size }) => <Smartphone size={size} className="text-green-600" />,
    iconBg: 'bg-green-50',
    accountLabel: 'Phone number',
    accountValue: '+254 700 000 000',
  },
  'facebook_dm': {
    name: 'Facebook Messenger',
    Icon: ({ size }) => <FacebookIcon size={size} />,
    iconBg: 'bg-blue-50',
    accountLabel: 'Facebook Page',
    accountValue: '@your brand page',
  },
  'facebook_comment': {
    name: 'Facebook Post Comments',
    Icon: ({ size }) => <FacebookIcon size={size} />,
    iconBg: 'bg-blue-50',
    accountLabel: 'Facebook Page',
    accountValue: '@your brand page',
  },
  'tiktok_dm': {
    name: 'TikTok DMs',
    Icon: ({ size }) => <TikTokIcon size={size} />,
    iconBg: 'bg-gray-100',
    accountLabel: 'TikTok Account',
    accountValue: '@yourbrand',
  },
  'tiktok_comment': {
    name: 'TikTok Comments',
    Icon: ({ size }) => <TikTokIcon size={size} />,
    iconBg: 'bg-gray-100',
    accountLabel: 'TikTok Account',
    accountValue: '@yourbrand',
  },
}

const statusBadge = (connected, enabled) => {
  if (!connected) return <span className="badge bg-red-50 text-red-600 border border-red-200"><AlertTriangle size={10} /> Disconnected</span>
  if (!enabled) return <span className="badge bg-amber-50 text-amber-600 border border-amber-200"><AlertTriangle size={10} /> Disabled</span>
  return <span className="badge bg-green-50 text-green-600 border border-green-200"><CheckCircle size={10} /> Connected</span>
}

export default function Channels() {
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [publicBaseUrl, setPublicBaseUrl] = useState('')
  const [testingChannelId, setTestingChannelId] = useState(null)
  const [testResults, setTestResults] = useState({})

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
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-brand-500" />
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
    <div className="space-y-4 sm:space-y-6 w-full px-0">
      <div className="px-0">
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Channels</h1>
        <p className="text-xs sm:text-sm text-gray-500 mt-0.5">Connected platforms and webhook status</p>
      </div>

      <div className="space-y-3 sm:space-y-4">
        {channels.map(ch => {
          const config = channelConfig[ch.channel] || { name: ch.display_name, Icon: MessageCircle, iconBg: 'bg-gray-50' }
          const testResult = testResults[ch.id]
          return (
            <div key={ch.id} className="card p-3 sm:p-5">
              <div className="flex flex-col sm:flex-row items-start justify-between gap-3 sm:gap-2 mb-3 sm:mb-4">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0 w-full sm:w-auto">
                  <div className={clsx('w-9 sm:w-11 h-9 sm:h-11 rounded-xl flex items-center justify-center shrink-0', config.iconBg)}>
                    <config.Icon size={18} />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-xs sm:text-sm font-bold text-gray-900">{config.name}</h2>
                    <p className="text-xs text-gray-500 mt-0.5 leading-snug">{ch.display_name}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0 w-full sm:w-auto justify-between sm:justify-end">
                  <div className="hidden sm:flex">
                    {statusBadge(ch.connected, ch.enabled)}
                  </div>
                  <button
                    onClick={() => testConnection(ch.id)}
                    disabled={testingChannelId === ch.id}
                    className="btn-ghost p-1.5 hover:text-brand-600 text-xs sm:text-sm"
                    title="Test connection"
                  >
                    {testingChannelId === ch.id ? <Loader2 size={13} className="animate-spin" /> : <ExternalLink size={13} />}
                  </button>
                  <button
                    onClick={() => toggleChannel(ch.id, ch.enabled)}
                    className={clsx(
                      'relative inline-flex w-10 sm:w-11 h-5 sm:h-6 rounded-full transition-colors duration-200 shrink-0',
                      ch.enabled ? 'bg-brand-500' : 'bg-gray-300'
                    )}
                    title={ch.enabled ? 'Disable channel' : 'Enable channel'}
                  >
                    <span
                      className="absolute top-0.5 sm:top-1 left-0.5 sm:left-1 w-4 h-4 rounded-full bg-white shadow transition-all duration-200"
                      style={{ transform: ch.enabled ? 'translateX(18px)' : 'translateX(0px)' }}
                    />
                  </button>
                </div>
              </div>

              {/* Mobile status badge */}
              <div className="flex sm:hidden mb-3 w-full">
                {statusBadge(ch.connected, ch.enabled)}
              </div>

              {/* Status details - responsive grid */}
              <div className="space-y-1.5 sm:space-y-2 mb-3">
                {/* Row 1 */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                    <span className="text-xs text-gray-500 font-medium">{config.accountLabel}</span>
                    <div className="flex items-center gap-1 mt-1 sm:mt-0">
                      {ch.connected
                        ? <CheckCircle size={11} className="text-green-500 shrink-0" />
                        : <AlertTriangle size={11} className="text-amber-500 shrink-0" />
                      }
                      <span className={clsx('text-xs font-semibold truncate', ch.connected ? 'text-green-600' : 'text-amber-600')}>
                        {ch.connected ? config.accountValue : 'Not connected'}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                    <span className="text-xs text-gray-500 font-medium">Webhook status</span>
                    <div className="flex items-center gap-1 mt-1 sm:mt-0">
                      {ch.connected
                        ? <CheckCircle size={11} className="text-green-500 shrink-0" />
                        : <AlertTriangle size={11} className="text-amber-500 shrink-0" />
                      }
                      <span className={clsx('text-xs font-semibold', ch.connected ? 'text-green-600' : 'text-amber-600')}>
                        {ch.connected ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Row 2 */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                    <span className="text-xs text-gray-500 font-medium">Message permission</span>
                    <div className="flex items-center gap-1 mt-1 sm:mt-0">
                      {ch.connected
                        ? <CheckCircle size={11} className="text-green-500 shrink-0" />
                        : <AlertTriangle size={11} className="text-amber-500 shrink-0" />
                      }
                      <span className={clsx('text-xs font-semibold', ch.connected ? 'text-green-600' : 'text-amber-600')}>
                        {ch.connected ? 'Granted' : 'Pending'}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                    <span className="text-xs text-gray-500 font-medium">Page access token</span>
                    <div className="flex items-center gap-1 mt-1 sm:mt-0">
                      {ch.credentials_set
                        ? <CheckCircle size={11} className="text-green-500 shrink-0" />
                        : <AlertTriangle size={11} className="text-red-500 shrink-0" />
                      }
                      <span className={clsx('text-xs font-semibold', ch.credentials_set ? 'text-green-600' : 'text-red-600')}>
                        {ch.credentials_set ? 'Valid (expires 47d)' : 'Invalid'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* WhatsApp Phone Number */}
                {ch.channel === 'whatsapp' && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                      <span className="text-xs text-gray-500 font-medium">Phone number</span>
                      <div className="flex items-center gap-1 mt-1 sm:mt-0">
                        {ch.connected
                          ? <CheckCircle size={11} className="text-green-500 shrink-0" />
                          : <AlertTriangle size={11} className="text-amber-500 shrink-0" />
                        }
                        <span className={clsx('text-xs font-semibold truncate', ch.connected ? 'text-green-600' : 'text-amber-600')}>
                          {ch.connected ? config.accountValue : 'Not configured'}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                      <span className="text-xs text-gray-500 font-medium">API status</span>
                      <div className="flex items-center gap-1 mt-1 sm:mt-0">
                        {ch.connected
                          ? <CheckCircle size={11} className="text-green-500 shrink-0" />
                          : <AlertTriangle size={11} className="text-amber-500 shrink-0" />
                        }
                        <span className={clsx('text-xs font-semibold', ch.connected ? 'text-green-600' : 'text-amber-600')}>
                          {ch.connected ? 'Active' : 'Inactive'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Additional rows if data exists */}
                {ch.last_verified_at && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                      <span className="text-xs text-gray-500 font-medium">Last verified</span>
                      <span className="text-xs font-semibold text-green-600 mt-1 sm:mt-0">
                        {new Date(ch.last_verified_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                )}

                {ch.message_count !== undefined && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                      <span className="text-xs text-gray-500 font-medium">Messages</span>
                      <span className="text-xs font-semibold text-green-600 mt-1 sm:mt-0">{ch.message_count}</span>
                    </div>
                    {ch.unread_count !== undefined && (
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                        <span className="text-xs text-gray-500 font-medium">Unread</span>
                        <span className="text-xs font-semibold text-amber-600 mt-1 sm:mt-0">{ch.unread_count}</span>
                      </div>
                    )}
                  </div>
                )}

                {ch.last_message_at && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 rounded-lg px-2.5 sm:px-3 py-1.5 sm:py-2 border border-gray-100">
                      <span className="text-xs text-gray-500 font-medium">Last message</span>
                      <span className="text-xs font-semibold text-green-600 mt-1 sm:mt-0">
                        {new Date(ch.last_message_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Test result */}
              {testResult && (
                <div className={clsx(
                  'text-xs p-2 rounded-lg border',
                  testResult.ok
                    ? 'bg-green-50 border-green-200 text-green-700'
                    : 'bg-red-50 border-red-200 text-red-700'
                )}>
                  {testResult.message}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Webhook URLs */}
      {publicBaseUrl && (
        <div className="card p-3 sm:p-5 space-y-3">
          <h2 className="text-sm sm:text-base font-bold text-gray-900">Webhook URLs</h2>
          <p className="text-xs text-gray-500">Register these in your respective Developer Consoles</p>
          {channels.map(ch => (
            <div key={ch.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between bg-gray-50 border border-gray-100 rounded-lg px-2.5 sm:px-3 py-2 sm:py-2.5 gap-2 sm:gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-gray-500 font-medium">{channelConfig[ch.channel]?.name || ch.display_name}</p>
                <p className="text-xs font-mono text-brand-600 mt-1 sm:mt-0.5 font-semibold break-all sm:break-normal">{ch.webhook_url}</p>
              </div>
              <button
                onClick={() => copyToClipboard(ch.webhook_url)}
                className="btn-ghost text-xs px-2 py-1.5 sm:py-1 w-full sm:w-auto shrink-0"
              >
                Copy
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
