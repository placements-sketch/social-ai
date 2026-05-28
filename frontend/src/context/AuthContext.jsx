import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext()

const API_URL = 'http://127.0.0.1:5000'

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

  const verifyToken = async (token) => {
    try {
      console.log('[AUTH] Verifying token:', token.substring(0, 20) + '...')
      const response = await fetch(`${API_URL}/api/auth/verify`, {
        method: 'GET',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })
      console.log('[AUTH] Verify response status:', response.status)
      if (response.ok) {
        const userData = await response.json()
        console.log('[AUTH] Token verified, user:', userData.email)
        setUser(userData)
      } else {
        const errorData = await response.json()
        console.error('[AUTH] Token verification failed:', response.status, errorData)
        localStorage.removeItem('authToken')
        setUser(null)
      }
    } catch (err) {
      console.error('[AUTH] Token verification error:', err)
      localStorage.removeItem('authToken')
      setUser(null)
    } finally {
      setLoading(false)
    }
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
    <AuthContext.Provider value={{ user, loading, error, login, logout }}>
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
