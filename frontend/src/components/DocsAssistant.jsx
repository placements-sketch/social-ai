import { useState, useRef, useEffect } from 'react'
import { BookOpen, X, Send, Loader2, RotateCcw } from 'lucide-react'
import clsx from 'clsx'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

/*
 * Docs assistant — "how does this work?", answered from the written explainers.
 *
 * A panel rather than a page, because the question always arrives while you are
 * looking at the thing you are confused about. Sending someone to /help means
 * leaving the screen that prompted the question, and they lose their place.
 *
 * Deliberately NOT the same thing as the Customer Profiling assistant: that one
 * answers questions about data and is admin-only. This one answers questions
 * about the system and is open to everyone — agents have the most questions and
 * the least context.
 */

// Starter questions, so the empty state shows what this is for. A blank box
// with a cursor is the worst possible onboarding for something whose whole
// value is that you didn't know what to ask.
// Written the way an agent would actually ask, not the way a developer would.
const SUGGESTIONS = [
  'What does "Unclaimed" mean?',
  "Why can't I see some conversations?",
  'When does the AI hand a chat over to me?',
  'What happens when I mark something resolved?',
]

function authHeaders() {
  const token = localStorage.getItem('authToken')
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

// The model replies in light markdown. Rather than pull in a parser for four
// constructs, handle exactly those four — headings would be over-formatting in
// a panel this narrow anyway.
function Rich({ text }) {
  const lines = String(text || '').split('\n')
  return lines.map((line, i) => {
    const bullet = /^\s*[-*]\s+/.test(line)
    const content = bullet ? line.replace(/^\s*[-*]\s+/, '') : line
    if (!content.trim()) return <div key={i} className="h-2" />
    // **bold** and `code`, split in one pass so they can't nest wrongly.
    const parts = content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    const rendered = parts.map((p, j) => {
      if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={j} className="font-bold text-gray-900">{p.slice(2, -2)}</strong>
      if (/^`[^`]+`$/.test(p)) return <code key={j} className="px-1 py-0.5 rounded bg-gray-100 text-[12px] font-mono text-gray-700">{p.slice(1, -1)}</code>
      return p
    })
    return (
      <p key={i} className={clsx('text-xs leading-relaxed text-gray-600', bullet && 'pl-3 relative')}>
        {bullet && <span className="absolute left-0 text-gray-300">•</span>}
        {rendered}
      </p>
    )
  })
}

export default function DocsAssistant() {
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState([])      // [{role, content}]
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, busy])
  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  // Escape closes it. A panel that traps you is worse than no panel.
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const ask = async (question) => {
    const q = (question ?? input).trim()
    if (!q || busy) return
    setError('')
    setInput('')
    // History is sent BEFORE this turn is appended, so the server sees prior
    // turns only — including the new question twice would make it read as an
    // echo and confuse follow-ups.
    const history = turns.slice(-8)
    setTurns(t => [...t, { role: 'user', content: q }])
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/docs/ask`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ question: q, history }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.error || 'Could not reach the assistant.')
      setTurns(t => [...t, { role: 'assistant', content: data.answer }])
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  return (
    <>
      {/* Floating trigger. Bottom-right, above the content but below modals. */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          title="Ask about how the system works"
          className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-gray-900 text-white pl-3.5 pr-4 py-2.5 shadow-lg hover:bg-black transition-colors"
        >
          <BookOpen size={15} className="text-brand-500" />
          <span className="text-xs font-bold">Ask the docs</span>
        </button>
      )}

      {open && (
        <>
          {/* Backdrop only below lg. On a wide screen the panel sits beside the
              page so you can read the thing you're asking about while you ask;
              dimming it would defeat that. */}
          <div
            className="fixed inset-0 z-40 bg-black/30 lg:hidden"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <aside
            role="dialog"
            aria-label="Documentation assistant"
            className="fixed z-40 bg-white shadow-2xl flex flex-col inset-x-0 bottom-0 top-16 rounded-t-2xl lg:inset-y-0 lg:right-0 lg:left-auto lg:top-0 lg:w-[26rem] lg:rounded-none border-l border-gray-200"
          >
            <header className="flex items-center justify-between gap-2 px-4 py-3 border-b border-gray-100 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <BookOpen size={15} className="text-brand-600 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-bold text-gray-900 leading-tight">Ask the docs</p>
                  <p className="text-[11px] text-gray-400 leading-tight">How this system works</p>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {turns.length > 0 && (
                  <button
                    onClick={() => { setTurns([]); setError(''); inputRef.current?.focus() }}
                    title="Start over"
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                  >
                    <RotateCcw size={14} />
                  </button>
                )}
                <button
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                  className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <X size={15} />
                </button>
              </div>
            </header>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {turns.length === 0 && (
                <div>
                  <p className="text-xs text-gray-500 leading-relaxed">
                    Stuck on something? Ask away — what a label means, why a chat
                    moved, what a button does. It knows how this system works and
                    what your role can do.
                  </p>
                  <p className="text-[11px] font-semibold text-gray-400 mt-4 mb-2">Try one of these</p>
                  <div className="space-y-1.5">
                    {SUGGESTIONS.map(s => (
                      <button
                        key={s}
                        onClick={() => ask(s)}
                        className="w-full text-left text-xs text-gray-600 rounded-lg border border-gray-200 px-3 py-2 hover:border-brand-500 hover:text-gray-900 transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                  {/* Said up front rather than discovered by asking. This one
                      cannot see live data, and the moment someone asks it for
                      a revenue figure they should already know that. */}
                  <p className="text-[11px] text-gray-400 mt-4 leading-relaxed">
                    It explains how things work. For real sales or customer
                    numbers, check the Dashboard or Analytics page.
                  </p>
                </div>
              )}

              {turns.map((t, i) => (
                t.role === 'user' ? (
                  <div key={i} className="flex justify-end">
                    <p className="max-w-[85%] rounded-2xl rounded-tr-sm bg-gray-900 text-white text-xs px-3 py-2 leading-relaxed">
                      {t.content}
                    </p>
                  </div>
                ) : (
                  <div key={i} className="space-y-1.5">
                    <Rich text={t.content} />
                  </div>
                )
              ))}

              {busy && (
                <div className="flex items-center gap-2 text-gray-400">
                  <Loader2 size={13} className="animate-spin" />
                  <span className="text-xs">Reading the docs…</span>
                </div>
              )}

              {error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                  <p className="text-xs text-red-700 leading-relaxed">{error}</p>
                </div>
              )}
              <div ref={endRef} />
            </div>

            <form
              onSubmit={(e) => { e.preventDefault(); ask() }}
              className="p-3 border-t border-gray-100 shrink-0 flex items-end gap-2"
            >
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  // Enter sends, Shift+Enter breaks the line — the convention
                  // everywhere else people type questions.
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() }
                }}
                placeholder="Ask a question…"
                className="flex-1 resize-none rounded-xl border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:outline-none focus:border-brand-500 max-h-28"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="shrink-0 p-2.5 rounded-xl bg-brand-500 text-black hover:bg-brand-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                aria-label="Send"
              >
                <Send size={14} />
              </button>
            </form>
          </aside>
        </>
      )}
    </>
  )
}
