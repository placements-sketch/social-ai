import { Instagram, Smartphone, MessageCircle, CheckCircle, AlertTriangle, ExternalLink } from 'lucide-react'
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

const channels = [
  {
    id: 'instagram_dm',
    name: 'Instagram DMs',
    Icon: ({ size }) => <Instagram size={size} className="text-pink-500" />,
    iconBg: 'bg-pink-50',
    status: 'connected',
    description: 'Receives and replies to direct messages on Instagram.',
    details: [
      { label: 'Account',            value: '@yourbrand',          ok: true  },
      { label: 'Webhook status',     value: 'Active',              ok: true  },
      { label: 'Message permission', value: 'Granted',             ok: true  },
      { label: 'Page access token',  value: 'Valid (expires 47d)', ok: true  },
    ],
  },
  {
    id: 'instagram_comments',
    name: 'Instagram Comments',
    Icon: ({ size }) => <MessageCircle size={size} className="text-pink-500" />,
    iconBg: 'bg-pink-50',
    status: 'connected',
    description: 'Monitors post comments and triggers DM flows automatically.',
    details: [
      { label: 'Auto-reply on comments', value: 'Enabled',  ok: true  },
      { label: 'DM trigger on price?',   value: 'Enabled',  ok: true  },
      { label: 'Comment webhook',        value: 'Active',   ok: true  },
      { label: 'Moderation filter',      value: 'Disabled', ok: false },
    ],
  },
  {
    id: 'whatsapp',
    name: 'WhatsApp',
    Icon: ({ size }) => <Smartphone size={size} className="text-green-600" />,
    iconBg: 'bg-green-50',
    status: 'warning',
    description: 'Sends and receives messages via Meta WhatsApp Cloud API.',
    details: [
      { label: 'Phone number',          value: '+254 700 000 000', ok: true  },
      { label: 'API status',            value: 'Active',           ok: true  },
      { label: 'Template approval',     value: '2 pending',        ok: false },
      { label: 'Webhook response time', value: 'Elevated (3.2s)',  ok: false },
    ],
  },
  {
    id: 'facebook_messenger',
    name: 'Facebook Messenger',
    Icon: ({ size }) => <FacebookIcon size={size} />,
    iconBg: 'bg-blue-50',
    status: 'connected',
    description: 'Receives and replies to Facebook Messenger DMs via Meta Graph API.',
    details: [
      { label: 'Facebook Page',      value: 'Your Brand Page',     ok: true  },
      { label: 'Webhook status',     value: 'Active',              ok: true  },
      { label: 'Message permission', value: 'Granted',             ok: true  },
      { label: 'Page access token',  value: 'Valid (expires 47d)', ok: true  },
    ],
  },
  {
    id: 'facebook_comments',
    name: 'Facebook Post Comments',
    Icon: ({ size }) => <FacebookIcon size={size} />,
    iconBg: 'bg-blue-50',
    status: 'connected',
    description: 'Monitors Facebook post comments and triggers Messenger DM flows.',
    details: [
      { label: 'Auto-reply on comments', value: 'Enabled', ok: true  },
      { label: 'DM trigger on price?',   value: 'Enabled', ok: true  },
      { label: 'Comment webhook',        value: 'Active',  ok: true  },
      { label: 'Moderation filter',      value: 'Enabled', ok: true  },
    ],
  },
  {
    id: 'tiktok_dm',
    name: 'TikTok DMs',
    Icon: ({ size }) => <TikTokIcon size={size} />,
    iconBg: 'bg-gray-100',
    status: 'connected',
    description: 'Receives and replies to TikTok direct messages.',
    details: [
      { label: 'TikTok Account',     value: '@yourbrand',        ok: true  },
      { label: 'Webhook status',     value: 'Active',            ok: true  },
      { label: 'DM permission',      value: 'Granted',           ok: true  },
      { label: 'Client key',         value: 'Valid',             ok: true  },
    ],
  },
  {
    id: 'tiktok_comments',
    name: 'TikTok Comments',
    Icon: ({ size }) => <TikTokIcon size={size} />,
    iconBg: 'bg-gray-100',
    status: 'connected',
    description: 'Monitors TikTok video comments and triggers DM flows.',
    details: [
      { label: 'Auto-reply on comments', value: 'Enabled', ok: true  },
      { label: 'DM trigger on price?',   value: 'Enabled', ok: true  },
      { label: 'Comment webhook',        value: 'Active',  ok: true  },
      { label: 'Moderation filter',      value: 'Enabled', ok: true  },
    ],
  },
]

