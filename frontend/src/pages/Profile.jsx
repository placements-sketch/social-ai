import { useState } from 'react'
import { User, Lock, Save, Eye, EyeOff, ShieldCheck, Calendar } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../context/AuthContext'
import PresenceDot from '../components/PresenceDot'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const authHeaders = () => ({
  'Content-Type': 'application/json',
  Authorization: `Bearer ${localStorage.getItem('authToken')}`,
})

// What each role actually permits. The badge said "admin" and left the reader
// to guess what that bought them.
const ROLE_BLURB = {
  admin: 'Full access — settings, users, the assistant\u2019s behaviour and every conversation.',
  supervisor: 'Oversees agents — sees every conversation and can assign work.',
  agent: 'Answers the conversations assigned to you, and can claim unclaimed ones.',
}

const strengthOf = (pw) => {
  if (!pw) return null
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++
  if (/\d/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  const buckets = [
    { label: 'Weak', color: 'bg-red-500', width: '30%' },
    { label: 'Weak', color: 'bg-red-500', width: '30%' },
    { label: 'Fair', color: 'bg-amber-500', width: '55%' },
    { label: 'Good', color: 'bg-yellow-500', width: '78%' },
    { label: 'Strong', color: 'bg-green-500', width: '100%' },
  ]
  return buckets[Math.min(s, 4)]
}

export default function Profile() {
  const { user, refreshUser } = useAuth()

  const [fullName, setFullName] = useState(user?.full_name || '')
  const [email, setEmail] = useState(user?.email || '')
  const [savingProfile, setSavingProfile] = useState(false)
  const [profileMsg, setProfileMsg] = useState(null)

  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [savingPw, setSavingPw] = useState(false)
  const [pwMsg, setPwMsg] = useState(null)

  const strength = strengthOf(newPw)
  const initial = user?.full_name?.charAt(0).toUpperCase() || 'U'
  const memberSince = user?.created_at
    ? new Date(user.created_at).toLocaleDateString('en-KE', { month: 'long', year: 'numeric' })
    : null

  const saveProfile = async () => {
    setProfileMsg(null)
    const name = fullName.trim()
    if (name.length < 2) return setProfileMsg({ type: 'error', text: 'Full name must be at least 2 characters.' })
    const mail = email.trim().toLowerCase()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail)) return setProfileMsg({ type: 'error', text: 'Enter a valid email address.' })
    // Not an error — nothing was wrong, there was simply nothing to do. It was
    // shown in red beside a red validation message, which taught people to read
    // "you made a mistake" when they had not.
    if (name === (user?.full_name || '') && mail === (user?.email || ''))
      return setProfileMsg({ type: 'info', text: 'No changes to save.' })
    setSavingProfile(true)
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        method: 'PATCH', headers: authHeaders(),
        body: JSON.stringify({ full_name: name, email: mail }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to update profile')
      setProfileMsg({ type: 'success', text: 'Profile updated.' })
      refreshUser?.()
    } catch (err) {
      setProfileMsg({ type: 'error', text: err.message })
    } finally {
      setSavingProfile(false)
    }
  }

  const savePassword = async () => {
    setPwMsg(null)
    if (!currentPw || !newPw) return setPwMsg({ type: 'error', text: 'Fill in all password fields.' })
    if (newPw.length < 8) return setPwMsg({ type: 'error', text: 'New password must be at least 8 characters.' })
    if (newPw !== confirmPw) return setPwMsg({ type: 'error', text: 'New passwords do not match.' })
    if (newPw === currentPw) return setPwMsg({ type: 'error', text: 'New password must differ from the current one.' })
    setSavingPw(true)
    try {
      const res = await fetch(`${API_BASE}/auth/me/password`, {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to change password')
      setPwMsg({ type: 'success', text: 'Password updated.' })
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
    } catch (err) {
      setPwMsg({ type: 'error', text: err.message })
    } finally {
      setSavingPw(false)
    }
  }

  // `input` is the shared class. This was a private copy of it that hardcoded
  // bg-white and border-gray-200, so it drifted from every other field in the
  // product and had to be maintained separately.
  const inputCls = 'input w-full text-sm'
  const labelCls = 'block text-xs font-semibold text-gray-600 mb-1.5'
  const Feedback = ({ msg }) => msg
    ? <p className={clsx('text-xs mt-1',
        msg.type === 'success' ? 'text-green-600'
          : msg.type === 'info' ? 'text-gray-500'
          : 'text-red-600')}>{msg.text}</p>
    : null

  return (
    // Two columns on desktop: identity on the left, the things you actually
    // came to change on the right. It was three identical stacked cards in a
    // narrow column before — every block the same weight, so nothing led.
    <div className="w-full max-w-5xl mx-auto">
      {/* ── Identity banner ────────────────────────────────────────────────
          A tinted band with the avatar breaking its lower edge, so the page
          opens with a piece of the brand instead of a fourth grey rectangle. */}
      <div className="card rounded-3xl overflow-hidden mb-5">
        <div className="relative h-28 sm:h-32" style={{
          // Brand 500 → 600 → 700. Was three hand-picked stops on the old hue,
          // which the palette swap left stranded a different colour from
          // everything around them. Using ramp members means the next change
          // carries them too.
          background: 'linear-gradient(115deg, #99e600 0%, #81c200 42%, #669900 100%)',
        }}>
          {/* Soft vignette so the avatar's ring has something to sit against. */}
          <div className="absolute inset-0" style={{
            background: 'radial-gradient(120% 140% at 82% -20%, rgba(255,255,255,0.42), transparent 58%)',
          }} />
          <span className="absolute top-4 right-5 text-[11px] font-bold uppercase tracking-[0.14em] text-black/45">
            Shop Zetu
          </span>
        </div>

        <div className="px-5 sm:px-7 pb-6">
          {/* Only the AVATAR overlaps the band. Pulling the whole row up took
              the name and email with it, so they sat on top of the lime and
              became unreadable — dark text on a bright field. The avatar is a
              solid shape and is the one thing that should break the edge. */}
          {/* relative z-10 so the avatar paints ABOVE the banner.
              The banner is `position: relative`, and a positioned element wins
              over a static sibling no matter which comes later in the DOM — so
              the avatar's negative margin lifted it into the banner's space and
              the banner then drew straight over the top of it. It looked like
              the avatar was clipped; it was buried. */}
          <div className="relative z-10 flex flex-col sm:flex-row sm:items-end gap-4">
            <div className="w-[88px] h-[88px] -mt-11 sm:-mt-12 rounded-3xl bg-gray-900 text-white flex items-center justify-center text-3xl font-bold shrink-0 ring-4 ring-white dark:ring-[#0f0f0f] shadow-xl">
              {initial}
            </div>
            <div className="min-w-0 flex-1 sm:pb-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-2xl font-bold text-gray-900 truncate leading-tight">
                  {user?.full_name || 'Your profile'}
                </h1>
                {user?.role && (
                  <span className="text-[11px] font-bold uppercase tracking-wide bg-gray-900 text-white px-2 py-0.5 rounded-full">
                    {user.role}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-500 truncate mt-0.5">{user?.email}</p>
            </div>

            {/* Your own presence, so the dot on the Users page is explicable
                rather than mysterious — this is what colleagues see of you. */}
            <div className="flex items-center gap-2 shrink-0 sm:pb-1.5">
              <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-gray-600 bg-gray-100 rounded-full pl-2 pr-2.5 py-1">
                <PresenceDot status="online" size="sm" />
                Online now
              </span>
            </div>
          </div>

          {/* At-a-glance facts. Previously these were a run-on line of muted
              text; as labelled cells they can actually be read. */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5">
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2.5">
              <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400">Member since</p>
              <p className="text-sm font-semibold text-gray-900 mt-0.5 flex items-center gap-1.5">
                <Calendar size={13} className="text-brand-500 shrink-0" />
                {memberSince || '—'}
              </p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-3.5 py-2.5 sm:col-span-2">
              <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400">
                What your role allows
              </p>
              <p className="text-xs text-gray-600 mt-1 leading-relaxed">
                {ROLE_BLURB[user?.role] || '—'}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
      {/* Profile details */}
      <div className="card rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <span className="w-8 h-8 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
            <User size={15} />
          </span>
          <div>
            <h2 className="text-sm font-bold text-gray-900 leading-tight">Profile details</h2>
            <p className="text-[12px] text-gray-400">Your name and sign-in email.</p>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <label className={labelCls}>Full name</label>
            <input className={inputCls} value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Your name" />
          </div>
          <div>
            <label className={labelCls}>Email</label>
            <input className={inputCls} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="name@company.com" />
          </div>
          <Feedback msg={profileMsg} />
          <div className="flex justify-end">
            <button onClick={saveProfile} disabled={savingProfile} className="btn-primary flex items-center gap-2 text-xs disabled:opacity-50">
              <Save size={14} /> {savingProfile ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </div>
      </div>

      {/* Password */}
      <div className="card rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <span className="w-8 h-8 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center shrink-0">
            <Lock size={15} />
          </span>
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-gray-900 leading-tight">Password</h2>
            <p className="text-[12px] text-gray-400 flex items-center gap-1">
              <ShieldCheck size={11} className="shrink-0" /> Requires your current password
            </p>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <label className={labelCls}>Current password</label>
            <input className={inputCls} type={showPw ? 'text' : 'password'} value={currentPw} onChange={e => setCurrentPw(e.target.value)} autoComplete="current-password" />
          </div>
          <div>
            <label className={labelCls}>New password</label>
            <div className="relative">
              <input className={`${inputCls} pr-10`} type={showPw ? 'text' : 'password'} value={newPw} onChange={e => setNewPw(e.target.value)} autoComplete="new-password" />
              <button type="button" onClick={() => setShowPw(s => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600" tabIndex={-1}>
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
            {strength && (
              <div className="mt-2">
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all ${strength.color}`} style={{ width: strength.width }} />
                </div>
                <p className="text-[11px] font-medium text-gray-400 mt-1">Strength: {strength.label}</p>
              </div>
            )}
          </div>
          <div>
            <label className={labelCls}>Confirm new password</label>
            <input className={inputCls} type={showPw ? 'text' : 'password'} value={confirmPw} onChange={e => setConfirmPw(e.target.value)} autoComplete="new-password" />
          </div>
          <Feedback msg={pwMsg} />
          <div className="flex justify-end">
            <button onClick={savePassword} disabled={savingPw} className="btn-primary flex items-center gap-2 text-xs disabled:opacity-50">
              <Lock size={14} /> {savingPw ? 'Updating…' : 'Update password'}
            </button>
          </div>
        </div>
      </div>
      </div>
    </div>
  )
}