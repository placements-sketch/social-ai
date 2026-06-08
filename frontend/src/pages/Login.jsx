import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Loader2, Mail, Lock, Eye, EyeOff } from 'lucide-react'
import bgImage from '../images/bg9.png'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    const success = await login(email, password)
    if (success) {
      navigate('/dashboard')
    } else {
      setError('Invalid email or password')
    }
    setIsLoading(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative bg-black">
      {/* Background image - full page horizontal cover */}
      <div 
        className="absolute inset-0"
        style={{
          backgroundImage: `url(${bgImage})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
        }}
      >
        {/* Gradient overlay - fades from transparent on left to black on right */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-black/40 to-black"></div>
      </div>

      {/* Content */}
      <div className="relative z-10 w-full max-w-sm">
        {/* Card — glassy */}
        <div
          className="backdrop-blur-sm border border-white/15 rounded-2xl p-8 shadow-2xl"
          style={{ background: 'rgba(255,255,255,0.08)' }}
        >
          {/* Logo & Branding */}
          <div className="mb-8 text-center">
            <div className="inline-flex items-center justify-center w-11 h-11 bg-brand-600 rounded-xl mb-4">
              <Lock size={20} className="text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white mb-1">Social AI</h1>
            <p className="text-xs text-white/50">Customer Support Platform</p>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-5 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
              <p className="text-xs text-red-300 font-medium">{error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email field */}
            <div>
              <label className="block text-xs font-medium text-white/60 mb-1.5">Email Address</label>
              <div className="relative">
                <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 z-10" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@company.com"
                  autoComplete="off"
                  className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm placeholder-white/25 focus:outline-none transition-all border"
                  style={{
                    background: 'transparent',
                    borderColor: 'rgba(255,255,255,0.15)',
                    color: 'white',
                    WebkitBoxShadow: '0 0 0px 1000px transparent inset',
                    WebkitTextFillColor: 'rgba(255,255,255,0.9)',
                    caretColor: 'white',
                    fontFamily: 'Quicksand, sans-serif',
                    fontWeight: 400,
                    letterSpacing: '0.01em',
                  }}
                  required
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Password field */}
            <div>
              <label className="block text-xs font-medium text-white/60 mb-1.5">Password</label>
              <div className="relative">
                <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 z-10" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className="w-full pl-9 pr-12 py-2.5 rounded-lg text-sm placeholder-white/25 focus:outline-none transition-all border"
                  style={{
                    background: 'transparent',
                    borderColor: 'rgba(255,255,255,0.15)',
                    color: 'white',
                    WebkitBoxShadow: '0 0 0px 1000px transparent inset',
                    WebkitTextFillColor: 'rgba(255,255,255,0.9)',
                    caretColor: 'white',
                    fontFamily: 'Quicksand, sans-serif',
                    fontWeight: 400,
                    letterSpacing: '0.01em',
                  }}
                  required
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70 transition-colors z-10 flex items-center"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full mt-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          {/* Demo info */}
          <div className="mt-6 pt-5 border-t border-white/10 text-center">
            <p className="text-[11px] text-white/30 mb-1">Demo — admin@company.com / admin123</p>
            <p className="text-[10px] text-white/20">Authorized personnel only</p>
          </div>
        </div>
      </div>
    </div>
  )
}
