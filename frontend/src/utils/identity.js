// Mirror of app/identity.py::display_for_external_id.
//
// A raw Instagram id is a 17-digit IGSID that identifies the customer to
// nobody — "@1486178709937522 sent a message" tells an agent less than "a
// customer did". Wherever we have no username, show what platform they are on
// and the last four digits, which is enough to tell two conversations apart.
//
// Keep in step with the Python version. The two exist separately because the
// server renders notification bodies and the browser renders the activity
// feed, and neither can call the other.
const PLATFORM_LABELS = {
  instagram: 'Instagram user',
  facebook: 'Facebook user',
  tiktok: 'TikTok user',
  whatsapp: 'WhatsApp user',
}

export function displayForExternalId(externalId, channel) {
  const ext = String(externalId ?? '').trim()
  if (!ext) return 'Unknown customer'
  // Platform ids only. A phone number or an email is already human-readable,
  // and 15 digits is the shortest real IGSID/PSID we have seen.
  if (/^\d{15,}$/.test(ext)) {
    const platform = String(channel ?? '').split('_')[0]
    return `${PLATFORM_LABELS[platform] || 'Customer'} · ${ext.slice(-4)}`
  }
  return ext
}

/**
 * Up to two initials for an avatar.
 *
 * One letter is ambiguous the moment two people share it — a sidebar showing
 * "S" cannot tell Super Admin from Sarah, which is precisely when you want to
 * know whose account you are in.
 *
 * Two words take a letter from each; a single word gives its first two letters,
 * because "MA" reads as a monogram while a lone "M" reads as a placeholder.
 * Anything unusable falls back to "U" — the character the call sites already
 * used, so nothing changes shape when a name is missing.
 */
export function initials(name) {
  const parts = String(name ?? '')
    .trim()
    .split(/\s+/)
    .filter(p => /[a-z0-9]/i.test(p))

  if (parts.length === 0) return 'U'
  if (parts.length === 1) {
    // Strip anything non-alphanumeric first, so "@amina_ke" gives AM, not "@A".
    const w = parts[0].replace(/[^a-z0-9]/gi, '')
    return (w.slice(0, 2) || 'U').toUpperCase()
  }
  const first = parts[0].replace(/[^a-z0-9]/gi, '').charAt(0)
  const last = parts[parts.length - 1].replace(/[^a-z0-9]/gi, '').charAt(0)
  return ((first + last) || 'U').toUpperCase()
}
