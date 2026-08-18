import { useState, useEffect } from 'react'
import { Settings2, Sliders, Bell, Plug, Store, Truck, AlertTriangle, Save, Loader2, Zap, Instagram, ShoppingBag, Mail, RefreshCw, MapPin, Plus, Trash2, Send, Download, Bot } from 'lucide-react'
import clsx from 'clsx'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('authToken')}`,
})

const TABS = [
  { id: 'handoff',       label: 'Handoff & assignment', icon: Sliders },
  { id: 'integrations',  label: 'Integrations',         icon: Plug },
  { id: 'business',      label: 'Business info',        icon: Store },
  { id: 'delivery',      label: 'Delivery & orders',    icon: Truck },
  { id: 'notifications', label: 'Notifications',        icon: Bell },
  { id: 'danger',        label: 'Danger zone',          icon: AlertTriangle },
]

export default function Settings({ embedded = false }) {
  const [tab, setTab] = useState('handoff')
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [integrations, setIntegrations] = useState(null)
  const [intLoading, setIntLoading] = useState(true)
  const [intError, setIntError] = useState(null)
  // Values the server resolves from settings + environment together, which the
  // form fields alone cannot determine.
  const [resolved, setResolved] = useState(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetch(`${API_BASE}/settings`, { headers: authHeaders() })
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || 'Failed to load settings')
        setSettings(data.settings)
        setResolved(data.resolved || null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const loadIntegrations = async () => {
    setIntLoading(true); setIntError(null)
    try {
      const res = await fetch(`${API_BASE}/settings/integrations`, { headers: authHeaders() })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to load')
      setIntegrations(d.integrations)
    } catch (err) { setIntError(err.message) } finally { setIntLoading(false) }
  }
  useEffect(() => { loadIntegrations() }, [])

  // Which tabs are currently asking for attention. The rail was six identical
  // buttons: to learn that Shopify hadn't synced in a month you had to guess
  // which tab to open. A stale feed or a dying token is exactly the thing you
  // came here to find, so it belongs in the navigation, not behind it.
  const mt = integrations?.meta, sh = integrations?.shopify
  const tabAlerts = {
    integrations: (sh?.stale || sh?.failed_recently > 0 ||
                   mt?.token_expired || mt?.token_expiring_soon || mt?.connected === false) || false,
  }

  const activeTab = TABS.find(t => t.id === tab)

  // When embedded, the wrapper already owns the page width. Keeping
  // `max-w-7xl mx-auto` here too meant that on a wide screen the wrapper's
  // title sat flush against the layout padding while this block was capped and
  // re-centred — so the heading and the content it belongs to started at two
  // different x positions. Channels and Meta Diagnostics already dropped it
  // when embedded; Settings was the one that didn't.
  return (
    <div className={embedded ? 'space-y-6 w-full' : 'space-y-6 w-full max-w-7xl mx-auto'}>
      {/* Header */}
      {!embedded && (
        <div>
          <h1 className="text-2xl font-bold text-gray-900 leading-tight">Settings</h1>
          <p className="text-sm text-gray-500">Organisation-wide configuration for your assistant.</p>
        </div>
      )}

      {!loading && !error && (
        <AIMasterSwitch settings={settings} setSettings={setSettings} />
      )}

      <div className="flex flex-col md:flex-row gap-5">
        {/* Tab rail */}
        <div className="md:w-60 shrink-0">
          <div className="card rounded-2xl p-1.5 flex md:flex-col gap-1 overflow-x-auto md:overflow-visible hide-scrollbar">
            {TABS.map(t => {
              const Icon = t.icon
              const active = tab === t.id
              const isDanger = t.id === 'danger'
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={clsx(
                    'flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium whitespace-nowrap transition-all text-left shrink-0',
                    active
                      ? (isDanger ? 'bg-red-500 text-white shadow-sm' : 'bg-black text-white shadow-sm')
                      : (isDanger ? 'text-red-600 hover:bg-red-50' : 'text-gray-600 hover:bg-gray-100')
                  )}
                >
                  <Icon size={16} className="shrink-0" />
                  <span className="flex-1">{t.label}</span>
                  {tabAlerts[t.id] && (
                    <span
                      title="Needs attention"
                      className={clsx(
                        'w-1.5 h-1.5 rounded-full shrink-0',
                        active ? 'bg-white' : 'bg-amber-500'
                      )}
                    />
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* Panel */}
        <div className="flex-1 min-w-0">
          {loading ? (
            <PanelSkeleton />
          ) : error ? (
            <div className="bg-red-50 border border-red-200 rounded-2xl p-4 text-sm text-red-600">{error}</div>
          ) : tab === 'handoff' ? (
            <HandoffPanel settings={settings} setSettings={setSettings} />
          ) : tab === 'integrations' ? (
            <IntegrationsPanel data={integrations} loading={intLoading}
                               error={intError} reload={loadIntegrations} />
          ) : tab === 'business' ? (
            <>
              <BusinessPanel settings={settings} setSettings={setSettings} />
              <BrandStoresPanel />
            </>
          ) : tab === 'delivery' ? (
            <DeliveryPanel settings={settings} setSettings={setSettings} />
          ) : tab === 'notifications' ? (
            <NotificationsPanel settings={settings} setSettings={setSettings} resolved={resolved} />
          ) : tab === 'danger' ? (
            <DangerPanel settings={settings} setSettings={setSettings} />
          ) : (
            <ComingSoon tab={activeTab} />
          )}
        </div>
      </div>
    </div>
  )
}

function AIMasterSwitch({ settings, setSettings }) {
  const enabled = settings?.ai?.enabled !== false
  const [saving, setSaving] = useState(false)
  const [confirming, setConfirming] = useState(false)   // 'on' | 'off' | false
  const [handover, setHandover] = useState(null)        // counts from the server
  const [msg, setMsg] = useState(null)

  // What flipping the switch would actually affect, so the prompt can state a
  // real number instead of a vague warning.
  const loadHandover = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/ai/handover`, { headers: authHeaders() })
      if (res.ok) setHandover(await res.json())
    } catch { /* the prompt still works without the count */ }
  }

  const apply = async (next, action = null) => {
    setMsg(null); setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ ai: { enabled: next } }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to save')
      setSettings(d.settings)

      // The queue/restore move is a separate call on purpose. Switching the AI
      // off and redistributing the queue are different decisions, and folding
      // the second into the first would redistribute everything every time an
      // admin wanted the AI quiet for ten minutes.
      if (action) {
        const r2 = await fetch(`${API_BASE}/settings/ai/handover`, {
          method: 'POST', headers: authHeaders(),
          body: JSON.stringify({ action }),
        })
        const d2 = await r2.json()
        if (!r2.ok) throw new Error(d2.error || 'Failed to move conversations')
        setMsg({ type: 'ok', text: action === 'queue'
          ? `${d2.affected} conversation${d2.affected === 1 ? '' : 's'} moved to the agent queue.`
          : `${d2.affected} conversation${d2.affected === 1 ? '' : 's'} handed back to the AI.` })
      }
    } catch (err) {
      setMsg({ type: 'error', text: err.message })
    } finally {
      setSaving(false); setConfirming(false); setHandover(null)
    }
  }

  // Both directions now ask, because both have consequences an admin should
  // see the size of first. Turning ON starts answering real customers; turning
  // OFF strands whatever the AI was holding unless it is queued for people.
  const onToggle = async () => {
    await loadHandover()
    setConfirming(enabled ? 'off' : 'on')
  }

  return (
    <div className={clsx(
      'rounded-2xl border p-5 sm:p-6 transition-colors',
      enabled ? 'bg-white border-gray-200' : 'bg-amber-50 border-amber-300'
    )}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className={clsx('w-10 h-10 rounded-xl flex items-center justify-center shrink-0',
            enabled ? 'bg-brand-50 text-brand-600' : 'bg-amber-100 text-amber-700')}>
            <Bot size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold text-gray-900">Automated AI replies</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {enabled
                ? 'The assistant is replying to customers automatically on all channels.'
                : 'OFF — messages still arrive in the inbox, but every reply is manual.'}
            </p>
          </div>
        </div>
        <button
          onClick={onToggle}
          disabled={saving}
          className={clsx(
            'relative inline-flex w-12 h-6 rounded-full transition-colors shrink-0 disabled:opacity-50',
            enabled ? 'bg-brand-600' : 'bg-gray-300'
          )}
          aria-label="Toggle automated AI replies"
        >
          <span className={clsx(
            'absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform',
            enabled && 'translate-x-6'
          )} />
        </button>
      </div>

      {/* Turning OFF — decide what happens to what the AI is holding.
          Leaving them is not a no-op: their conversations keep ai_enabled=true,
          so the inbox goes on reporting them as "AI handling" while nothing is
          handling them, and because Unclaimed requires ai_enabled=false no
          agent is shown them either. Hence the choice, stated with a number. */}
      {confirming === 'off' && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs font-bold text-gray-900">
            Turn automated replies off?
          </p>
          <p className="text-xs text-gray-600 mt-1">
            {handover?.live_ai_conversations > 0
              ? `${handover.live_ai_conversations} open conversation${handover.live_ai_conversations === 1 ? ' is' : 's are'} currently with the AI.`
              : 'No conversations are currently with the AI.'}
          </p>

          {/* One path, not a choice.
              "Leave them for the AI to resume" promised something that never
              happened: the AI does not catch up on messages received while it
              was off, it only becomes eligible again for the NEXT one. Meanwhile
              those conversations kept ai_enabled=true and status='active', which
              means the Unclaimed queue could not see them (it needs
              'human_override') and no agent's inbox listed them (that needs an
              assignee) — invisible to every part of the product at once. That is
              how 13 direct messages went unanswered for up to 18 days.

              Messages arriving DURING the pause are now routed to agents
              automatically at the gate, so this button only has to deal with the
              backlog that already exists. */}
          {handover?.live_ai_conversations > 0 && (
            <div className="mt-3">
              <button onClick={() => apply(false, 'queue')} disabled={saving}
                className="w-full text-left px-3 py-2.5 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 disabled:opacity-50">
                <span className="block text-xs font-bold text-gray-900">
                  Turn off and queue {handover.live_ai_conversations} conversation
                  {handover.live_ai_conversations === 1 ? '' : 's'} for agents
                </span>
                <span className="block text-[12px] text-gray-500 mt-0.5">
                  Moves them to Unclaimed so agents can pick them up, and anything
                  that arrives while the AI is off goes there too. Already-assigned
                  chats stay with whoever owns them. You can hand back the ones
                  nobody touched when you switch the AI on again.
                </span>
              </button>
            </div>
          )}

          <div className="flex gap-2 mt-3">
            {!handover?.live_ai_conversations && (
              <button onClick={() => apply(false)} disabled={saving}
                className="text-xs font-semibold px-3 py-2 rounded-lg bg-gray-900 text-white hover:bg-black disabled:opacity-50">
                {saving ? 'Turning off…' : 'Turn AI off'}
              </button>
            )}
            <button onClick={() => { setConfirming(false); setHandover(null) }}
              className="text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Turning ON — offer to hand back exactly what the switch took away. */}
      {confirming === 'on' && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs font-bold text-gray-900">Turn automated replies back on?</p>
          <p className="text-xs text-gray-600 mt-1">
            The assistant will start answering real customers on every connected
            channel immediately.
          </p>

          {handover?.restorable > 0 && (
            <div className="mt-3 space-y-2">
              <button onClick={() => apply(true, 'restore')} disabled={saving}
                className="w-full text-left px-3 py-2.5 rounded-lg border border-brand-200 bg-brand-50 hover:bg-brand-100 disabled:opacity-50">
                <span className="block text-xs font-bold text-gray-900">
                  Turn on and hand back {handover.restorable} queued conversation
                  {handover.restorable === 1 ? '' : 's'}
                </span>
                <span className="block text-[12px] text-gray-600 mt-0.5">
                  Only the ones nobody picked up. Claiming a chat or replying to it
                  makes it that agent's, so a hand-back can no longer take a
                  conversation off someone mid-thread.
                  {handover.held_by_humans > 0 && (
                    <> {handover.held_by_humans} conversation
                      {handover.held_by_humans === 1 ? ' is' : 's are'} being handled
                      by an agent and will be left alone.</>
                  )}
                  {' '}Each one handed back gets a note in the thread saying the AI resumed.
                </span>
              </button>
              <button onClick={() => apply(true)} disabled={saving}
                className="w-full text-left px-3 py-2.5 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 disabled:opacity-50">
                <span className="block text-xs font-bold text-gray-900">
                  Turn on for new messages only
                </span>
                <span className="block text-[12px] text-gray-500 mt-0.5">
                  The {handover.restorable} queued conversation
                  {handover.restorable === 1 ? '' : 's'} stay with agents.
                </span>
              </button>
            </div>
          )}

          <div className="flex gap-2 mt-3">
            {!handover?.restorable && (
              <button onClick={() => apply(true)} disabled={saving}
                className="text-xs font-semibold px-3 py-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50">
                {saving ? 'Turning on…' : 'Yes, turn AI on'}
              </button>
            )}
            <button onClick={() => { setConfirming(false); setHandover(null) }}
              className="text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50">
              Cancel
            </button>
          </div>
        </div>
      )}

      {!enabled && !confirming && (
        <p className="text-xs text-amber-800 mt-3 pt-3 border-t border-amber-200">
          Every DM and comment now needs a human reply. Instagram's 24-hour window
          still applies — after that you can't reply until the customer writes again.
        </p>
      )}

      {msg && (
        <p className={clsx('text-xs mt-2', msg.type === 'error' ? 'text-red-600' : 'text-green-700')}>
          {msg.text}
        </p>
      )}
    </div>
  )
}

