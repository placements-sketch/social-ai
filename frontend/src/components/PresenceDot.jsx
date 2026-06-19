import clsx from 'clsx'

/**
 * Small colored dot showing a user's presence status.
 * Sizes: 'sm' (default, 8px), 'md' (10px), 'lg' (12px)
 */
export default function PresenceDot({ status, size = 'sm', pulse = true, className }) {
  const colorMap = {
    online:  'bg-green-500',
    idle:    'bg-amber-500',
    offline: 'bg-gray-400',
  }
  const sizeMap = {
    sm: 'w-2 h-2',
    md: 'w-2.5 h-2.5',
    lg: 'w-3 h-3',
  }
  const titleMap = {
    online:  'Online',
    idle:    'Idle',
    offline: 'Offline',
  }
  const color = colorMap[status] || colorMap.offline

  return (
    <span
      className={clsx('inline-block rounded-full shrink-0', sizeMap[size] || sizeMap.sm, color, className)}
      style={status === 'online' && pulse ? { animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' } : undefined}
      title={titleMap[status] || 'Unknown'}
      aria-label={titleMap[status] || 'Unknown'}
    />
  )
}

/**
 * Compute a human-readable "last seen" string.
 * Returns null for online (no point telling someone they're online).
 */
export function lastSeenLabel(lastSeenAt, status) {
  if (status === 'online') return null
  if (!lastSeenAt) return 'Never signed in'
  const seen = new Date(lastSeenAt)
  const delta = Math.floor((Date.now() - seen.getTime()) / 1000)
  if (delta < 60) return 'Last seen just now'
  if (delta < 3600) return `Last seen ${Math.floor(delta / 60)} min ago`
  if (delta < 86400) return `Last seen ${Math.floor(delta / 3600)}h ago`
  const days = Math.floor(delta / 86400)
  if (days < 7) return `Last seen ${days}d ago`
  return `Last seen ${seen.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`
}