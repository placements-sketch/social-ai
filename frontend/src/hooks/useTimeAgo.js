import { useState, useEffect } from 'react'
import { formatTimeAgo } from '../utils/time'

/**
 * Hook that provides a reactive "time ago" string that updates every 30s.
 * Backend timestamps are naive UTC — formatTimeAgo handles the Z-append.
 */
export function useTimeAgo(isoTimestamp) {
  const [timeAgo, setTimeAgo] = useState(() => formatTimeAgo(isoTimestamp))

  useEffect(() => {
    setTimeAgo(formatTimeAgo(isoTimestamp))
    const timer = setInterval(() => setTimeAgo(formatTimeAgo(isoTimestamp)), 30000)
    return () => clearInterval(timer)
  }, [isoTimestamp])

  return timeAgo
}