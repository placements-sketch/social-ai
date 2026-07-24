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

export default function Settings() {
  const [tab, setTab] = useState('handoff')
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetch(`${API_BASE}/settings`, { headers: authHeaders() })
        const data = await res.json()
        if (!res.ok) throw new Error(data.error || 'Failed to load settings')
        setSettings(data.settings)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const activeTab = TABS.find(t => t.id === tab)

  return (
    <div className="space-y-6 w-full max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 leading-tight">Settings</h1>
        <p className="text-sm text-gray-500">Organisation-wide configuration for your assistant.</p>
      </div>

      {!loading && !error && (
        <AIMasterSwitch settings={settings} setSettings={setSettings} />
      )}

      <div className="flex flex-col md:flex-row gap-5">
        {/* Tab rail */}
        <div className="md:w-60 shrink-0">
          <div className="bg-white rounded-2xl border border-gray-200 p-1.5 flex md:flex-col gap-1 overflow-x-auto md:overflow-visible hide-scrollbar">
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
                  <span>{t.label}</span>
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
            <IntegrationsPanel />
          ) : tab === 'business' ? (
            <BusinessPanel settings={settings} setSettings={setSettings} />
          ) : tab === 'delivery' ? (
            <DeliveryPanel settings={settings} setSettings={setSettings} />
          ) : tab === 'notifications' ? (
            <NotificationsPanel settings={settings} setSettings={setSettings} />
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
  const [confirming, setConfirming] = useState(false)
  const [msg, setMsg] = useState(null)

  const apply = async (next) => {
    setMsg(null); setSaving(true); setConfirming(false)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ ai: { enabled: next } }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to save')
      setSettings(d.settings)
    } catch (err) {
      setMsg({ type: 'error', text: err.message })
    } finally { setSaving(false) }
  }

  // Turning ON is the risky direction — it starts auto-replying to real
  // customers — so that one asks first. Turning OFF is immediate.
  const onToggle = () => (enabled ? apply(false) : setConfirming(true))

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

      {confirming && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs text-gray-700">
            Turn automated replies back on? The assistant will start answering real
            customers on every connected channel immediately.
          </p>
          <div className="flex gap-2 mt-2.5">
            <button onClick={() => apply(true)} disabled={saving}
              className="text-xs font-semibold px-3 py-2 rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50">
              {saving ? 'Turning on…' : 'Yes, turn AI on'}
            </button>
            <button onClick={() => setConfirming(false)}
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

      {msg && <p className="text-xs text-red-600 mt-2">{msg.text}</p>}
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
      <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
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
                    className="flex-1 min-w-[120px] px-3 py-2 rounded-lg border border-red-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-red-400/40"
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

      <p className="text-[11px] text-gray-400 px-1">
        Deleting conversations, customers, or products isn't exposed here by design — those are irreversible on a live store and shouldn't sit behind a single click.
      </p>
    </div>
  )
}

