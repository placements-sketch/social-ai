import { createContext, useContext, useEffect, useState, useCallback } from 'react'

/**
 * Theme state for the app. Dark is the default — light is opt-in and
 * remembered per browser via localStorage.
 *
 * The `dark` class actually lands on <html> in index.html, before React
 * mounts, so the first paint is already correct. This provider keeps that
 * class in sync afterwards. Keep the two in agreement if the rule changes.
 */
const ThemeContext = createContext({ theme: 'dark', toggleTheme: () => {}, setTheme: () => {} })

const STORAGE_KEY = 'theme'

function readStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    // Private mode / storage blocked — fall back to the default.
    return 'dark'
  }
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStoredTheme)

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Non-fatal: the theme still applies for this session.
    }
  }, [theme])

  const setTheme = useCallback((next) => {
    setThemeState(next === 'light' ? 'light' : 'dark')
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeState(t => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme, isDark: theme === 'dark' }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
