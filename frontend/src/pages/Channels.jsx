import { useState, useEffect, useContext } from 'react'
import { Instagram, Smartphone, MessageCircle, CheckCircle, AlertTriangle, ExternalLink, Loader2, Copy, Check, Zap, ZapOff } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'
import { parseBackendTime } from '../utils/time'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

// ── Platform icons ──────────────────────────────────────────────────────────
const FacebookIcon = ({ size = 20 }) => (
  <span
    className="inline-flex items-center justify-center font-black text-white"
    style={{ width: size, height: size, fontSize: size * 0.6, background: '#1877F2', borderRadius: 6 }}
  >f</span>
)

const TikTokIcon = ({ size = 20 }) => (
  <span
    className="inline-flex items-center justify-center font-black text-white"
    style={{ width: size, height: size, fontSize: size * 0.6, background: '#000', borderRadius: 6 }}
  >♪</span>
)

// ── Channel config ──────────────────────────────────────────────────────────
const channelConfig = {
  instagram_dm: {
    name: 'Instagram DMs',
    description: 'Direct messages from Instagram',
    Icon: ({ size = 20 }) => <Instagram size={size} className="text-pink-500" />,
    accent: '#ec4899',
    accentLight: '#fdf2f8',
    platform: 'Instagram',
  },
  instagram_comment: {
    name: 'Instagram Comments',
    description: 'Post and reel comment replies',
    Icon: ({ size = 20 }) => <MessageCircle size={size} className="text-pink-500" />,
    accent: '#ec4899',
    accentLight: '#fdf2f8',
    platform: 'Instagram',
  },
  whatsapp: {
    name: 'WhatsApp',
    description: 'WhatsApp Business API messages',
    Icon: ({ size = 20 }) => <Smartphone size={size} className="text-green-500" />,
    accent: '#22c55e',
    accentLight: '#f0fdf4',
    platform: 'WhatsApp',
  },
  facebook_dm: {
    name: 'Facebook Messenger',
    description: 'Messenger inbox messages',
    Icon: ({ size = 20 }) => <FacebookIcon size={size} />,
    accent: '#3b82f6',
    accentLight: '#eff6ff',
    platform: 'Facebook',
  },
  facebook_comment: {
    name: 'Facebook Comments',
    description: 'Facebook post comment replies',
    Icon: ({ size = 20 }) => <FacebookIcon size={size} />,
    accent: '#3b82f6',
    accentLight: '#eff6ff',
    platform: 'Facebook',
  },
  tiktok_dm: {
    name: 'TikTok DMs',
    description: 'TikTok direct messages',
    Icon: ({ size = 20 }) => <TikTokIcon size={size} />,
    accent: '#000000',
    accentLight: '#f9fafb',
    platform: 'TikTok',
  },
  tiktok_comment: {
    name: 'TikTok Comments',
    description: 'TikTok video comment replies',
    Icon: ({ size = 20 }) => <TikTokIcon size={size} />,
    accent: '#000000',
    accentLight: '#f9fafb',
    platform: 'TikTok',
  },
}

// ── Platform groups ─────────────────────────────────────────────────────────
const platforms = [
  { key: 'Instagram', filter: ch => ch.channel.startsWith('instagram'), accent: '#ec4899' },
  { key: 'Facebook',  filter: ch => ch.channel.startsWith('facebook'),  accent: '#3b82f6' },
  { key: 'TikTok',    filter: ch => ch.channel.startsWith('tiktok'),    accent: '#000000' },
  { key: 'WhatsApp',  filter: ch => ch.channel === 'whatsapp',          accent: '#22c55e' },
]

