import { Instagram, MessageCircle, Smartphone, Music } from 'lucide-react'
import clsx from 'clsx'

/*
 * One social-channel icon, everywhere.
 *
 * There were three independent mappings — Messages.jsx, Dashboard.jsx and
 * Channels.jsx — each with its own sizes, its own Facebook mark (an inline "f"
 * on a blue square in one, a component in another) and its own TikTok glyph (a
 * "♪" character). They drifted because nothing held them together, so the same
 * channel looked different depending on which page you were on.
 *
 * The design is the one from the connections list: a soft round tile with the
 * platform's colour on the glyph, not on the tile. A saturated tile at 36px
 * reads as a button and competes with the content beside it; a tinted glyph on
 * a neutral ground stays recognisable and stays quiet.
 */

// Facebook and TikTok have no lucide glyph, so they are drawn.
function FacebookGlyph({ size }) {
  return (
    <span
      className="font-black leading-none"
      style={{ color: '#1877F2', fontSize: size, lineHeight: 1 }}
    >
      f
    </span>
  )
}

const CHANNELS = {
  instagram_dm:      { Icon: Instagram,     color: '#e1306c', label: 'Instagram DM' },
  instagram_comment: { Icon: MessageCircle, color: '#e1306c', label: 'Instagram comment' },
  facebook_dm:       { Icon: FacebookGlyph, color: '#1877F2', label: 'Facebook DM' },
  facebook_comment:  { Icon: FacebookGlyph, color: '#1877F2', label: 'Facebook comment' },
  whatsapp:          { Icon: Smartphone,    color: '#25D366', label: 'WhatsApp' },
  tiktok_dm:         { Icon: Music,         color: '#ff0050', label: 'TikTok DM' },
  tiktok_comment:    { Icon: Music,         color: '#ff0050', label: 'TikTok comment' },
}

// Platform-level fallback, so 'instagram' works as well as 'instagram_dm'.
const PLATFORMS = {
  instagram: CHANNELS.instagram_dm,
  facebook:  CHANNELS.facebook_dm,
  whatsapp:  CHANNELS.whatsapp,
  tiktok:    CHANNELS.tiktok_dm,
}

const SIZES = {
  xs: { tile: 'w-6 h-6',  glyph: 11 },
  sm: { tile: 'w-7 h-7',  glyph: 13 },
  md: { tile: 'w-9 h-9',  glyph: 15 },
  lg: { tile: 'w-11 h-11', glyph: 19 },
}

export function channelMeta(channel) {
  const key = String(channel || '').toLowerCase()
  return CHANNELS[key] || PLATFORMS[key.split('_')[0]] || null
}

export default function ChannelIcon({
  channel,
  size = 'md',
  bare = false,        // glyph only, for tight rows where a tile is too heavy
  className,
  title,
}) {
  const meta = channelMeta(channel)
  const { tile, glyph } = SIZES[size] || SIZES.md
  if (!meta) return null
  const { Icon, color, label } = meta

  const mark = Icon === FacebookGlyph
    ? <FacebookGlyph size={glyph} />
    : <Icon size={glyph} style={{ color }} />

  if (bare) {
    return <span className={clsx('inline-flex shrink-0', className)} title={title || label}>{mark}</span>
  }

  return (
    <span
      title={title || label}
      className={clsx(
        tile,
        /* bg-gray-100 rather than a tinted-per-platform ground: `.dark
           .bg-gray-100` already maps to a raised dark surface, so one class
           gives a tile that works in both themes. A per-platform tint would
           need a dark variant per platform and would drift the moment one was
           missed. */
        'rounded-full bg-gray-100 flex items-center justify-center shrink-0',
        className
      )}
    >
      {mark}
    </span>
  )
}
