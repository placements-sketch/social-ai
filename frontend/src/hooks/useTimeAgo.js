import { useState, useEffect } from 'react'

/**
 * Hook that provides a reactive "time ago" string that updates every minute.
 * This ensures timestamps like "3h ago" update to "3h 1m ago" instead of staying static.
 */
export function useTimeAgo(isoTimestamp) {
  const [timeAgo, setTimeAgo] = useState('')

  useEffect(() => {
    const calculate = () => {
      if (!isoTimestamp) {
        setTimeAgo('')
        return
      }
      const date = new Date(isoTimestamp)
      const now = new Date()
      const seconds = Math.floor((now - date) / 1000)

      if (seconds < 60) setTimeAgo('just now')
      else if (seconds < 3600) setTimeAgo(`${Math.floor(seconds / 60)}m ago`)
      else if (seconds < 86400) setTimeAgo(`${Math.floor(seconds / 3600)}h ago`)
      else setTimeAgo(`${Math.floor(seconds / 86400)}d ago`)
    }

    calculate()
    // Update every 30 seconds to keep times reasonably fresh
    const timer = setInterval(calculate, 30000)
    return () => clearInterval(timer)
  }, [isoTimestamp])

  return timeAgo
}