function DangerPanel({ settings, setSettings }) {
  const [showReset, setShowReset] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [resetting, setResetting] = useState(false)
  const [msg, setMsg] = useState(null)

  const exportConfig = () => {
    const blob = new Blob([JSON.stringify(settings ?? {}, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `shopzetu-settings-${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const doReset = async () => {
    setMsg(null); setResetting(true)
    try {
      const res = await fetch(`${API_BASE}/settings/reset`, { method: 'POST', headers: authHeaders() })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Reset failed')
      setSettings(d.settings)
      setShowReset(false); setConfirmText('')
      setMsg({ type: 'success', text: 'Settings reset to defaults.' })
    } catch (err) { setMsg({ type: 'error', text: err.message }) } finally { setResetting(false) }
  }

  return (
    <div className="space-y-4">
      <div className="card rounded-2xl p-5 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-bold text-gray-900">Export configuration</p>
            <p className="text-xs text-gray-500 mt-0.5">Download your current settings as a JSON backup — worth doing before a reset.</p>
          </div>
          <button onClick={exportConfig} className="text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 flex items-center gap-1.5 shrink-0">
            <Download size={13} /> Export
          </button>
        </div>
      </div>

      <div className="bg-red-50 rounded-2xl border border-red-200 p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-red-100 flex items-center justify-center text-red-600 shrink-0">
            <AlertTriangle size={18} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-red-900">Reset all settings</p>
            <p className="text-xs text-red-700 mt-0.5">Restores handoff, business, delivery, and notification settings to their defaults. Your data — conversations, customers, products — is not touched.</p>

            {!showReset ? (
              <button onClick={() => setShowReset(true)} className="mt-3 text-xs font-semibold px-3 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700">
                Reset to defaults
              </button>
            ) : (
              <div className="mt-3 space-y-2">
                <p className="text-xs text-red-800">Type <span className="font-bold font-mono">RESET</span> to confirm.</p>
                <div className="flex flex-wrap gap-2">
                  <input
                    className="flex-1 min-w-[120px] px-3 py-2 rounded-lg border border-red-300 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-red-400/40"
                    value={confirmText} onChange={e => setConfirmText(e.target.value)} placeholder="RESET"
                  />
                  <button onClick={doReset} disabled={confirmText !== 'RESET' || resetting}
                    className="text-xs font-semibold px-3 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 shrink-0">
                    {resetting ? 'Resetting…' : 'Confirm reset'}
                  </button>
                  <button onClick={() => { setShowReset(false); setConfirmText('') }}
                    className="text-xs font-semibold px-3 py-2 rounded-lg border border-red-200 text-red-700 hover:bg-red-100 shrink-0">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {msg && <p className={`text-xs font-medium px-1 ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}

      <p className="text-[12px] text-gray-400 px-1">
        Deleting conversations, customers, or products isn't exposed here by design — those are irreversible on a live store and shouldn't sit behind a single click.
      </p>
    </div>
  )
}

function PanelSkeleton() {
  return (
    <div className="card rounded-2xl p-5 sm:p-6 animate-pulse">
      <div className="flex items-start gap-3 pb-4 mb-5 border-b border-gray-100">
        <div className="w-10 h-10 rounded-xl bg-gray-200 shrink-0" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="h-3.5 w-40 bg-gray-200 rounded" />
          <div className="h-2.5 w-64 max-w-full bg-gray-100 rounded" />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
        {[0, 1].map(i => (
          <div key={i} className="space-y-2">
            <div className="h-2.5 w-24 bg-gray-100 rounded" />
            <div className="h-10 w-full bg-gray-100 rounded-xl" />
          </div>
        ))}
      </div>
      <div className="space-y-2 mb-5">
        <div className="h-2.5 w-28 bg-gray-100 rounded" />
        <div className="h-20 w-full bg-gray-100 rounded-xl" />
      </div>
      <div className="flex justify-end">
        <div className="h-8 w-28 bg-gray-200 rounded-lg" />
      </div>
    </div>
  )
}

// One header for every section, so a change here reaches all six at once.
// `aside` carries a section-specific fact (a count, a state) — the headers were
// title-and-blurb only, which told you what the section was but never anything
// about your own configuration.
function PanelHeader({ icon: Icon, title, desc, aside = null, tone = 'brand' }) {
  return (
    <div className="flex items-start gap-3 pb-4 mb-5 border-b border-gray-100">
      <div className={clsx(
        'w-10 h-10 rounded-xl flex items-center justify-center shrink-0',
        tone === 'danger' ? 'bg-red-50 text-red-600' : 'bg-brand-50 text-brand-600',
      )}>
        <Icon size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <h2 className="text-sm font-bold text-gray-900 leading-tight">{title}</h2>
        <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
      </div>
      {aside && <div className="shrink-0 pt-0.5">{aside}</div>}
    </div>
  )
}

// Small labelled pill for PanelHeader's `aside`.
function HeaderStat({ label, value, tone = 'default' }) {
  return (
    <span className={clsx(
      'inline-flex items-baseline gap-1.5 rounded-lg px-2.5 py-1 border',
      tone === 'warn'
        ? 'bg-amber-50 border-amber-200 text-amber-700'
        : 'bg-gray-50 border-gray-200 text-gray-600',
    )}>
      <span className="text-xs font-bold">{value}</span>
      <span className="text-[11px] font-medium uppercase tracking-wide opacity-70">{label}</span>
    </span>
  )
}

function HandoffPanel({ settings, setSettings }) {
  const h = settings?.handoff || {}
  const [maxLoad, setMaxLoad] = useState(h.max_agent_load ?? 10)
  const [presence, setPresence] = useState(h.presence_window_seconds ?? 300)
  const [bridging, setBridging] = useState(h.bridging_reply ?? '')
  const [unclaimedMins, setUnclaimedMins] = useState(h.unclaimed_alert_minutes ?? 15)
  const [agentWaitMins, setAgentWaitMins] = useState(h.agent_waiting_minutes ?? 10)
  // Both of these were live behaviour with no way to see or change them: a
  // nightly job closes conversations idle past auto_resolve_days, and a reply
  // arriving within reopen_resolved_within_hours re-opens a resolved chat
  // instead of forking a new one. Real rules acting on real conversations,
  // decided by a constant nobody could read off the page.
  const [autoResolve, setAutoResolve] = useState(h.auto_resolve_days ?? 14)
  const [reopenHours, setReopenHours] = useState(
    settings?.conversations?.reopen_resolved_within_hours ?? 24)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition'

  const save = async () => {
    setMsg(null)
    const ml = parseInt(maxLoad, 10)
    const pw = parseInt(presence, 10)
    if (!Number.isFinite(ml) || ml < 1 || ml > 100) return setMsg({ type: 'error', text: 'Max load must be between 1 and 100.' })
    if (!Number.isFinite(pw) || pw < 30 || pw > 3600) return setMsg({ type: 'error', text: 'Presence window must be 30–3600 seconds.' })
    const um = parseInt(unclaimedMins, 10)
    const aw = parseInt(agentWaitMins, 10)
    if (!Number.isFinite(um) || um < 1 || um > 1440) return setMsg({ type: 'error', text: 'Unclaimed alert must be 1–1440 minutes.' })
    if (!Number.isFinite(aw) || aw < 1 || aw > 1440) return setMsg({ type: 'error', text: 'Agent wait flag must be 1–1440 minutes.' })
    const ar = parseInt(autoResolve, 10)
    const rh = parseInt(reopenHours, 10)
    if (!Number.isFinite(ar) || ar < 0 || ar > 365) return setMsg({ type: 'error', text: 'Auto-resolve must be 0–365 days (0 turns it off).' })
    if (!Number.isFinite(rh) || rh < 0 || rh > 720) return setMsg({ type: 'error', text: 'Re-open window must be 0–720 hours (0 always starts a new chat).' })
    if (!bridging.trim()) return setMsg({ type: 'error', text: 'The handoff message cannot be empty.' })

    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ handoff: {
          max_agent_load: ml, presence_window_seconds: pw, bridging_reply: bridging.trim(),
          unclaimed_alert_minutes: um, agent_waiting_minutes: aw, auto_resolve_days: ar,
        }, conversations: { reopen_resolved_within_hours: rh } }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to save')
      setSettings(data.settings)
      setMsg({ type: 'success', text: 'Saved.' })
    } catch (err) {
      setMsg({ type: 'error', text: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card rounded-2xl p-5 sm:p-6">
      <PanelHeader
        icon={Sliders}
        title="Handoff & assignment"
        desc="How conversations auto-assign, and what customers hear when a chat is escalated."
        aside={<HeaderStat label="per agent" value={h.max_agent_load ?? 10} />}
      />

      <div className="flex items-center gap-2 text-[12px] font-medium text-brand-700 bg-brand-50 rounded-lg px-3 py-2 mb-5">
        <Zap size={13} className="shrink-0" />
        Changes take effect immediately — no redeploy needed.
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
        <div>
          <label className={labelCls}>Max open conversations per agent</label>
          <div className="relative">
            <input className={`${inputCls} pr-28`} type="number" min="1" max="100" value={maxLoad} onChange={e => setMaxLoad(e.target.value)} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">conversations</span>
          </div>
          <p className="text-[12px] text-gray-400 mt-1.5">Agents at or above this are skipped for auto-assignment.</p>
        </div>
        <div>
          <label className={labelCls}>Presence window</label>
          <div className="relative">
            <input className={`${inputCls} pr-16`} type="number" min="30" max="3600" value={presence} onChange={e => setPresence(e.target.value)} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">seconds</span>
          </div>
          <p className="text-[12px] text-gray-400 mt-1.5">How recently an agent must've been active to count as present. 300 = 5 min.</p>
        </div>
        <div>
          <label className={labelCls}>Alert when unclaimed for</label>
          <div className="relative">
            <input className={`${inputCls} pr-16`} type="number" min="1" max="1440" value={unclaimedMins} onChange={e => setUnclaimedMins(e.target.value)} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">minutes</span>
          </div>
          <p className="text-[12px] text-gray-400 mt-1.5">A conversation waiting this long with nobody assigned alerts supervisors.</p>
        </div>
        <div>
          <label className={labelCls}>Flag agent's chat after</label>
          <div className="relative">
            <input className={`${inputCls} pr-16`} type="number" min="1" max="1440" value={agentWaitMins} onChange={e => setAgentWaitMins(e.target.value)} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">minutes</span>
          </div>
          <p className="text-[12px] text-gray-400 mt-1.5">A customer waiting this long on an agent who owns the chat shows in that agent's Needs Attention panel.</p>
        </div>
      </div>

      <div className="border-t border-gray-200/70 dark:border-white/10 pt-5 mb-5">
        <p className="text-xs font-semibold text-gray-900 mb-1">Conversation lifecycle</p>
        <p className="text-[12px] text-gray-400 mb-4">
          When a chat closes itself, and when a returning customer continues the old thread instead of starting a new one.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Auto-resolve silent chats after</label>
            <div className="relative">
              <input className={`${inputCls} pr-14`} type="number" min="0" max="365" value={autoResolve} onChange={e => setAutoResolve(e.target.value)} />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">days</span>
            </div>
            <p className="text-[12px] text-gray-400 mt-1.5">
              Only closes chats where <span className="font-medium text-gray-500">we</span> spoke last — if the customer is still waiting on a reply it stays open. 0 turns auto-resolve off.
            </p>
          </div>
          <div>
            <label className={labelCls}>Re-open a resolved chat within</label>
            <div className="relative">
              <input className={`${inputCls} pr-16`} type="number" min="0" max="720" value={reopenHours} onChange={e => setReopenHours(e.target.value)} />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">hours</span>
            </div>
            <p className="text-[12px] text-gray-400 mt-1.5">
              A reply this soon after resolving continues the same conversation. Later, it starts a fresh one. 0 always starts fresh.
            </p>
          </div>
        </div>
      </div>

      <div className="mb-5">
        <label className={labelCls}>Default handoff message</label>
        <textarea className={`${inputCls} resize-none`} rows={3} value={bridging} onChange={e => setBridging(e.target.value)} />
        <p className="text-[12px] text-gray-400 mt-1.5">Sent to the customer on escalation. Abuse and frustration cases use their own tuned messages.</p>
      </div>

      <div className="flex items-center justify-end gap-3">
        {msg && <p className={`text-xs font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
        <button onClick={save} disabled={saving} className="btn-primary flex items-center gap-2 text-xs disabled:opacity-50">
          <Save size={14} /> {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}

function BusinessPanel({ settings, setSettings }) {
  const b = settings?.business || {}
  const [storeName, setStoreName] = useState(b.store_name ?? '')
  const [about, setAbout] = useState(b.about ?? '')
  const [hours, setHours] = useState(b.hours ?? '')
  const [phone, setPhone] = useState(b.phone ?? '')
  const [whatsapp, setWhatsapp] = useState(b.whatsapp ?? '')
  const [email, setEmail] = useState(b.email ?? '')
  const [timezone, setTimezone] = useState(b.timezone ?? 'Africa/Nairobi')
  const [weekStart, setWeekStart] = useState(b.week_starts_on ?? 'monday')
  const [zones, setZones] = useState([])
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  // What the admin's own browser thinks it is — offered as a shortcut, never
  // applied automatically: the reporting zone is the business's, not the
  // viewer's, and someone travelling shouldn't silently reshape the Dashboard.
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone

  useEffect(() => {
    fetch(`${API_BASE}/settings/timezones`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => setZones(d?.timezones || []))
      .catch(() => {})   // datalist is a convenience; typing still works without it
  }, [])

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition'

  const save = async () => {
    setMsg(null)
    if (!storeName.trim()) return setMsg({ type: 'error', text: 'Store name is required.' })
    if (!timezone.trim()) return setMsg({ type: 'error', text: 'Timezone is required.' })
    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ business: {
          store_name: storeName.trim(), about: about.trim(), hours: hours.trim(),
          phone: phone.trim(), whatsapp: whatsapp.trim(), email: email.trim(),
          timezone: timezone.trim(), week_starts_on: weekStart,
        } }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to save')
      setSettings(d.settings)
      setMsg({ type: 'success', text: 'Saved.' })
    } catch (err) { setMsg({ type: 'error', text: err.message }) } finally { setSaving(false) }
  }

  return (
    <div className="space-y-4">
      <div className="card rounded-2xl p-5 sm:p-6">
        <PanelHeader icon={Store} title="Business info"
          desc="What your assistant knows about the business — the background it answers from, plus the details customers ask for directly." />

        {/* The one field here that is prose rather than a value. Everything
            else answers a fixed question; this is for what does not fit a
            field and still changes the answer. */}
        <div className="mb-5">
          <label className={labelCls}>What the assistant should know about us</label>
          <textarea
            className={inputCls + ' min-h-[140px] resize-y leading-relaxed'}
            value={about}
            onChange={e => setAbout(e.target.value)}
            placeholder={`Shop Zetu is online-only — we have no walk-in shop of our own.
We manage products, stock and delivery for a number of brands.
Vivo is one of them, and Vivo products can also be bought in Vivo's own stores.
Returns are accepted within 7 days, unworn and with tags on.`}
          />
          <p className="text-xs text-gray-500 mt-1.5">
            Goes into every reply as background. Write it as facts, one per line —
            it is read, not recited. This is also the quickest way to correct the
            assistant: if it says something untrue, write the true version here.
            For delivery fees and timeframes use <span className="font-semibold">Delivery &amp; orders</span> instead,
            so a price lives in one place.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
          <div>
            <label className={labelCls}>Store name</label>
            <input className={inputCls} value={storeName} onChange={e => setStoreName(e.target.value)} placeholder="Shop Zetu" />
          </div>
          <div>
            <label className={labelCls}>Opening hours</label>
            <input className={inputCls} value={hours} onChange={e => setHours(e.target.value)} placeholder="Mon–Sat, 8am–8pm EAT" />
          </div>
          <div>
            <label className={labelCls}>Phone</label>
            <input className={inputCls} value={phone} onChange={e => setPhone(e.target.value)} placeholder="+254 7…" />
          </div>
          <div>
            <label className={labelCls}>WhatsApp</label>
            <input className={inputCls} value={whatsapp} onChange={e => setWhatsapp(e.target.value)} placeholder="+254 7…" />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls}>Contact email</label>
            <input className={inputCls} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="hello@shopzetu.com" />
          </div>
        </div>

        {/* Reporting period — drives the Dashboard's calendar windows */}
        <div className="pt-5 border-t border-gray-100 mb-5">
          <p className="text-xs font-bold text-gray-900 mb-1">Reporting</p>
          <p className="text-xs text-gray-500 mb-4">
            Analytics are stored in UTC and shown in this timezone. It decides when
            “Today”, “This week” and “This month” on the Dashboard begin — set it wrong
            and a day’s figures land in the neighbouring day.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Timezone</label>
              <input
                className={inputCls}
                list="tz-list"
                value={timezone}
                onChange={e => setTimezone(e.target.value)}
                placeholder="Africa/Nairobi"
                spellCheck={false}
              />
              <datalist id="tz-list">
                {zones.map(z => <option key={z} value={z} />)}
              </datalist>
              {browserTz && browserTz !== timezone && (
                <button
                  type="button"
                  onClick={() => setTimezone(browserTz)}
                  className="mt-1.5 text-[12px] text-brand-600 hover:text-brand-700 font-medium transition-colors"
                >
                  Use this device’s timezone ({browserTz})
                </button>
              )}
            </div>
            <div>
              <label className={labelCls}>Week starts on</label>
              <select className={inputCls} value={weekStart} onChange={e => setWeekStart(e.target.value)}>
                <option value="monday">Monday</option>
                <option value="sunday">Sunday</option>
              </select>
              <p className="mt-1.5 text-[12px] text-gray-400">
                Where the Dashboard’s “This week” window begins.
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-3">
          {msg && <p className={`text-xs font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
          <button onClick={save} disabled={saving} className="btn-primary flex items-center gap-2 text-xs disabled:opacity-50">
            <Save size={14} /> {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

function WebhookRegister() {
  const [hooks, setHooks] = useState(null)
  const [loading, setLoading] = useState(true)
  const [registering, setRegistering] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/settings/webhooks`, { headers: authHeaders() })
      const d = await res.json()
      if (res.ok) setHooks(d.webhooks || [])
    } catch { /* silent */ } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const register = async () => {
    setMsg(null); setRegistering(true)
    try {
      const res = await fetch(`${API_BASE}/settings/webhooks/register`, { method: 'POST', headers: authHeaders() })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to register')
      const created = (d.created || []).length
      const already = (d.already_registered || []).length
      const errs = (d.errors || []).length
      setMsg({
        type: errs ? 'error' : 'success',
        text: `${created} registered, ${already} already set${errs ? `, ${errs} failed — check Logs` : ''}.`,
      })
      await load()
    } catch (err) {
      setMsg({ type: 'error', text: err.message })
    } finally {
      setRegistering(false)
    }
  }

  return (
    <div className="mt-3 pt-3 border-t border-gray-100">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-gray-800">Real-time webhooks</p>
          <p className="text-[12px] text-gray-500 mt-0.5">
            {loading ? 'Checking…' : `${hooks?.length || 0} topic${hooks?.length === 1 ? '' : 's'} registered with Shopify.`}
          </p>
        </div>
        <button onClick={register} disabled={registering}
          className="text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-50 shrink-0">
          {registering ? 'Registering…' : 'Register webhooks'}
        </button>
      </div>
      {msg && <p className={`text-[12px] mt-2 font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
    </div>
  )
}

function BrandStoresPanel() {
  // Shop Zetu is online-only. These are the shops belonging to the brands whose
  // products we manage — Vivo and its sub-brands — and they are the ONLY
  // addresses the assistant is allowed to give out. Anything not listed here it
  // will say it doesn't have, rather than guess, because a wrong address sends
  // a real person across Nairobi to a shop that isn't there.
  const [stores, setStores] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/settings/brand-stores`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Could not load stores')))
      .then(d => setStores(d.stores || []))
      .catch(err => setMsg({ type: 'error', text: err.message }))
      .finally(() => setLoading(false))
  }, [])

  const patch = (i, key, val) =>
    setStores(prev => prev.map((s, n) => n === i ? { ...s, [key]: val } : s))
  const remove = (i) => setStores(prev => prev.filter((_, n) => n !== i))
  const add = () => setStores(prev => [...prev, { name: '', address: '', area: '', phone: '', hours: '' }])

  // Hours are identical across every branch today, so a new row copies the one
  // above rather than making someone retype it and risk a branch that quietly
  // disagrees with the other twenty.
  const addLikeLast = () => setStores(prev => prev.length
    ? [...prev, { name: '', address: '', area: '', phone: '', hours: prev[prev.length - 1].hours || '' }]
    : [{ name: '', address: '', area: '', phone: '', hours: '' }])

  const named = stores.filter(s => (s.name || '').trim())
  const unnamed = stores.length - named.length

  const save = async () => {
    setMsg(null); setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings/brand-stores`, {
        method: 'PUT', headers: authHeaders(),
        body: JSON.stringify({ stores }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to save')
      setStores(d.stores)
      setMsg({ type: 'success', text: `Saved ${d.stores.length} store${d.stores.length === 1 ? '' : 's'}.` })
    } catch (err) { setMsg({ type: 'error', text: err.message }) } finally { setSaving(false) }
  }

  const inputCls = 'w-full px-2.5 py-2 rounded-lg border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition'

  return (
    <div className="card rounded-2xl p-5 sm:p-6">
      <PanelHeader icon={MapPin} title="Brand stores"
        desc="Physical shops belonging to the brands we manage. The assistant may give out these addresses and no others — anything not listed here it will say it doesn't have rather than guess." />

      {loading ? (
        <p className="text-xs text-gray-500">Loading…</p>
      ) : (
        <>
          <div className="space-y-3">
            {stores.map((s, i) => (
              <div key={i} className="rounded-xl border border-gray-200 p-3">
                <div className="flex items-start gap-2">
                  <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input className={inputCls} value={s.name || ''} placeholder="Vivo - Sarit Centre Mall"
                      onChange={e => patch(i, 'name', e.target.value)} />
                    <input className={inputCls} value={s.phone || ''} placeholder="+254 7…"
                      onChange={e => patch(i, 'phone', e.target.value)} />
                    <input className={inputCls} value={s.address || ''} placeholder="Ground Floor, New Wing"
                      onChange={e => patch(i, 'address', e.target.value)} />
                    <input className={inputCls} value={s.area || ''} placeholder="Karuna Road, Nairobi"
                      onChange={e => patch(i, 'area', e.target.value)} />
                    <input className={inputCls + ' sm:col-span-2'} value={s.hours || ''}
                      placeholder="Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
                      onChange={e => patch(i, 'hours', e.target.value)} />
                  </div>
                  <button onClick={() => remove(i)} title="Remove this store"
                    className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 shrink-0">
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button onClick={addLikeLast}
            className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700">
            <Plus size={14} /> Add store
          </button>

          <div className="flex items-center gap-3 mt-5 pt-5 border-t border-gray-100">
            <button onClick={save} disabled={saving}
              className="inline-flex items-center gap-2 text-xs font-semibold px-4 py-2.5 rounded-xl bg-gray-900 text-white hover:bg-black disabled:opacity-50">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
              {saving ? 'Saving…' : 'Save stores'}
            </button>
            <span className="text-xs text-gray-500">
              {named.length} store{named.length === 1 ? '' : 's'} the assistant can name
              {unnamed > 0 && <span className="text-amber-600"> · {unnamed} row{unnamed === 1 ? '' : 's'} without a name will be dropped</span>}
            </span>
          </div>
          {msg && <p className={`text-[12px] mt-2 font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
        </>
      )}
    </div>
  )
}

function DeliveryPanel({ settings, setSettings }) {
  const d = settings?.delivery || {}
  const [zones, setZones] = useState(Array.isArray(d.zones) ? d.zones : [])
  const [notes, setNotes] = useState(d.notes ?? '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition'

  const updateZone = (i, field, val) => setZones(zs => zs.map((z, idx) => idx === i ? { ...z, [field]: val } : z))
  const addZone = () => setZones(zs => [...zs, { name: '', fee: '', eta: '' }])
  const removeZone = (i) => setZones(zs => zs.filter((_, idx) => idx !== i))

  const save = async () => {
    setMsg(null)
    const clean = zones
      .map(z => ({ name: (z.name || '').trim(), fee: (z.fee || '').trim(), eta: (z.eta || '').trim() }))
      .filter(z => z.name)
    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ delivery: { zones: clean, notes: notes.trim() } }),
      })
      const dd = await res.json()
      if (!res.ok) throw new Error(dd.error || 'Failed to save')
      setSettings(dd.settings)
      setZones(clean)
      setMsg({ type: 'success', text: 'Saved.' })
    } catch (err) { setMsg({ type: 'error', text: err.message }) } finally { setSaving(false) }
  }

  return (
    <div className="card rounded-2xl p-5 sm:p-6">
      <PanelHeader icon={Truck} title="Delivery & orders"
        desc="Delivery zones and rates your assistant quotes when customers ask about shipping."
        aside={<HeaderStat label={zones.length === 1 ? 'zone' : 'zones'} value={zones.length}
                           tone={zones.length === 0 ? 'warn' : 'default'} />} />

      <div className="flex items-center gap-2 text-[12px] font-medium text-brand-700 bg-brand-50 rounded-lg px-3 py-2 mb-5">
        <Zap size={13} className="shrink-0" />
        Add zones so the assistant can answer "how much is delivery?" — otherwise it just says it'll check with the team.
      </div>

      <label className={labelCls}>Delivery zones</label>
      <div className="space-y-2 mb-3">
        {zones.length === 0 && <p className="text-xs text-gray-400 py-2">No zones yet. Add one below.</p>}
        {zones.map((z, i) => (
          <div key={i} className="flex gap-2 items-start">
            <input className={inputCls} placeholder="Zone (e.g. Nairobi CBD)" value={z.name || ''} onChange={e => updateZone(i, 'name', e.target.value)} />
            <input className={`${inputCls} sm:w-32 shrink-0`} placeholder="Fee" value={z.fee || ''} onChange={e => updateZone(i, 'fee', e.target.value)} />
            <input className={`${inputCls} sm:w-36 shrink-0`} placeholder="ETA" value={z.eta || ''} onChange={e => updateZone(i, 'eta', e.target.value)} />
            <button onClick={() => removeZone(i)} className="p-2.5 text-gray-400 hover:text-red-600 shrink-0" title="Remove zone">
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
      <button onClick={addZone} className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1.5 mb-5">
        <Plus size={14} /> Add zone
      </button>

      <div className="mb-5">
        <label className={labelCls}>Delivery notes</label>
        <textarea className={`${inputCls} resize-none`} rows={3} value={notes} onChange={e => setNotes(e.target.value)}
          placeholder="e.g. Free delivery on orders over KES 5,000. Countrywide shipping via courier, 2–4 days." />
        <p className="text-[12px] text-gray-400 mt-1.5">Anything zones don't cover — free-delivery thresholds, courier info, timelines.</p>
      </div>

      <div className="flex items-center justify-end gap-3">
        {msg && <p className={`text-xs font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
        <button onClick={save} disabled={saving} className="btn-primary flex items-center gap-2 text-xs disabled:opacity-50">
          <Save size={14} /> {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}

function Toggle({ on, onChange }) {
  return (
    <button type="button" onClick={() => onChange(!on)}
      className={clsx('relative w-10 h-6 rounded-full transition-colors shrink-0', on ? 'bg-brand-500' : 'bg-gray-300')}>
      <span className={clsx('absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform', on && 'translate-x-4')} />
    </button>
  )
}

function NotificationsPanel({ settings, setSettings, resolved }) {
  const n = settings?.notifications || {}
  const [enabled, setEnabled] = useState(n.discord_enabled ?? true)
  const [url, setUrl] = useState(n.discord_webhook_url ?? '')
  // Server-resolved: covers a webhook supplied by environment variable, which
  // the form field cannot see.
  const delivering = resolved?.discord_delivering ?? false
  const fromEnv = resolved?.discord_url_source === 'env'
  const [severity, setSeverity] = useState(n.discord_min_severity ?? 'warning')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState(null)

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition'

  const save = async () => {
    setMsg(null); setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ notifications: { discord_enabled: enabled, discord_webhook_url: url.trim(), discord_min_severity: severity } }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to save')
      setSettings(d.settings)
      setMsg({ type: 'success', text: 'Saved.' })
    } catch (err) { setMsg({ type: 'error', text: err.message }) } finally { setSaving(false) }
  }

  const sendTest = async () => {
    setMsg(null); setTesting(true)
    try {
      const res = await fetch(`${API_BASE}/settings/notifications/test`, {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ webhook_url: url.trim() }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Test failed')
      setMsg({ type: 'success', text: 'Test alert sent — check Discord.' })
    } catch (err) { setMsg({ type: 'error', text: err.message }) } finally { setTesting(false) }
  }

  return (
    <div className="card rounded-2xl p-5 sm:p-6">
      {/* Whether alerts are actually going out. The webhook URL can come from
          this form OR from the DISCORD_WEBHOOK_URL environment variable, so
          judging it on the form field alone reported "not delivering" while
          alerts were in fact being sent. The server resolves both and says. */}
      <PanelHeader icon={Bell} title="Notifications"
        desc="Where operational alerts go when syncs fail or run long."
        aside={<HeaderStat
                 label={delivering ? 'alerts on' : 'not delivering'}
                 value={delivering ? severity : 'off'}
                 tone={enabled && !delivering ? 'warn' : 'default'} />} />

      <div className="flex items-center justify-between py-3 border-b border-gray-100 mb-4">
        <div className="min-w-0 pr-3">
          <p className="text-sm font-semibold text-gray-900">Discord alerts</p>
          <p className="text-xs text-gray-500 mt-0.5">Ping a Discord channel on sync failures and stuck jobs.</p>
        </div>
        <Toggle on={enabled} onChange={setEnabled} />
      </div>

      <div className={clsx('space-y-4 transition-opacity', !enabled && 'opacity-50 pointer-events-none')}>
        <div>
          <label className={labelCls}>Webhook URL</label>
          <input className={`${inputCls} font-mono text-xs`} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://discord.com/api/webhooks/…" />
          {/* An empty field with alerts working reads as broken unless we say
              where the webhook is coming from. */}
          {fromEnv ? (
            <p className="text-[12px] text-emerald-600 mt-1.5 font-medium">
              Using the server's environment-configured webhook. Alerts are being delivered — enter a URL here only to override it.
            </p>
          ) : (
            <p className="text-[12px] text-gray-400 mt-1.5">Leave blank to use the server's env-configured webhook, if any.</p>
          )}
        </div>
        <div>
          <label className={labelCls}>Alert level</label>
          <select className={inputCls} value={severity} onChange={e => setSeverity(e.target.value)}>
            <option value="warning">All alerts (warnings + failures)</option>
            <option value="failure">Failures only</option>
          </select>
        </div>
        <button onClick={sendTest} disabled={testing} className="text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-50 flex items-center gap-1.5">
          <Send size={13} /> {testing ? 'Sending…' : 'Send test alert'}
        </button>
      </div>

      <div className="mt-5 pt-4 border-t border-gray-100">
        <p className="text-[12px] text-gray-400">In-app notifications (assignments, escalations) are always on and can't be disabled here.</p>
      </div>

      <div className="flex items-center justify-end gap-3 mt-4">
        {msg && <p className={`text-xs font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
        <button onClick={save} disabled={saving} className="btn-primary flex items-center gap-2 text-xs disabled:opacity-50">
          <Save size={14} /> {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}

const fmtAgo = (iso) => {
  if (!iso) return 'Never'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return new Date(iso).toLocaleDateString()
}
const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

function StatusPill({ ok, warn }) {
  const cls = warn ? 'bg-amber-50 text-amber-700' : ok ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
  const dot = warn ? 'bg-amber-500' : ok ? 'bg-green-500' : 'bg-gray-400'
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-[12px] font-semibold px-2 py-1 rounded-full shrink-0', cls)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', dot)} />
      {warn ? 'Needs attention' : ok ? 'Connected' : 'Not connected'}
    </span>
  )
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-xs gap-3">
      <span className="text-gray-500 shrink-0">{label}</span>
      <span className={clsx('text-gray-800 font-medium truncate text-right', mono && 'font-mono text-[12px]')}>{value}</span>
    </div>
  )
}

function IntegrationCard({ icon: Icon, name, ok, warn, children }) {
  return (
    <div className="card rounded-2xl p-4 sm:p-5">
      <div className="flex items-center justify-between mb-2.5 gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-gray-100 flex items-center justify-center text-gray-700 shrink-0">
            <Icon size={17} />
          </div>
          <span className="text-sm font-bold text-gray-900 truncate">{name}</span>
        </div>
        <StatusPill ok={ok} warn={warn} />
      </div>
      <div className="border-t border-gray-100 pt-1.5">{children}</div>
    </div>
  )
}

// State lives in Settings so the tab rail can flag a problem without you having
// to open the tab to find out there is one. Same single request either way.
function IntegrationsPanel({ data, loading, error, reload }) {
  const load = reload
  const m = data?.meta, s = data?.shopify, b = data?.brevo

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center text-brand-600 shrink-0">
            <Plug size={18} />
          </div>
          <div>
            <h2 className="text-sm font-bold text-gray-900">Integrations</h2>
            <p className="text-xs text-gray-500 mt-0.5">Connection health for the services powering your assistant.</p>
          </div>
        </div>
        <button onClick={load} disabled={loading} className="text-gray-400 hover:text-gray-700 p-2 rounded-lg hover:bg-gray-100 transition-colors" title="Re-check">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {error ? (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 text-sm text-red-600">{error}</div>
      ) : loading && !data ? (
        <PanelSkeleton />
      ) : (
        <>
          <IntegrationCard icon={Instagram} name="Meta · Instagram"
                           ok={m?.connected} warn={m?.token_expiring_soon || m?.token_expired}>
            {m?.connected ? (
              <>
                {m.page_name && <Row label="Page" value={m.page_name} />}
                {m.ig_username && <Row label="Instagram" value={`@${m.ig_username}`} />}
                {m.source === 'env' && <Row label="Source" value="Legacy env token" />}
                {m.token_expires_at && (
                  <Row label="Token expires"
                       value={`${fmtDate(m.token_expires_at)}${
                         m.token_days_left != null && m.token_days_left >= 0
                           ? ` · ${m.token_days_left}d left` : ''}`} />
                )}
                {m.token_expired && (
                  <p className="text-[12px] text-red-600 mt-1.5">
                    This token has expired — Instagram messages are not being sent or received. Reconnect the account.
                  </p>
                )}
                {m.token_expiring_soon && !m.token_expired && (
                  <p className="text-[12px] text-amber-600 mt-1.5">
                    Expires in {m.token_days_left} day{m.token_days_left === 1 ? '' : 's'}. A daily job refreshes this — if it's still falling, that job has been failing.
                  </p>
                )}
              </>
            ) : (
              <p className="text-xs text-gray-500 py-1">Not connected. Link a Facebook Page and Instagram account through Facebook Login.</p>
            )}
          </IntegrationCard>

          <IntegrationCard icon={ShoppingBag} name="Shopify" ok={s?.connected} warn={s?.recent_failed}>
            {s?.connected ? (
              <>
                <Row label="Products synced" value={fmtAgo(s.last_sync?.products)} />
                <Row label="Orders synced" value={fmtAgo(s.last_sync?.orders)} />
                <Row label="Customers synced" value={fmtAgo(s.last_sync?.customers)} />
                {/* Name the feed and the number. "Something failed" sends you
                    to the Logs to work out what; "Orders and products haven't
                    synced in over 9h" tells you where to look before you go. */}
                {s.stale && (
                  <p className="text-[12px] text-amber-600 mt-1.5">
                    {s.stale_kinds.join(' and ')} {s.stale_kinds.length === 1 ? 'has' : 'have'} not synced in over {s.stale_after_hours}h — syncs are scheduled every 3h.
                  </p>
                )}
                {s.failed_recently > 0 && (
                  <p className="text-[12px] text-amber-600 mt-1.5">
                    {s.failed_recently} sync {s.failed_recently === 1 ? 'job' : 'jobs'} failed in the last 24h — check Logs.
                  </p>
                )}
                <WebhookRegister />
              </>
            ) : (
              <p className="text-xs text-gray-500 py-1">No successful sync yet. Trigger a products sync to verify the connection.</p>
            )}
          </IntegrationCard>

          <IntegrationCard icon={Mail} name="Brevo · Email" ok={b?.configured}>
            {b?.configured ? (
              <Row label="Verified sender" value={b.sender} mono />
            ) : (
              <p className="text-xs text-gray-500 py-1">Not configured. Add a Brevo API key and verified sender to send emails.</p>
            )}
          </IntegrationCard>
        </>
      )}
    </div>
  )
}

function ComingSoon({ tab }) {
  const Icon = tab?.icon || Settings2
  return (
    <div className="card rounded-2xl p-10 text-center">
      <div className="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center text-gray-400 mx-auto mb-3">
        <Icon size={22} />
      </div>
      <p className="text-sm font-semibold text-gray-700">{tab?.label}</p>
      <p className="text-xs text-gray-400 mt-1">This section is coming soon.</p>
    </div>
  )
}