// ── CopyButton ──────────────────────────────────────────────────────────────
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handle = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handle}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-gray-200 text-xs font-semibold text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all shrink-0"
    >
      {copied ? <Check size={11} className="text-green-600" /> : <Copy size={11} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

// ── ChannelRow ──────────────────────────────────────────────────────────────
function ChannelRow({ ch, config, testingChannelId, testResults, onToggle, onTest }) {
  const testResult = testResults[ch.id]
  const isActive = ch.connected && ch.enabled
  const isPending = ch.connected && !ch.enabled

  return (
    <div className="flex items-center gap-5 px-5 py-4 hover:bg-gray-50/60 transition-colors group">
      {/* Icon */}
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: config.accentLight }}
      >
        <config.Icon size={20} />
      </div>

      {/* Name + description */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">{config.name}</p>
        <p className="text-xs text-gray-400 mt-0.5">{config.description}</p>

        {/* Token expiry — persistent, from DB */}
        {(() => {
          if (!ch.token_expires_at && !ch.last_verified_at) return null
          if (!ch.token_expires_at) {
            // Verified but no expiry stored → long-lived token
            return (
              <p className="text-[11px] font-medium mt-1 text-gray-500">
                Token: no expiry (long-lived)
              </p>
            )
          }
          const expiresAt = parseBackendTime(ch.token_expires_at)
          const now = new Date()
          const daysLeft = Math.floor((expiresAt - now) / (1000 * 60 * 60 * 24))
          let cls = 'text-gray-500'
          let label = `Token expires in ${daysLeft} days`
          if (daysLeft < 0) {
            cls = 'text-red-600'
            label = 'Token expired'
          } else if (daysLeft < 7) {
            cls = 'text-red-600'
            label = `Token expires in ${daysLeft} days — renew soon`
          } else if (daysLeft < 14) {
            cls = 'text-amber-600'
            label = `Token expires in ${daysLeft} days`
          }
          return (
            <p className={clsx('text-[11px] font-medium mt-1', cls)}>
              {label}
            </p>
          )
        })()}

        {/* Live test result — transient, only after click */}
        {testResult && (
          <p className={clsx(
            'text-[11px] font-medium mt-1',
            testResult.ok ? 'text-green-600' : 'text-red-500'
          )}>
            {testResult.ok ? '✓' : '✗'} {testResult.message}
          </p>
        )}
      </div>

      {/* Stats */}
      <div className="hidden md:flex items-center gap-6 shrink-0">
        <div className="text-center">
          <p className="text-xs text-gray-400 font-medium">Messages</p>
          <p className="text-sm font-bold text-gray-900 tabular-nums">{ch.message_count || 0}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-400 font-medium">Unread</p>
          <p className={clsx(
            'text-sm font-bold tabular-nums',
            ch.unread_count > 0 ? 'text-amber-500' : 'text-gray-900'
          )}>{ch.unread_count || 0}</p>
        </div>
      </div>

      {/* Status badge */}
      <div className={clsx(
        'hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-semibold shrink-0',
        isActive  ? 'bg-green-50 text-green-700 border-green-200' :
        isPending ? 'bg-amber-50 text-amber-700 border-amber-200' :
                   'bg-red-50 text-red-600 border-red-200'
      )}>
        {isActive
          ? <><span className="ripple w-1.5 h-1.5 rounded-full bg-green-500 text-green-500 relative" /> Active</>
          : isPending
          ? <><span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Disabled</>
          : <><AlertTriangle size={11} /> Disconnected</>
        }
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={() => onTest(ch.id)}
          disabled={testingChannelId === ch.id}
          title="Test connection"
          className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 hover:text-gray-700 hover:border-gray-300 transition-all disabled:opacity-40"
        >
          {testingChannelId === ch.id
            ? <Loader2 size={13} className="animate-spin" />
            : <ExternalLink size={13} />
          }
        </button>

        {/* Toggle */}
        <button
          onClick={() => onToggle(ch.id, ch.enabled)}
          className={clsx(
            'relative inline-flex w-10 h-5 rounded-full transition-colors duration-200 shrink-0',
            ch.enabled ? 'bg-black' : 'bg-gray-200'
          )}
          title={ch.enabled ? 'Disable' : 'Enable'}
        >
          <span
            className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-all duration-300"
            style={{ left: ch.enabled ? 'calc(100% - 1.125rem)' : '0.125rem' }}
          />
        </button>
      </div>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────
export default function Channels() {
  const [channels, setChannels]           = useState([])
  const [loading, setLoading]             = useState(true)
  const [error, setError]                 = useState(null)
  const [publicBaseUrl, setPublicBaseUrl] = useState('')
  const [testingChannelId, setTestingChannelId] = useState(null)
  const [testResults, setTestResults]     = useState({})
  const { confirm } = useContext(ConfirmationContext)

  useEffect(() => {
    const fetchChannels = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${API_BASE}/channels`, {
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
      const res = await fetch(`${API_BASE}/channels/${id}`, {
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
      const res = await fetch(`${API_BASE}/channels/${id}/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('authToken')}`,
        },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error('Connection test failed')
      const data = await res.json()
      setTestResults(prev => ({ ...prev, [id]: data }))
    } catch (err) {
      setTestResults(prev => ({ ...prev, [id]: { ok: false, message: err.message } }))
    } finally {
      setTestingChannelId(null)
    }
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
      <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600">
        {error}
      </div>
    )
  }

  // Summary counts
  const activeCount = channels.filter(ch => ch.connected && ch.enabled).length
  const totalCount  = channels.length

  return (
    <div className="space-y-6 w-full max-w-7xl mx-auto">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Channels</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage connected platforms and monitor their real-time status</p>
        </div>
        {/* Summary pill */}
        <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-50 border border-gray-200 shrink-0">
          <span className="w-2 h-2 rounded-full bg-green-500" style={{ animation: 'pulse 2s cubic-bezier(0.4,0,0.6,1) infinite' }} />
          <span className="text-xs font-semibold text-gray-700">
            {activeCount} <span className="text-gray-400 font-normal">of</span> {totalCount} active
          </span>
        </div>
      </div>

      {/* ── Platform sections ────────────────────────────────────── */}
      <div className="space-y-5">
        {platforms.map(({ key, filter, accent }) => {
          const group = channels.filter(filter)
          if (group.length === 0) return null
          return (
            <div key={key} className="card overflow-hidden">
              {/* Section header */}
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100 bg-gray-50/50">
                <div className="flex items-center gap-2.5">
                  <span className="w-2 h-2 rounded-full" style={{ background: accent }} />
                  <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">{key}</h2>
                  <span className="text-xs text-gray-400 font-medium">
                    {group.filter(ch => ch.connected && ch.enabled).length}/{group.length} active
                  </span>
                </div>
              </div>

              {/* Channel rows */}
              <div className="divide-y divide-gray-100">
                {group.map(ch => {
                  const config = channelConfig[ch.channel]
                  if (!config) return null
                  return (
                    <ChannelRow
                      key={ch.id}
                      ch={ch}
                      config={config}
                      testingChannelId={testingChannelId}
                      testResults={testResults}
                      onToggle={toggleChannel}
                      onTest={testConnection}
                    />
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Webhook URLs ─────────────────────────────────────────── */}
      {publicBaseUrl && (
        <div className="card overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-gray-100 bg-gray-50/50">
            <span className="w-2 h-2 rounded-full bg-gray-400" />
            <h2 className="text-xs font-bold text-gray-600 uppercase tracking-wider">Webhook URLs</h2>
            <span className="text-xs text-gray-400 font-medium">Register these in your Developer Consoles</span>
          </div>
          <div className="divide-y divide-gray-100">
            {channels.map(ch => {
              const config = channelConfig[ch.channel]
              return (
                <div key={ch.id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-gray-50/60 transition-colors">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: config?.accentLight }}>
                    {config && <config.Icon size={16} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-gray-600 mb-0.5">{config?.name || ch.display_name}</p>
                    <p className="text-xs font-mono text-brand-600 truncate">{ch.webhook_url}</p>
                  </div>
                  <CopyButton text={ch.webhook_url} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
