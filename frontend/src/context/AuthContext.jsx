import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext()

// Standardise on VITE_API_BASE which already includes /api. Strip the
// trailing /api so existing `${API_URL}/api/auth/login` fetches still work.
const API_BASE = import.meta.env.VITE_API_BASE || ''
const API_URL = API_BASE.endsWith('/api') ? API_BASE.slice(0, -4) : API_BASE

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Check if user is logged in on mount
  useEffect(() => {
    const token = localStorage.getItem('authToken')
    if (token) {
      verifyToken(token)
    } else {
      setLoading(false)
    }
  }, [])

  // Auto-logout the moment the JWT expires — decode `exp` and schedule it.
  // Clearing the user makes ProtectedRoute redirect to /login automatically.
  useEffect(() => {
    if (!user) return
    const token = localStorage.getItem('authToken')
    if (!token) return
    let timer
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      const msLeft = payload?.exp ? payload.exp * 1000 - Date.now() : null
      if (msLeft !== null) {
        if (msLeft <= 0) {
          localStorage.removeItem('authToken')
          setUser(null)
          return
        }
        timer = setTimeout(() => {
          localStorage.removeItem('authToken')
          setUser(null)
        }, msLeft)
      }
    } catch { /* malformed token — verifyToken already handles the 401 path */ }
    return () => clearTimeout(timer)
  }, [user])

  // Heartbeat: while authenticated, ping the backend every 30s so other
  // staff see this user as "online". Only runs when a tab is visible —
  // background tabs go idle naturally.
  // Keyed on user?.id, NOT the whole user object: the ping below writes the
  // fresh presence back into `user`, and depending on the object identity would
  // tear down and restart this effect on every beat — pinging again, updating
  // again, forever.
  useEffect(() => {
    if (!user?.id) return

    const ping = async () => {
      if (document.visibilityState !== 'visible') return
      const token = localStorage.getItem('authToken')
      if (!token) return
      try {
        const res = await fetch(`${API_URL}/api/auth/heartbeat`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        // The heartbeat is the only thing that knows you're online. Without
        // feeding its answer back, `user.presence` kept whatever /auth/verify
        // said at login — 'offline', because logging out clears last_seen_at —
        // and only a page refresh ever corrected it.
        const data = await res.json()
        if (!data?.presence) return
        setUser(prev => (
          prev && prev.presence === data.presence ? prev : { ...prev, ...data }
        ))
      } catch {
        // Silent — heartbeat failure is non-fatal
      }
    }

    ping() // immediate ping on login
    const timer = setInterval(ping, 30_000)

    // Coming back to a backgrounded tab should not leave you showing offline
    // for up to another 30 seconds. Beats are skipped while hidden, so the
    // moment the tab is visible again is exactly when one is owed.
    const onVisible = () => { if (document.visibilityState === 'visible') ping() }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [user?.id])

const verifyToken = async (token) => {
    try {
      const response = await fetch(`${API_URL}/api/auth/verify`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      })
      if (response.ok) {
        setUser(await response.json())
      } else {
        localStorage.removeItem('authToken')
        setUser(null)
      }
    } catch {
      localStorage.removeItem('authToken')
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  const refreshUser = async () => {
    const token = localStorage.getItem('authToken')
    if (!token) return
    try {
      const res = await fetch(`${API_URL}/api/auth/verify`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) setUser(await res.json())
    } catch { /* silent */ }
  }

  const login = async (email, password) => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || 'Login failed')
      }

      const { user, token } = await response.json()
      localStorage.setItem('authToken', token)
      setUser(user)
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    const token = localStorage.getItem('authToken')
    if (token) {
      try {
        await fetch(`${API_URL}/api/auth/logout`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` }
        })
      } catch (err) {
        console.error('Logout error:', err)
      }
    }
    localStorage.removeItem('authToken')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
