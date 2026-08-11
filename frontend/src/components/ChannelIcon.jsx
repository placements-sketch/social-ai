import { Instagram, MessageCircle, Music } from 'lucide-react'
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

// Facebook, WhatsApp and TikTok have no lucide glyph, so they are drawn.
//
// WhatsApp was a Smartphone icon — a generic handset that reads as "mobile",
// not as WhatsApp. Nobody identifies the app by a phone outline; they identify
// it by the speech bubble with the receiver inside it. The real mark is one
// path, so there is no reason to approximate it.
function WhatsAppGlyph({ size, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} aria-hidden="true">
      <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2 22l5.25-1.38a9.9 9.9 0 0 0 4.79 1.22h.01c5.46 0 9.9-4.45 9.9-9.91C21.95 6.45 17.5 2 12.04 2zm0 18.15h-.01a8.2 8.2 0 0 1-4.19-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.2 8.2 0 0 1-1.26-4.38c0-4.54 3.7-8.23 8.24-8.23a8.18 8.18 0 0 1 8.23 8.24c0 4.54-3.7 8.23-8.22 8.23zm4.52-6.16c-.25-.12-1.47-.72-1.69-.81-.23-.08-.39-.12-.56.13-.16.24-.64.8-.78.97-.14.16-.29.18-.54.06-.25-.13-1.05-.39-1.99-1.23-.74-.66-1.24-1.47-1.38-1.72-.15-.25-.02-.38.11-.5.11-.11.25-.29.37-.43.13-.15.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.41-.42-.56-.43h-.48c-.16 0-.43.06-.65.31-.22.25-.85.83-.85 2.03s.87 2.35.99 2.51c.12.16 1.71 2.61 4.14 3.66.58.25 1.03.4 1.38.51.58.19 1.11.16 1.53.1.47-.07 1.44-.59 1.64-1.16.2-.57.2-1.05.14-1.16-.06-.1-.22-.16-.47-.28z"/>
    </svg>
  )
}

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
  whatsapp:          { Icon: WhatsAppGlyph, color: '#25D366', label: 'WhatsApp' },
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

  // The drawn glyphs take their colour as a prop; lucide icons take a style.
  const mark = Icon === FacebookGlyph
    ? <FacebookGlyph size={glyph} />
    : Icon === WhatsAppGlyph
      ? <WhatsAppGlyph size={glyph} color={color} />
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
