import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Loader2, Mail, ArrowLeft, MailCheck, ArrowRight } from 'lucide-react'
import bgImage from '../images/bg9.png'
import szLogo from '../images/sz-bg.jpg'

/*
 * Password reset.
 *
 * Ported onto the sign-in layout. It had been left on the previous design — a
 * translucent card floated over a full-bleed photo — which matters beyond
 * consistency: this page is reached FROM sign-in, usually by someone already
 * having a bad minute, and a screen that looks like it belongs to a different
 * product is exactly when people start wondering whether they are being
 * phished.
 *
 * The old card also set its colours through inline styles
 * (`WebkitTextFillColor`, hand-written rgba borders) instead of the theme, so
 * the heading rendered near-black on a dark background — legible in whatever
 * state it was authored in, and not since.
 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsLoading(true)
    try {
      await fetch(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      })
    } catch { /* enumeration-safe: same outcome regardless */ }
    setIsLoading(false)
    setSent(true)
  }

  // Same field styling as sign-in, duplicated rather than shared: these two are
  // the only unauthenticated screens, and promoting it to a shared class would
  // invite the rest of the app to reach for a dark-only input.
  const field =
    'w-full pl-10 pr-4 py-2.5 rounded-xl text-sm bg-white/[0.04] text-white ' +
    'placeholder-white/25 border border-white/10 transition-colors ' +
    'focus:outline-none focus:border-brand-500/60 focus:bg-white/[0.06] ' +
    'disabled:opacity-50'

  return (
    <div className="min-h-screen w-full bg-[#0a0a0a] text-white lg:grid lg:grid-cols-[1.1fr_1fr]">
      {/* ── Brand panel. Hidden on small screens by design. ─────────────── */}
      <aside className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden">
        <img
          src={bgImage}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-tr from-black via-black/70 to-black/30" />
        <div
          className="absolute inset-0"
          style={{
            background:
              'radial-gradient(38rem 38rem at 15% 95%, rgba(153, 230, 0,0.16), transparent 60%)',
          }}
        />

        <div className="relative flex items-center gap-3">
          <img src={szLogo} alt="" aria-hidden="true" className="w-9 h-9 rounded-lg" />
          <div>
            <p className="text-sm font-bold leading-tight tracking-tight">Shop Zetu</p>
            <p className="text-[12px] text-white/50 mt-0.5">Social AI</p>
          </div>
        </div>

        {/* Different copy from sign-in on purpose — the same headline twice
            reads as a page that failed to navigate. */}
        <div className="relative max-w-md">
          <h2 className="text-3xl font-bold leading-[1.15] tracking-tight">
            Locked out?
            <span className="text-brand-500"> It happens.</span>
          </h2>
          <p className="text-sm text-white/60 mt-4 leading-relaxed">
            We'll email you a link to set a new password. It's good for a short
            while, so use it soon after it lands.
          </p>
        </div>

        <p className="relative text-[12px] text-white/30">
          © {new Date().getFullYear()} Shop Zetu
        </p>
      </aside>

      {/* ── Form ────────────────────────────────────────────────────────── */}
      <main className="flex items-center justify-center p-6 sm:p-10 min-h-screen lg:min-h-0">
        <div className="w-full max-w-sm">
          {/* Logo repeats only where the panel is hidden, so small screens keep
              branding without duplicating it on desktop. */}
          <div className="flex items-center gap-2.5 mb-10 lg:hidden">
            <img src={szLogo} alt="" aria-hidden="true" className="w-8 h-8 rounded-lg" />
            <div>
              <p className="text-sm font-bold leading-tight tracking-tight">Shop Zetu</p>
              <p className="text-[11px] text-white/50">Social AI</p>
            </div>
          </div>

          {sent ? (
            <>
              <div className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-brand-500/15 border border-brand-500/30 mb-5">
                <MailCheck size={20} className="text-brand-500" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">Check your email</h1>
              {/* States the address back. A typo is the likeliest reason nothing
                  arrives, and this is the only moment it can be caught before
                  someone spends ten minutes waiting on mail that was never
                  addressed to them. */}
              <p className="text-sm text-white/60 mt-2 leading-relaxed">
                If an account exists for{' '}
                <span className="text-white/90 font-medium break-all">
                  {email.trim().toLowerCase()}
                </span>
                , a reset link is on its way.
              </p>
              <p className="text-[12px] text-white/40 mt-3 leading-relaxed">
                Nothing after a few minutes? Check spam, then try again — the
                address may not match the one on the account.
              </p>

              <button
                onClick={() => navigate('/login')}
                className="w-full mt-7 inline-flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-400 text-black font-semibold py-2.5 rounded-xl transition-colors text-sm"
              >
                Back to sign in <ArrowRight size={15} />
              </button>
              <button
                onClick={() => { setSent(false); setEmail('') }}
                className="w-full mt-3 text-[13px] text-white/50 hover:text-white/80 transition-colors"
              >
                Use a different email
              </button>
            </>
          ) : (
            <>
              <div className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-brand-500/15 border border-brand-500/30 mb-5">
                <Mail size={20} className="text-brand-500" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight">Forgot password?</h1>
              <p className="text-sm text-white/60 mt-2 leading-relaxed">
                Enter the email on your account and we'll send you a reset link.
              </p>

              <form onSubmit={handleSubmit} className="mt-7 space-y-4">
                <div>
                  <label htmlFor="reset-email" className="block text-[12px] font-medium text-white/60 mb-1.5">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail
                      size={15}
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none"
                    />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      autoFocus
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={isLoading}
                      className={field}
                      placeholder="you@shopzetu.com"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading || !email.trim()}
                  className="w-full inline-flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-400 text-black font-semibold py-2.5 rounded-xl transition-colors text-sm disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isLoading ? <Loader2 size={15} className="animate-spin" /> : null}
                  {isLoading ? 'Sending…' : 'Send reset link'}
                </button>
              </form>

              <div className="mt-8 pt-6 border-t border-white/10">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 text-[13px] text-white/50 hover:text-white/80 transition-colors"
                >
                  <ArrowLeft size={14} /> Back to sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
