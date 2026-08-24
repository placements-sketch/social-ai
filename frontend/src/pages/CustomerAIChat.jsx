import { useState, useRef, useEffect } from 'react'
import { Sparkles, Send, Loader2, User, Bot, X, MessageSquareText } from 'lucide-react'
import clsx from 'clsx'
import { askCustomerAI } from '../api/customers'

// These are the first thing anyone clicks, so they are effectively the demo.
// "Revenue by city this month" ran through aggregate_orders, which had no
// financial_status filter and returned figures 20% high; that is fixed in
// ai_query.py, and the wording here now says which orders are counted so the
// answer is not mistaken for Shopify Analytics, which nets off returns.
const SUGGESTIONS = [
  'Top 10 spenders in Nairobi, all time',
  'How many VIP customers do we have?',
  'Which customers are at risk of churning?',
  'Revenue by city this month (paid orders)',
]

function DataTable({ rows }) {
  if (!rows || rows.length === 0) return null
  const preferred = ['name', 'city', 'segment', 'revenue', 'orders', 'total_spent', 'total_orders', 'aov', 'email', 'last_order_date']
  const keys = Array.from(new Set([...preferred.filter(k => k in rows[0]), ...Object.keys(rows[0])]))
  const fmt = (k, v) => {
    if (v == null) return '—'
    if (['revenue', 'total_spent', 'aov'].includes(k) && typeof v === 'number') return `KES ${v.toLocaleString()}`
    return String(v)
  }
  const label = (k) => k.replace(/_/g, ' ')
  return (
    <div>
    <div className="mt-2.5 overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-xs min-w-[320px]">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            {keys.map(k => (
              <th key={k} className="text-left px-2.5 py-1.5 text-[11px] font-bold text-gray-600 uppercase tracking-wide whitespace-nowrap">{label(k)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-gray-100 last:border-0">
              {keys.map(k => (
                <td key={k} className={clsx('px-2.5 py-1.5 whitespace-nowrap',
                  ['revenue', 'total_spent', 'aov', 'orders', 'total_orders'].includes(k) ? 'text-right tabular-nums font-medium text-gray-900' : 'text-gray-700')}>
                  {fmt(k, r[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {/* The prose above the table is generated; this line is not. Whatever the
        model says, the figures came from paid orders and include VAT. */}
    <p className="text-[11px] text-gray-400 mt-1.5">
      Paid orders only · KES, VAT included · returns not deducted
    </p>
    </div>
  )
}

export default function CustomerAIChat() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (open) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading, open])

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('chat-panel-toggle', { detail: { open } }))
    return () => window.dispatchEvent(new CustomEvent('chat-panel-toggle', { detail: { open: false } }))
  }, [open])

  const send = async (text) => {
    const q = (text ?? input).trim()
    if (!q || loading) return
    setError(null)
    setInput('')
    const newMessages = [...messages, { role: 'user', content: q }]
    setMessages(newMessages)
    setLoading(true)

    const history = newMessages
      .filter(m => m.content)
      .map(m => ({ role: m.role, content: m.content }))
      .slice(-6)

    try {
      const res = await askCustomerAI(q, history.slice(0, -1))
      setMessages(prev => [...prev, { role: 'assistant', content: res.answer || 'No answer returned.', rows: res.rows || [] }])
    } catch (err) {
      setError(err.message || 'Something went wrong.')
      setMessages(prev => [...prev, { role: 'assistant', content: `Sorry — I couldn't answer that. ${err.message || ''}`.trim(), rows: [], isError: true }])
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <>
      {/* Floating panel */}
      {open && (
        <div
          className="fixed z-50 flex flex-col rounded-2xl border border-gray-200 overflow-hidden animate-[fadeInUp_.18s_ease-out]"
          /* var(--surface), not bg-white. `.dark .bg-white` would have handled
             the panel, but the header below used a GRADIENT ending in white and
             no class-remap reaches a gradient stop — which is why the header
             stayed a white band on a dark page. */
          style={{
            background: 'var(--surface)',
            bottom: 152, right: 24,
            width: 'min(520px, calc(100vw - 32px))',
            height: 'min(720px, calc(100vh - 184px))',
            boxShadow: '0 12px 48px -12px rgba(16,24,40,0.28), 0 4px 12px -4px rgba(16,24,40,0.12)',
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between gap-2.5 px-4 py-3 border-b border-gray-100"
               style={{ background: 'var(--surface-2)' }}>
            <div className="flex items-center gap-2.5">
              <span className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center shadow-sm">
                <Sparkles size={16} className="text-black" />
              </span>
              <div>
                <p className="text-sm font-bold text-gray-900 leading-none">Ask about your customers</p>
                <p className="text-[12px] text-gray-500 mt-0.5">Spend, segments, cities & more</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="w-7 h-7 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-700 transition-colors">
              <X size={16} />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center">
                <span className="w-12 h-12 rounded-2xl bg-brand-50 flex items-center justify-center mb-3">
                  <Bot size={22} className="text-brand-500" />
                </span>
                <p className="text-sm font-semibold text-gray-700">Ask me anything about your customers</p>
                <p className="text-xs text-gray-400 mt-1 mb-4 max-w-xs">I can filter, rank, and aggregate — spend, segments, cities, order history.</p>
                <div className="flex flex-col gap-2 w-full">
                  {SUGGESTIONS.map(s => (
                    <button key={s} onClick={() => send(s)}
                      className="text-left text-xs text-gray-600 bg-gray-50 hover:bg-brand-50 hover:text-brand-700 border border-gray-200 rounded-lg px-3 py-2 transition-colors">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={clsx('flex gap-2.5', m.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
                {/* neutral-700, not gray-900.
                    Two problems, one cause. gray-900 is #111827 against a panel
                    of #141414 — a contrast ratio of 1.04:1, so in dark mode the
                    bubble was not dim, it was invisible: white text floating on
                    the panel with no shape behind it. neutral-700 is #404040,
                    1.78:1, and needs no dark override to get there.

                    It is also the right colour by the convention this product
                    already has. Messages paints msg.from === 'ai' gray-900 and
                    msg.from === 'human' neutral-700. The person typing here IS
                    the human agent, so gray-900 was the contradiction — navy
                    means AI everywhere else and it was being worn by the human. */}
                <span className={clsx('w-7 h-7 rounded-lg flex items-center justify-center shrink-0',
                  m.role === 'user' ? 'bg-neutral-700' : 'bg-brand-100')}>
                  {m.role === 'user' ? <User size={14} className="text-white" /> : <Bot size={14} className="text-brand-600" />}
                </span>
                <div className={clsx('min-w-0 max-w-[85%]', m.role === 'user' && 'flex flex-col items-end')}>
                  <div className={clsx('rounded-2xl px-3.5 py-2 text-sm',
                    m.role === 'user' ? 'bg-neutral-700 text-white' : m.isError ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-800')}>
                    <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
                  </div>
                  {m.role === 'assistant' && m.rows?.length > 0 && <DataTable rows={m.rows} />}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-2.5">
                <span className="w-7 h-7 rounded-lg bg-brand-100 flex items-center justify-center shrink-0">
                  <Bot size={14} className="text-brand-600" />
                </span>
                <div className="bg-gray-100 rounded-2xl px-3.5 py-2.5 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-gray-400" />
                  <span className="text-xs text-gray-500">Thinking…</span>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-gray-100 p-3">
            {error && <p className="text-xs text-red-600 mb-2 px-1">{error}</p>}
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                placeholder="Ask about spenders, segments, cities…"
                className="flex-1 resize-none text-sm border border-gray-200 rounded-xl px-3 py-2 focus:outline-none focus:ring-1 focus:ring-brand-200 focus:border-brand-300 max-h-24"
                style={{ background: 'var(--surface)', color: 'var(--text)' }}
                disabled={loading}
              />
              <button onClick={() => send()} disabled={loading || !input.trim()}
                className="w-9 h-9 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors shrink-0">
                <Send size={15} className="text-black" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating action button */}
      <button
        onClick={() => setOpen(o => !o)}
        className="fixed z-50 flex items-center justify-center rounded-full shadow-lg transition-all hover:scale-105 active:scale-95"
        style={{
          // Sits ABOVE the "Ask the docs" pill, which is fixed at bottom-5
          // right-5. Both were in the same corner, so this covered it and the
          // pagination beneath — two assistants fighting for one square inch.
          bottom: 72, right: 24, width: 56, height: 56,
          background: 'linear-gradient(135deg, #c9ff5c, #99e600)',
          // Was rgba(255,89,0,.5) - an ORANGE glow under a green button, left
          // behind when the palette changed. Matched to #99e600.
          boxShadow: '0 8px 24px -6px rgba(153,230,0,0.45)',
        }}
        aria-label={open ? 'Close assistant' : 'Open customer assistant'}
      >
        {open ? <X size={22} className="text-black" /> : <MessageSquareText size={22} className="text-black" />}
      </button>

      <style>{`@keyframes fadeInUp { from { opacity:0; transform:translateY(12px) } to { opacity:1; transform:translateY(0) } }`}</style>
    </>
  )
}
