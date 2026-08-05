import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Loader2, Mail, Lock, Eye, EyeOff, AlertCircle, ArrowRight } from 'lucide-react'
import bgImage from '../images/bg9.png'
import szLogo from '../images/sz.png'

/*
 * Sign in.
 *
 * The previous version was a small translucent card floated in the middle of a
 * full-bleed photo, with a padlock glyph standing in for the logo and every
 * input carrying twenty lines of inline style — the same twenty lines, twice.
 * Three things were wrong with it beyond taste:
 *
 *   - It used a generic padlock where the product has an actual mark, and
 *     called itself "Social AI" when the brand is Shop Zetu.
 *   - `backdrop-blur-sm` is 4px. The rest of the app runs 28px, so the one
 *     screen every user sees first didn't look like the product behind it.
 *   - The error was a coloured div nothing pointed at: not announced to screen
 *     readers, not linked to the fields it described.
 *
 * Now a split: the photo earns its place on the left carrying the brand and a
 * line about what this is, the form sits on its own calm surface on the right.
 * Below `lg` the panel is dropped entirely rather than stacked — on a phone a
 * decorative half-screen just pushes the form below the fold.
 */
export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const { login, loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const emailRef = useRef(null)
  const googleRef = useRef(null)
  const [googleReady, setGoogleReady] = useState(false)

  // Land in the first field. On a screen whose only purpose is a two-field
  // form, making people click first is friction for nothing.
  useEffect(() => { emailRef.current?.focus() }, [])

  // Google sign-in, rendered only when the server says it is configured.
  //
  // Asking the server rather than reading a build-time env var: the client id
  // lives in Render, and a frontend built before it was set would show a dead
  // button forever. This way the button appears exactly when it can work, and
  // the password form below is untouched either way — Google is a shortcut, not
  // a dependency, so nothing here may ever block signing in the normal way.
  // The context recreates loginWithGoogle on every render, so it cannot be an
  // effect dependency — the effect would re-run forever, appending a script tag
  // and a new Google button each time. A ref holds the current one and the
  // effect runs exactly once.
  const onCredential = useRef(null)
  onCredential.current = async ({ credential }) => {
    setError('')
    setIsLoading(true)
    const { ok, error: msg } = await loginWithGoogle(credential)
    if (ok) navigate('/dashboard')
    else setError(msg || 'Google sign-in failed.')
    setIsLoading(false)
  }

  useEffect(() => {
    let cancelled = false

    const start = async () => {
      let clientId = ''
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/auth/google/config`)
        const cfg = await res.json()
        if (!cfg.enabled || !cfg.client_id) return
        clientId = cfg.client_id
      } catch { return }          // offline or old backend → password form only
      if (cancelled) return

      const init = () => {
        if (cancelled || !window.google?.accounts?.id || !googleRef.current) return
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (resp) => onCredential.current?.(resp),
        })
        window.google.accounts.id.renderButton(googleRef.current, {
          theme: 'filled_black', size: 'large', width: 320,
          text: 'signin_with', shape: 'pill', logo_alignment: 'center',
        })
        setGoogleReady(true)
      }

      if (window.google?.accounts?.id) return init()
      // One script tag, reused if the user navigates back to this page.
      let s = document.getElementById('google-gsi')
      if (!s) {
        s = document.createElement('script')
        s.src = 'https://accounts.google.com/gsi/client'
        s.async = true
        s.defer = true
        s.id = 'google-gsi'
        document.head.appendChild(s)
      }
      s.addEventListener('load', init, { once: true })
    }

    start()
    return () => { cancelled = true }
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)
    const success = await login(email, password)
    if (success) {
      navigate('/dashboard')
    } else {
      setError('That email and password combination did not match an account.')
    }
    setIsLoading(false)
  }

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
        {/* Two overlays, not one: a wash for text contrast, and a lime bloom
            that ties this screen to the accent used everywhere inside. */}
        <div className="absolute inset-0 bg-gradient-to-tr from-black via-black/70 to-black/30" />
        <div
          className="absolute inset-0"
          style={{
            background:
              'radial-gradient(38rem 38rem at 15% 95%, rgba(153, 230, 0,0.16), transparent 60%)',
          }}
        />

        <div className="relative flex items-center gap-3">
          <img src={szLogo} alt="" aria-hidden="true" className="w-9 h-9" />
          <div>
            <p className="text-sm font-bold leading-tight tracking-tight">Shop Zetu</p>
            <p className="text-[11px] text-white/50 mt-0.5">Social AI</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <h2 className="text-3xl font-bold leading-[1.15] tracking-tight">
            Every customer conversation,
            <span className="text-brand-500"> in one place.</span>
          </h2>
          <p className="text-sm text-white/60 mt-4 leading-relaxed">
            Instagram, WhatsApp, Facebook and TikTok — DMs and comments — answered
            by the assistant or picked up by your team, without switching apps.
          </p>
        </div>

        <p className="relative text-[11px] text-white/30">
          © {new Date().getFullYear()} Shop Zetu
        </p>
      </aside>

      {/* ── Form ────────────────────────────────────────────────────────── */}
      <main className="flex items-center justify-center p-6 sm:p-10 min-h-screen lg:min-h-0">
        <div className="w-full max-w-sm">
          {/* The logo repeats here only where the panel is hidden, so small
              screens still get branding without duplicating it on desktop. */}
          <div className="flex items-center gap-2.5 mb-10 lg:hidden">
            <img src={szLogo} alt="" aria-hidden="true" className="w-8 h-8" />
            <div>
              <p className="text-sm font-bold leading-tight tracking-tight">Shop Zetu</p>
              <p className="text-[11px] text-white/50 mt-0.5">Social AI</p>
            </div>
          </div>

          <h1 className="text-2xl font-bold tracking-tight">Sign in</h1>
          <p className="text-sm text-white/50 mt-1.5">
            Use the account your administrator set up for you.
          </p>

          {/* aria-live so the failure is spoken, not just coloured. */}
          <div aria-live="polite">
            {error && (
              <div
                id="login-error"
                className="mt-6 flex items-start gap-2.5 rounded-xl border border-red-500/25 bg-red-500/10 px-3.5 py-3"
              >
                <AlertCircle size={15} className="text-red-400 shrink-0 mt-px" />
                <p className="text-xs text-red-200 leading-relaxed">{error}</p>
              </div>
            )}
          </div>

          {/* Google sits ABOVE the form because it is the faster path for the
              people who have it, and below-the-form placement reads as a
              fallback. It renders into a div Google owns — its button is
              iframe-based and cannot be restyled, so the divider carries the
              visual join instead.

              Nothing here gates the password form: if Google is unconfigured,
              blocked, or slow, this whole block is simply absent. */}
          {/* The target div is always mounted — Google's renderButton needs a
              real node to draw into, so gating it on `googleReady` would mean
              the node never exists when we ask, and the button never appears.
              Visibility is what's conditional, not existence. */}
          <div className={googleReady ? 'mt-6' : 'hidden'}>
            <div ref={googleRef} className="flex justify-center [color-scheme:light]" />
            <div className="flex items-center gap-3 mt-6">
              <span className="h-px flex-1 bg-white/[0.07]" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-white/25">
                or use your password
              </span>
              <span className="h-px flex-1 bg-white/[0.07]" />
            </div>
          </div>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="email" className="block text-xs font-semibold text-white/60 mb-1.5">
                Email address
              </label>
              <div className="relative">
                <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none" />
                <input
                  id="email"
                  ref={emailRef}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@shopzetu.com"
                  autoComplete="email"
                  className={field}
                  aria-invalid={Boolean(error)}
                  aria-describedby={error ? 'login-error' : undefined}
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            <div>
              <div className="flex items-baseline justify-between mb-1.5">
                <label htmlFor="password" className="block text-xs font-semibold text-white/60">
                  Password
                </label>
                {/* Beside the field it belongs to, rather than stranded under
                    the submit button where it read as an afterthought. */}
                <button
                  type="button"
                  onClick={() => navigate('/forgot-password')}
                  className="text-[11px] font-semibold text-white/40 hover:text-brand-500 transition-colors"
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative">
                <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/30 pointer-events-none" />
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className={field + ' pr-11'}
                  aria-invalid={Boolean(error)}
                  aria-describedby={error ? 'login-error' : undefined}
                  required
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-md text-white/35 hover:text-white/70 transition-colors"
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || !email || !password}
              className="group w-full mt-2 flex items-center justify-center gap-2 rounded-xl bg-brand-500 py-3 text-sm font-bold text-black transition-all hover:bg-brand-400 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-brand-500"
            >
              {isLoading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </button>
          </form>

          <p className="mt-8 pt-6 border-t border-white/[0.07] text-[11px] text-white/25 text-center">
            Authorised personnel only. Activity on this platform is logged.
          </p>
        </div>
      </main>
    </div>
  )
}
