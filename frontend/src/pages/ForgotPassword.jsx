import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Mail, ArrowLeft, MailCheck } from 'lucide-react'
import bgImage from '../images/bg9.png'

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

  const inputStyle = { background: 'transparent', borderColor: 'rgba(255,255,255,0.15)', color: 'white', WebkitTextFillColor: 'rgba(255,255,255,0.9)', caretColor: 'white', fontFamily: 'Quicksand, sans-serif', fontWeight: 400, letterSpacing: '0.03em' }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative bg-black">
      <div className="absolute inset-0" style={{ backgroundImage: `url(${bgImage})`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundRepeat: 'no-repeat' }}>
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-black/40 to-black" />
      </div>

      <div className="relative z-10 w-full max-w-sm">
        <div className="backdrop-blur-sm rounded-2xl p-8 shadow-2xl" style={{ background: 'rgba(255,255,255,0.08)', border: '0.5px solid rgba(255,255,255,0.08)' }}>
          {sent ? (
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-11 h-11 bg-brand-600 rounded-xl mb-4">
                <MailCheck size={20} className="text-white" />
              </div>
              <h1 className="text-xl font-bold text-white mb-2">Check your email</h1>
              <p className="text-xs text-white/50 leading-relaxed mb-6" style={{ letterSpacing: '0.03em' }}>
                If an account exists for that email, we've sent a link to reset your password. It expires in 1 hour.
              </p>
              <button onClick={() => navigate('/login')} className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-2.5 rounded-lg transition-colors text-sm">
                Back to sign in
              </button>
            </div>
          ) : (
            <>
              <div className="mb-8 text-center">
                <div className="inline-flex items-center justify-center w-11 h-11 bg-brand-600 rounded-xl mb-4">
                  <Mail size={20} className="text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white mb-1" style={{ letterSpacing: '0.02em' }}>Forgot password?</h1>
                <p className="text-xs text-white/50" style={{ letterSpacing: '0.03em', lineHeight: '1.5' }}>Enter your email and we'll send a reset link</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-white/60 mb-1.5" style={{ letterSpacing: '0.03em' }}>Email Address</label>
                  <div className="relative">
                    <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 z-10" />
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@company.com" autoComplete="email" required disabled={isLoading}
                      className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm placeholder-white/25 focus:outline-none transition-all border" style={inputStyle} />
                  </div>
                </div>
                <button type="submit" disabled={isLoading} className="w-full mt-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm" style={{ letterSpacing: '0.03em' }}>
                  {isLoading ? (<><Loader2 size={15} className="animate-spin" /> Sending...</>) : 'Send reset link'}
                </button>
              </form>

              <div className="mt-6 pt-5 border-t border-white/10 text-center">
                <button onClick={() => navigate('/login')} className="text-xs text-white/50 hover:text-white/80 transition-colors inline-flex items-center gap-1.5">
                  <ArrowLeft size={12} /> Back to sign in
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}