import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'

/**
 * Fires when a link the assistant sent turns into an order.
 *
 * Triggered off the existing notification poll rather than a new endpoint — a
 * `conversion_attributed` notification arriving IS the event. That keeps the
 * backend unaware of the animation and means the permanent record and the
 * celebration are the same fact, so one cannot happen without the other.
 *
 * Deliberately short and non-blocking: it sits above everything, ignores
 * pointer events entirely, and clears itself. A sale is worth marking; it is
 * not worth interrupting someone mid-reply to a customer.
 */

// Brand lime through to warm, so it reads as ours rather than generic party
// confetti.
const COLOURS = ['#99e600', '#c9ff5c', '#81c200', '#ffd166', '#f4978e', '#ffffff']

function Piece({ i }) {
  // Spread across the width, with per-piece drift, spin and delay so the fall
  // doesn't read as a single sheet of identical dots.
  const left = (i * 37) % 100
  const drift = ((i * 53) % 40) - 20
  const delay = ((i * 71) % 900) / 1000
  const duration = 2.2 + (((i * 29) % 120) / 100)
  const size = 6 + ((i * 13) % 6)
  const colour = COLOURS[i % COLOURS.length]
  const round = i % 3 === 0

  return (
    <span
      className="confetti-piece"
      style={{
        left: `${left}%`,
        width: size,
        height: round ? size : size * 0.4,
        background: colour,
        borderRadius: round ? '50%' : 2,
        animationDelay: `${delay}s`,
        animationDuration: `${duration}s`,
        '--drift': `${drift}vw`,
      }}
    />
  )
}

export default function Celebration({ trigger, amount }) {
  const [runId, setRunId] = useState(null)

  useEffect(() => {
    if (!trigger) return
    setRunId(trigger)
    const t = setTimeout(() => setRunId(null), 4200)
    return () => clearTimeout(t)
  }, [trigger])

  if (!runId) return null

  return (
    // pointer-events-none throughout: an agent mid-conversation must never have
    // to dismiss this or wait for it.
    <div className="fixed inset-0 z-[60] pointer-events-none overflow-hidden" aria-hidden="true">
      {Array.from({ length: 60 }, (_, i) => <Piece key={`${runId}-${i}`} i={i} />)}

      <div className="absolute inset-x-0 top-24 flex justify-center px-4">
        <div className="celebrate-banner flex items-center gap-2.5 rounded-2xl px-5 py-3 shadow-2xl"
             style={{ background: 'rgba(18,18,20,0.94)', border: '1px solid rgba(153, 230, 0,0.35)' }}>
          <Sparkles size={18} style={{ color: '#99e600' }} className="shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-bold" style={{ color: '#fff' }}>
              The assistant made a sale
            </p>
            {amount && (
              <p className="text-xs tabular-nums" style={{ color: '#99e600' }}>{amount}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
