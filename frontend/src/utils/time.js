/**
 * Backend timestamps are naive (no Z, no offset) but always represent UTC.
 * JS `new Date(string)` parses naive ISO strings as LOCAL time, which is wrong.
 * parseBackendTime forces UTC interpretation by appending 'Z' if missing.
 */
export function parseBackendTime(isoString) {
  if (!isoString) return null
  const hasTz = isoString.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(isoString)
  const normalized = hasTz ? isoString : isoString + 'Z'
  const d = new Date(normalized)
  return isNaN(d.getTime()) ? null : d
}

/**
 * "just now" / "5m ago" / "3h ago" / "2d ago" for a backend ISO timestamp.
 */
export function formatTimeAgo(isoString) {
  const date = parseBackendTime(isoString)
  if (!date) return ''
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 0) return 'just now'           // clock skew safety
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

/**
 * Day-grained version for things older than today: "Today" / "Yesterday" / "5d ago" / "2mo ago" / "1y ago"
 */
export function formatDateAgo(isoString) {
  const date = parseBackendTime(isoString)
  if (!date) return 'Never'
  const days = Math.floor((Date.now() - date.getTime()) / 86400000)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 30) return `${days}d ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}