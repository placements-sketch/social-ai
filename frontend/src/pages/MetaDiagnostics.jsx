import { useState } from 'react'
import clsx from 'clsx'
import { Play, Loader2, CheckCircle2, XCircle } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

function authHeaders() {
  return { Authorization: `Bearer ${localStorage.getItem('authToken')}` }
}

const TESTS = [
  // First in the list on purpose: when Instagram Login calls are failing with
  // "Unsupported request", this is the one that tells you which URL shape it
  // actually accepts, instead of another round of guessing.
  { key: 'iglogin',        label: 'Instagram Login — URL probe',
    desc: 'tries every URL shape against the stored token and reports which one Meta accepts',
    path: '/meta-test/ig-login-probe' },
  { key: 'profile',        label: 'IG profile',        desc: 'username, followers, media count',           path: '/meta-test/profile' },
  { key: 'conversations',  label: 'List conversations', desc: 'recent IG DM threads (Advanced Access gate)', path: '/meta-test/conversations' },
  { key: 'conversation',   label: 'One conversation',   desc: 'messages in a thread — needs an ID',          path: '/meta-test/conversation', needsId: true },
  { key: 'media',          label: 'Recent media',       desc: 'last 10 posts + captions',                    path: '/meta-test/media' },
  { key: 'subscribed',     label: 'Subscribed apps',    desc: 'which app + fields the page is subscribed to', path: '/meta-test/subscribed-apps' },
]

export default function MetaDiagnostics({ embedded = false }) {
  const [results, setResults] = useState({})
  const [loading, setLoading] = useState({})
  const [convId, setConvId] = useState('')

  const run = async (test) => {
    setLoading(l => ({ ...l, [test.key]: true }))
    setResults(r => ({ ...r, [test.key]: null }))
    try {
      let url = `${API_BASE}${test.path}`
      if (test.needsId) url += `?id=${encodeURIComponent(convId.trim())}`
      const res = await fetch(url, { headers: authHeaders() })
      const body = await res.json()
      setResults(r => ({ ...r, [test.key]: { status: res.status, ok: res.ok, body } }))
    } catch (err) {
      setResults(r => ({ ...r, [test.key]: { status: 0, ok: false, body: { error: err.message } } }))
    } finally {
      setLoading(l => ({ ...l, [test.key]: false }))
    }
  }

  return (
    <div className={embedded ? 'space-y-4 w-full' : 'space-y-4 w-full max-w-4xl mx-auto'}>
      {!embedded && (
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Meta Diagnostics</h1>
          <p className="text-sm text-gray-500 mt-0.5">Test the live Graph API endpoints. The token stays server-side.</p>
        </div>
      )}

      {TESTS.map(test => {
        const res = results[test.key]
        const busy = loading[test.key]
        return (
          <div key={test.key} className="card p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-900">{test.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{test.desc}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {test.needsId && (
                  <input
                    value={convId}
                    onChange={e => setConvId(e.target.value)}
                    placeholder="conversation id"
                    className="input text-xs w-40"
                  />
                )}
                <button
                  onClick={() => run(test)}
                  disabled={busy || (test.needsId && !convId.trim())}
                  className="btn-primary flex items-center gap-1.5 text-xs disabled:opacity-50"
                >
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  Run
                </button>
              </div>
            </div>

            {res && (
              <div className="mt-3">
                <div className={clsx('flex items-center gap-1.5 text-xs font-semibold mb-1.5',
                  res.ok ? 'text-green-600' : 'text-red-600')}>
                  {res.ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                  HTTP {res.status}
                </div>
                <pre className="text-[11px] bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto max-h-72 overflow-y-auto whitespace-pre-wrap break-all">
                  {JSON.stringify(res.body, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}