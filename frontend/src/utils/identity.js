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