function PanelSkeleton() {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6 animate-pulse">
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

function PanelHeader({ icon: Icon, title, desc }) {
  return (
    <div className="flex items-start gap-3 pb-4 mb-5 border-b border-gray-100">
      <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center text-brand-600 shrink-0">
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <h2 className="text-sm font-bold text-gray-900">{title}</h2>
        <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
      </div>
    </div>
  )
}

function HandoffPanel({ settings, setSettings }) {
  const h = settings?.handoff || {}
  const [maxLoad, setMaxLoad] = useState(h.max_agent_load ?? 10)
  const [presence, setPresence] = useState(h.presence_window_seconds ?? 300)
  const [bridging, setBridging] = useState(h.bridging_reply ?? '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition'

  const save = async () => {
    setMsg(null)
    const ml = parseInt(maxLoad, 10)
    const pw = parseInt(presence, 10)
    if (!Number.isFinite(ml) || ml < 1 || ml > 100) return setMsg({ type: 'error', text: 'Max load must be between 1 and 100.' })
    if (!Number.isFinite(pw) || pw < 30 || pw > 3600) return setMsg({ type: 'error', text: 'Presence window must be 30–3600 seconds.' })
    if (!bridging.trim()) return setMsg({ type: 'error', text: 'The handoff message cannot be empty.' })

    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ handoff: { max_agent_load: ml, presence_window_seconds: pw, bridging_reply: bridging.trim() } }),
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
    <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
      <PanelHeader
        icon={Sliders}
        title="Handoff & assignment"
        desc="How conversations auto-assign, and what customers hear when a chat is escalated."
      />

      <div className="flex items-center gap-2 text-[11px] font-medium text-brand-700 bg-brand-50 rounded-lg px-3 py-2 mb-5">
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
          <p className="text-[11px] text-gray-400 mt-1.5">Agents at or above this are skipped for auto-assignment.</p>
        </div>
        <div>
          <label className={labelCls}>Presence window</label>
          <div className="relative">
            <input className={`${inputCls} pr-16`} type="number" min="30" max="3600" value={presence} onChange={e => setPresence(e.target.value)} />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">seconds</span>
          </div>
          <p className="text-[11px] text-gray-400 mt-1.5">How recently an agent must've been active to count as present. 300 = 5 min.</p>
        </div>
      </div>

      <div className="mb-5">
        <label className={labelCls}>Default handoff message</label>
        <textarea className={`${inputCls} resize-none`} rows={3} value={bridging} onChange={e => setBridging(e.target.value)} />
        <p className="text-[11px] text-gray-400 mt-1.5">Sent to the customer on escalation. Abuse and frustration cases use their own tuned messages.</p>
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
  const [hours, setHours] = useState(b.hours ?? '')
  const [phone, setPhone] = useState(b.phone ?? '')
  const [whatsapp, setWhatsapp] = useState(b.whatsapp ?? '')
  const [email, setEmail] = useState(b.email ?? '')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition'

  const save = async () => {
    setMsg(null)
    if (!storeName.trim()) return setMsg({ type: 'error', text: 'Store name is required.' })
    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/settings`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ business: {
          store_name: storeName.trim(), hours: hours.trim(),
          phone: phone.trim(), whatsapp: whatsapp.trim(), email: email.trim(),
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
      <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
        <PanelHeader icon={Store} title="Business info"
          desc="Details your assistant uses when customers ask about hours or how to reach you. Shop Zetu is online-only." />
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
          <p className="text-[11px] text-gray-500 mt-0.5">
            {loading ? 'Checking…' : `${hooks?.length || 0} topic${hooks?.length === 1 ? '' : 's'} registered with Shopify.`}
          </p>
        </div>
        <button onClick={register} disabled={registering}
          className="text-xs font-semibold px-3 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 disabled:opacity-50 shrink-0">
          {registering ? 'Registering…' : 'Register webhooks'}
        </button>
      </div>
      {msg && <p className={`text-[11px] mt-2 font-medium ${msg.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
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
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition'

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
    <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
      <PanelHeader icon={Truck} title="Delivery & orders"
        desc="Delivery zones and rates your assistant quotes when customers ask about shipping." />

      <div className="flex items-center gap-2 text-[11px] font-medium text-brand-700 bg-brand-50 rounded-lg px-3 py-2 mb-5">
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
        <p className="text-[11px] text-gray-400 mt-1.5">Anything zones don't cover — free-delivery thresholds, courier info, timelines.</p>
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

function NotificationsPanel({ settings, setSettings }) {
  const n = settings?.notifications || {}
  const [enabled, setEnabled] = useState(n.discord_enabled ?? true)
  const [url, setUrl] = useState(n.discord_webhook_url ?? '')
  const [severity, setSeverity] = useState(n.discord_min_severity ?? 'warning')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState(null)

  const labelCls = 'block text-xs font-semibold text-gray-700 mb-1.5'
  const inputCls = 'w-full px-3 py-2.5 rounded-xl border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition'

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
    <div className="bg-white rounded-2xl border border-gray-200 p-5 sm:p-6">
      <PanelHeader icon={Bell} title="Notifications" desc="Where operational alerts go when syncs fail or run long." />

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
          <p className="text-[11px] text-gray-400 mt-1.5">Leave blank to use the server's env-configured webhook, if any.</p>
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
        <p className="text-[11px] text-gray-400">In-app notifications (assignments, escalations) are always on and can't be disabled here.</p>
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
    <span className={clsx('inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-1 rounded-full shrink-0', cls)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', dot)} />
      {warn ? 'Needs attention' : ok ? 'Connected' : 'Not connected'}
    </span>
  )
}

function Row({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-xs gap-3">
      <span className="text-gray-500 shrink-0">{label}</span>
      <span className={clsx('text-gray-800 font-medium truncate text-right', mono && 'font-mono text-[11px]')}>{value}</span>
    </div>
  )
}

function IntegrationCard({ icon: Icon, name, ok, warn, children }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-4 sm:p-5">
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

function IntegrationsPanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API_BASE}/settings/integrations`, { headers: authHeaders() })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error || 'Failed to load')
      setData(d.integrations)
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

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
          <IntegrationCard icon={Instagram} name="Meta · Instagram" ok={m?.connected}>
            {m?.connected ? (
              <>
                {m.page_name && <Row label="Page" value={m.page_name} />}
                {m.ig_username && <Row label="Instagram" value={`@${m.ig_username}`} />}
                {m.source === 'env' && <Row label="Source" value="Legacy env token" />}
                {m.token_expires_at && <Row label="Token expires" value={fmtDate(m.token_expires_at)} />}
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
                {s.recent_failed && <p className="text-[11px] text-amber-600 mt-1.5">The most recent sync job failed — check Logs.</p>}
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
    <div className="bg-white rounded-2xl border border-gray-200 p-10 text-center">
      <div className="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center text-gray-400 mx-auto mb-3">
        <Icon size={22} />
      </div>
      <p className="text-sm font-semibold text-gray-700">{tab?.label}</p>
      <p className="text-xs text-gray-400 mt-1">This section is coming soon.</p>
    </div>
  )
}