import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Lock, Eye, EyeOff, CheckCircle2, AlertCircle } from 'lucide-react'
import bgImage from '../images/bg9.png'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const navigate = useNavigate()

  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (newPw.length < 8) return setError('Password must be at least 8 characters.')
    if (newPw !== confirmPw) return setError('Passwords do not match.')
    setIsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPw }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to reset password')
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  const inputStyle = { background: 'transparent', borderColor: 'rgba(255,255,255,0.15)', color: 'white', WebkitTextFillColor: 'rgba(255,255,255,0.9)', caretColor: 'white', fontFamily: 'Quicksand, sans-serif', fontWeight: 400, letterSpacing: '0.03em' }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative bg-black">
      <div className="absolute inset-0" style={{ backgroundImage: `url(${bgImage})`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundRepeat: 'no-repeat' }}>
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-black/40 to-black" />
      </div>

      <div className="relative z-10 w-full max-w-sm">
        <div className="backdrop-blur-sm rounded-2xl p-8 shadow-2xl" style={{ background: 'rgba(255,255,255,0.08)', border: '0.5px solid rgba(255,255,255,0.08)' }}>
          {!token ? (
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-11 h-11 bg-red-500/20 rounded-xl mb-4"><AlertCircle size={20} className="text-red-300" /></div>
              <h1 className="text-xl font-bold text-white mb-2">Invalid link</h1>
              <p className="text-xs text-white/50 leading-relaxed mb-6">This reset link is missing or malformed. Request a new one.</p>
              <button onClick={() => navigate('/forgot-password')} className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-2.5 rounded-lg transition-colors text-sm">Request a new link</button>
            </div>
          ) : done ? (
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-11 h-11 bg-brand-600 rounded-xl mb-4"><CheckCircle2 size={20} className="text-white" /></div>
              <h1 className="text-xl font-bold text-white mb-2">Password reset</h1>
              <p className="text-xs text-white/50 leading-relaxed mb-6">Your password has been updated. You can now sign in with your new password.</p>
              <button onClick={() => navigate('/login')} className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-2.5 rounded-lg transition-colors text-sm">Go to sign in</button>
            </div>
          ) : (
            <>
              <div className="mb-8 text-center">
                <div className="inline-flex items-center justify-center w-11 h-11 bg-brand-600 rounded-xl mb-4"><Lock size={20} className="text-white" /></div>
                <h1 className="text-2xl font-bold text-white mb-1" style={{ letterSpacing: '0.02em' }}>Set a new password</h1>
                <p className="text-xs text-white/50" style={{ letterSpacing: '0.03em' }}>Choose a strong password you'll remember</p>
              </div>

              {error && (
                <div className="mb-5 p-3 bg-red-500/10 border border-red-500/30 rounded-lg"><p className="text-xs text-red-300 font-medium">{error}</p></div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-white/60 mb-1.5" style={{ letterSpacing: '0.03em' }}>New password</label>
                  <div className="relative">
                    <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 z-10" />
                    <input type={showPw ? 'text' : 'password'} value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="••••••••" autoComplete="new-password" required disabled={isLoading}
                      className="w-full pl-9 pr-12 py-2.5 rounded-lg text-sm placeholder-white/25 focus:outline-none transition-all border" style={inputStyle} />
                    <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70 transition-colors z-10">
                      {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-white/60 mb-1.5" style={{ letterSpacing: '0.03em' }}>Confirm new password</label>
                  <div className="relative">
                    <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 z-10" />
                    <input type={showPw ? 'text' : 'password'} value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} placeholder="••••••••" autoComplete="new-password" required disabled={isLoading}
                      className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm placeholder-white/25 focus:outline-none transition-all border" style={inputStyle} />
                  </div>
                </div>
                <button type="submit" disabled={isLoading} className="w-full mt-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm" style={{ letterSpacing: '0.03em' }}>
                  {isLoading ? (<><Loader2 size={15} className="animate-spin" /> Resetting...</>) : 'Reset password'}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}