import clsx from 'clsx'
import { parseBackendTime } from '../utils/time'

/**
 * A user's presence, as a dot.
 *
 * Two states, not three. There used to be an amber "Idle" between online and
 * offline, covering 90 seconds to 5 minutes since the last heartbeat. It was
 * removed because nobody could act on it — an agent shown as idle might be
 * reading a long thread or might have shut their laptop four minutes ago, and
 * the dot could not tell you which. "Offline · last seen 4m ago" says the same
 * thing without implying someone is half-available.
 *
 * Sizes: 'sm' (default, 8px), 'md' (10px), 'lg' (12px)
 */
export default function PresenceDot({ status, size = 'sm', pulse = true, className }) {
  const online = status === 'online'
  const sizeMap = {
    sm: 'w-2 h-2',
    md: 'w-2.5 h-2.5',
    lg: 'w-3 h-3',
  }
  const label = online ? 'Online' : 'Offline'

  return (
    <span
      role="img"
      className={clsx(
        'inline-block rounded-full shrink-0',
        sizeMap[size] || sizeMap.sm,
        online ? 'bg-green-500' : 'bg-gray-400',
        className
      )}
      style={online && pulse
        ? { animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }
        : undefined}
      title={label}
      aria-label={label}
    />
  )
}

/**
 * A human-readable "last seen" string.
 *
 * Returns null when the user is online — there is no point telling someone
 * that a person who is here right now was last seen just now.
 */
export function lastSeenLabel(lastSeenAt, status) {
  if (status === 'online') return null
  if (!lastSeenAt) return 'Never signed in'

  const seen = parseBackendTime(lastSeenAt)
  // A bare `return` here handed back undefined, so a malformed timestamp
  // rendered as nothing at all rather than as an honest "unknown".
  if (!seen) return 'Last seen unknown'

  const delta = Math.floor((Date.now() - seen.getTime()) / 1000)
  if (delta < 0) return 'Last seen just now'      // clock skew safety
  if (delta < 60) return 'Last seen just now'
  if (delta < 3600) return `Last seen ${Math.floor(delta / 60)}m ago`
  if (delta < 86400) return `Last seen ${Math.floor(delta / 3600)}h ago`

  const days = Math.floor(delta / 86400)
  if (days < 7) return `Last seen ${days}d ago`
  return `Last seen ${seen.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
}
