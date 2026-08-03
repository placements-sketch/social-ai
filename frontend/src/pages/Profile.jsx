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
    <div className="space-y-5 w-full max-w-2xl mx-auto">
      {/* Identity hero */}
      <div className="card p-6 flex items-center gap-5">
        <div className="w-16 h-16 rounded-2xl bg-brand-500 flex items-center justify-center text-white text-2xl font-bold shrink-0">
          {initial}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-gray-900 truncate">{user?.full_name || 'Your profile'}</h1>
            {user?.role && (
              <span className="text-[10px] font-semibold bg-gray-900 text-white px-2 py-0.5 rounded-full capitalize">{user.role}</span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-0.5 truncate">{user?.email}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {/* Your own presence, so the dot on the Users page is explicable
                rather than mysterious — this is what colleagues see of you. */}
            <span className="inline-flex items-center gap-1.5 text-[11px] text-gray-500">
              <PresenceDot status="online" size="sm" />
              Online now
            </span>
            {memberSince && (
              <span className="text-[11px] text-gray-400">· Member since {memberSince}</span>
            )}
          </div>
          <p className="text-[11px] text-gray-400 mt-1.5">{ROLE_BLURB[user?.role] || ''}</p>
        </div>
      </div>

      {/* Profile details */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <User size={15} className="text-brand-500" />
          <h2 className="text-sm font-bold text-gray-900">Profile details</h2>
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
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Lock size={15} className="text-brand-500" />
          <h2 className="text-sm font-bold text-gray-900">Password</h2>
          <span className="ml-auto flex items-center gap-1 text-[10px] font-medium text-gray-400">
            <ShieldCheck size={12} /> Requires current password
          </span>
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
                <p className="text-[10px] font-medium text-gray-400 mt-1">Strength: {strength.label}</p>
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
  )
}