const statusBadge = (s) => {
  if (s === 'connected') return <span className="badge bg-green-50 text-green-600 border border-green-200"><CheckCircle size={10} /> Connected</span>
  if (s === 'warning')   return <span className="badge bg-amber-50 text-amber-600 border border-amber-200"><AlertTriangle size={10} /> Warning</span>
  if (s === 'error')     return <span className="badge bg-red-50 text-red-600 border border-red-200"><AlertTriangle size={10} /> Error</span>
}

export default function Channels() {
  return (
    <div className="space-y-6 w-full max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Channels</h1>
        <p className="text-sm text-gray-500 mt-0.5">Connected platforms and webhook status</p>
      </div>

      <div className="space-y-4">
        {channels.map(ch => (
          <div key={ch.id} className="card p-5">
            <div className="flex items-start justify-between mb-4 gap-2">
              <div className="flex items-center gap-3 min-w-0">
                <div className={clsx('w-11 h-11 rounded-xl flex items-center justify-center shrink-0', ch.iconBg)}>
                  <ch.Icon size={22} />
                </div>
                <div className="min-w-0">
                  <h2 className="text-sm font-bold text-gray-900">{ch.name}</h2>
                  <p className="text-xs text-gray-500 mt-0.5 leading-snug">{ch.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {statusBadge(ch.status)}
                <button className="btn-ghost p-1.5" title="Open in Meta Developer Console">
                  <ExternalLink size={13} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {ch.details.map(d => (
                <div key={d.label} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
                  <span className="text-xs text-gray-500 font-medium">{d.label}</span>
                  <div className="flex items-center gap-1.5">
                    {d.ok
                      ? <CheckCircle size={11} className="text-green-500" />
                      : <AlertTriangle size={11} className="text-amber-500" />
                    }
                    <span className={clsx('text-xs font-semibold', d.ok ? 'text-gray-700' : 'text-amber-600')}>
                      {d.value}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Webhook URLs */}
      <div className="card p-5 space-y-3">
        <h2 className="text-sm font-bold text-gray-900">Webhook URLs</h2>
        <p className="text-xs text-gray-500">Register these in your respective Developer Consoles</p>
        {[
          { label: 'Instagram DMs & Comments',          url: 'https://yourdomain.com/webhook/instagram'         },
          { label: 'WhatsApp',                          url: 'https://yourdomain.com/webhook/whatsapp'          },
          { label: 'Facebook Messenger',                url: 'https://yourdomain.com/webhook/facebook'          },
          { label: 'Facebook Post Comments',            url: 'https://yourdomain.com/webhook/facebook/comments' },
          { label: 'TikTok DMs & Comments',             url: 'https://yourdomain.com/webhook/tiktok'            },
        ].map(w => (
          <div key={w.label} className="flex items-center justify-between bg-gray-50 border border-gray-100 rounded-lg px-3 py-2.5">
            <div>
              <p className="text-xs text-gray-500 font-medium">{w.label}</p>
              <p className="text-xs font-mono text-brand-600 mt-0.5 font-semibold">{w.url}</p>
            </div>
            <button className="btn-ghost text-xs px-2 py-1">Copy</button>
          </div>
        ))}
      </div>
    </div>
  )
}
