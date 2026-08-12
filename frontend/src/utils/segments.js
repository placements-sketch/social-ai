import { Crown, Heart, Users, Sparkles, UserPlus, AlertTriangle, UserMinus } from 'lucide-react'

/*
 * One definition of what each customer segment looks like.
 *
 * This lived in three files — the list page, the detail page and the trends
 * chart — and had already drifted: the chart used #94a3b8 for never_bought
 * while the chips used slate-600, so the same customer was two different
 * colours depending on which screen you were on. Colour is how someone tracks
 * an entity across a page; if it changes between the badge and the chart beside
 * it, it has stopped being information and become decoration.
 *
 * ── Why these hexes ──────────────────────────────────────────────────────────
 * They are validated, not chosen by eye. Each sits in the L 0.48–0.67 band so
 * it reads on both the white and the #141414 surface, clears a 0.10 chroma
 * floor, and holds >=3:1 contrast against both.
 *
 * Two properties are deliberate and will look like mistakes:
 *
 * 1. never_bought and churned are not grey. Grey is what a category looks like
 *    when nobody assigned it a colour, and these are real segments people
 *    filter and act on. The hard constraint: two greys cannot be told apart.
 *    Grey varies only in lightness, the usable band is 0.19 wide, and no two
 *    points in it are both far enough apart to distinguish AND dark enough to
 *    read on white. One had to gain a hue, so both did.
 *
 * 2. Tints are opacity on the segment's own hex, not Tailwind's -50 shades.
 *    bg-amber-50 is a fixed near-white — right on the light surface, a glowing
 *    slab on the dark one. /10 of the hex tracks whatever sits underneath.
 *
 * ── Why this order ───────────────────────────────────────────────────────────
 * Lifecycle order, and it is load-bearing: it keeps the pairs that collide
 * under colour blindness away from each other. Adjacent-pair checks pass in
 * both modes. Across ALL pairs, VIP-amber and At-Risk-orange still converge
 * under deuteranopia (ΔE 3.2) — seven categorical hues is past what CVD leaves
 * room for. That pair is carried by the icon and text label that every chip,
 * badge and legend entry already shows. Re-run before changing anything here:
 *
 *   node scripts/validate_palette.js \
 *     "#b38600,#c43a6f,#4a90e2,#00a37f,#6d70b8,#cf5f2c,#9333ea" \
 *     --mode dark --surface "#141414"
 */
export const SEGMENT_COLORS = {
  vip:          '#b38600',
  loyal:        '#c43a6f',
  regular:      '#4a90e2',
  new:          '#00a37f',
  never_bought: '#6d70b8',
  at_risk:      '#cf5f2c',
  churned:      '#9333ea',
}

// Tailwind scans source for complete class strings, so these are written out in
// full rather than built from SEGMENT_COLORS — `text-[${hex}]` would compile to
// nothing and every badge would render unstyled.
export const SEGMENT_META = {
  vip:          { label: 'VIP',          icon: Crown,         color: 'text-[#b38600]', bg: 'bg-[#b38600]/10', border: 'border-[#b38600]/30', ring: 'ring-[#b38600]/30', accent: 'from-[#b38600]/70 to-[#b38600]', dot: 'bg-[#b38600]' },
  loyal:        { label: 'Loyal',        icon: Heart,         color: 'text-[#c43a6f]', bg: 'bg-[#c43a6f]/10', border: 'border-[#c43a6f]/30', ring: 'ring-[#c43a6f]/30', accent: 'from-[#c43a6f]/70 to-[#c43a6f]', dot: 'bg-[#c43a6f]' },
  regular:      { label: 'Regular',      icon: Users,         color: 'text-[#4a90e2]', bg: 'bg-[#4a90e2]/10', border: 'border-[#4a90e2]/30', ring: 'ring-[#4a90e2]/30', accent: 'from-[#4a90e2]/70 to-[#4a90e2]', dot: 'bg-[#4a90e2]' },
  new:          { label: 'New Convert',  icon: Sparkles,      color: 'text-[#00a37f]', bg: 'bg-[#00a37f]/10', border: 'border-[#00a37f]/30', ring: 'ring-[#00a37f]/30', accent: 'from-[#00a37f]/70 to-[#00a37f]', dot: 'bg-[#00a37f]' },
  never_bought: { label: 'Never Bought', icon: UserPlus,      color: 'text-[#6d70b8]', bg: 'bg-[#6d70b8]/10', border: 'border-[#6d70b8]/30', ring: 'ring-[#6d70b8]/30', accent: 'from-[#6d70b8]/70 to-[#6d70b8]', dot: 'bg-[#6d70b8]' },
  at_risk:      { label: 'At Risk',      icon: AlertTriangle, color: 'text-[#cf5f2c]', bg: 'bg-[#cf5f2c]/10', border: 'border-[#cf5f2c]/30', ring: 'ring-[#cf5f2c]/30', accent: 'from-[#cf5f2c]/70 to-[#cf5f2c]', dot: 'bg-[#cf5f2c]' },
  churned:      { label: 'Churned',      icon: UserMinus,     color: 'text-[#9333ea]', bg: 'bg-[#9333ea]/10', border: 'border-[#9333ea]/30', ring: 'ring-[#9333ea]/30', accent: 'from-[#9333ea]/70 to-[#9333ea]', dot: 'bg-[#9333ea]' },
}

// Shorter than SEGMENT_META.label where space is tight — chart legends and
// axis ticks, which have no room for "New Convert".
export const SEGMENT_LABELS = {
  vip: 'VIP', loyal: 'Loyal', regular: 'Regular', new: 'New',
  never_bought: 'Never bought', at_risk: 'At risk', churned: 'Churned',
}

// For a segment the backend invented that the frontend has not been taught.
// Deliberately outside the palette: an unknown segment should look unknown
// rather than borrow another segment's identity and be silently miscounted.
export const SEGMENT_FALLBACK = '#7a7a7a'
