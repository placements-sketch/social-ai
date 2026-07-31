import { useState, useEffect, useCallback } from 'react'
import {
  Instagram, Plus, RefreshCw, Unlink, CheckCircle2,
  AlertTriangle, XCircle, Loader2,
} from 'lucide-react'
import clsx from 'clsx'
import { useToast } from './Toast'
import {
  listConnections, startInstagramConnect, refreshConnection, disconnectConnection,
} from '../api/connections'

// Token health, surfaced plainly. Instagram Login tokens last 60 days and can
// only be refreshed while still valid — once expired the only fix is
// reconnecting by hand, so "expiring" has to be visible before it bites.
const STATUS = {
  ok:           { label: 'Connected',   Icon: CheckCircle2,  cls: 'text-green-600 bg-green-50' },
  expiring:     { label: 'Expiring',    Icon: AlertTriangle, cls: 'text-amber-600 bg-amber-50' },
  expired:      { label: 'Expired',     Icon: XCircle,       cls: 'text-red-600 bg-red-50' },
  disconnected: { label: 'Disconnected',Icon: XCircle,       cls: 'text-gray-500 bg-gray-100' },
}

const SURFACE = {
  instagram_login: 'Instagram Login',
  facebook_login:  'Facebook Login',
  unknown:         'No credentials',
}

export default function InstagramConnections() {
  const [conns, setConns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [connecting, setConnecting] = useState(false)
  const { showToast } = useToast()

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await listConnections()
      setConns(data.connections || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // The OAuth callback redirects back with ?connected=1 — report the outcome
  // and clean the query so a refresh doesn't re-toast.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    if (!p.has('connected')) return
    if (p.get('connected') === '1') {
      const acct = p.get('account')
      showToast(
        p.get('subscribed') === '1'
          ? `Connected @${acct} — webhooks subscribed.`
          : `Connected @${acct}, but webhook subscription failed. Messages won't arrive until that succeeds.`,
        p.get('subscribed') === '1' ? 'success' : 'warning'
      )
    } else {
      showToast(p.get('error') || 'Connection cancelled.', 'error')
    }
    window.history.replaceState({}, '', window.location.pathname)
    load()
  }, [load, showToast])

  const handleConnect = async () => {
    setConnecting(true)
    try {
      const { oauth_url } = await startInstagramConnect(window.location.pathname)
      window.location.href = oauth_url
    } catch (e) {
      showToast(e.message, 'error')
      setConnecting(false)
    }
  }

  const handleRefresh = async (c) => {
    setBusyId(c.id)
    try {
      await refreshConnection(c.id)
      showToast(`Token refreshed for @${c.ig_username || c.ig_login_user_id}.`, 'success')
      load()
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setBusyId(null)
    }
  }

  const handleDisconnect = async (c) => {
    setBusyId(c.id)
    try {
      await disconnectConnection(c.id)
      showToast(`Disconnected @${c.ig_username || c.ig_login_user_id}.`, 'success')
      load()
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <h2 className="text-sm font-bold text-gray-900">Connected accounts</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Each account replies with its own credentials. Add as many as you need.
          </p>
        </div>
        <button
          onClick={handleConnect}
          disabled={connecting}
          className="btn-primary inline-flex items-center gap-1.5 shrink-0 disabled:opacity-60"
        >
          {connecting
            ? <Loader2 size={14} className="animate-spin" />
            : <Plus size={14} />}
          Connect Instagram
        </button>
      </div>

      {loading && (
        <p className="text-xs text-gray-400 py-6 text-center">Loading connections…</p>
      )}

      {error && !loading && (
        <div className="py-4 text-center">
          <p className="text-xs text-red-500 mb-2">{error}</p>
          <button onClick={load} className="text-xs font-semibold text-brand-600">Retry</button>
        </div>
      )}

      {!loading && !error && conns.length === 0 && (
        <div className="py-8 text-center">
          <Instagram size={22} className="mx-auto text-gray-300 mb-2" />
          <p className="text-xs text-gray-500">No accounts connected yet.</p>
          <p className="text-xs text-gray-400 mt-1">
            Connect one to start receiving DMs and comments.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {conns.map(c => {
          const meta = STATUS[c.status] || STATUS.disconnected
          const StatusIcon = meta.Icon
          const busy = busyId === c.id
          return (
            <div
              key={c.id}
              className={clsx(
                'rounded-2xl px-3 py-3 flex items-start gap-3 transition-colors',
                c.is_active ? 'bg-gray-50' : 'bg-gray-50 opacity-60'
              )}
            >
              <div className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
                <Instagram size={15} className="text-pink-500" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[13px] font-semibold text-gray-900 truncate">
                    {c.ig_username ? `@${c.ig_username}` : (c.page_name || c.ig_login_user_id || `Connection ${c.id}`)}
                  </span>
                  <span className={clsx(
                    'inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded-md',
                    meta.cls
                  )}>
                    <StatusIcon size={10} />
                    {meta.label}
                  </span>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-gray-100 text-gray-600">
                    {SURFACE[c.surface] || c.surface}
                  </span>
                </div>

                <p className="text-xs text-gray-500 mt-1">
                  {c.days_left != null
                    ? (c.days_left < 0
                        ? 'Token expired — reconnect to restore messaging.'
                        : `Token valid for ${c.days_left} more day${c.days_left === 1 ? '' : 's'}.`)
                    : 'No expiry recorded for this token.'}
                </p>
              </div>

              {c.is_active && (
                <div className="flex items-center gap-1 shrink-0">
                  {c.surface === 'instagram_login' && (
                    <button
                      onClick={() => handleRefresh(c)}
                      disabled={busy}
                      title="Refresh token"
                      className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-200/60 transition-colors disabled:opacity-50"
                    >
                      {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                    </button>
                  )}
                  <button
                    onClick={() => handleDisconnect(c)}
                    disabled={busy}
                    title="Disconnect"
                    className="p-1.5 rounded-lg text-gray-500 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <Unlink size={14} />
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
