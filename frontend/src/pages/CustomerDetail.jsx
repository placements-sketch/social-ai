import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Mail, Phone, MapPin, Calendar, ShoppingBag, TrendingUp,
  Repeat, Tag, Heart, Crown, Sparkles,
  Loader2, AlertCircle, Package, ChevronLeft, ChevronRight,
  Activity, Clock, Award, Target, Zap, ExternalLink, CheckCircle2, XCircle,
} from 'lucide-react'
import clsx from 'clsx'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { formatDateAgo, formatTimeAgo, parseBackendTime } from '../utils/time'
import { getCustomer, getCustomerOrders } from '../api/customers'
import CustomerProfileExtras from './CustomerProfileExtras'
import { SEGMENT_META } from '../utils/segments'

const ORDERS_PER_PAGE = 10

// Counts, not currency. formatKES was being used for order counts and page
// totals purely because it happened to add thousands separators — which meant
// a reader (and the next editor) could not tell money from quantities, in a
// file where the money definition has just changed underneath them.
function formatCount(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

function formatKES(n) {
  return new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(n || 0)
}

function formatFullDate(iso) {
  const d = parseBackendTime(iso)
  if (!d) return '—'
  return d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ─── RFM score helpers ───────────────────────────────────────────
// recencyScore / frequencyScore / monetaryScore used to live here and are gone.
//
// They were never called: the page reads customer.rfm_r / rfm_f / rfm_m, which
// customers.py computes and stores. So these were a second, unused copy of the
// scoring thresholds sitting in the file that displays the scores — the kind of
// dead code that gets read as authoritative and then quietly disagrees with the
// rules actually in force. One set of thresholds, in the place that applies them.

function scoreColor(score) {
  if (score >= 5) return { bar: 'bg-green-500',  text: 'text-green-600',  bg: 'bg-green-50' }
  if (score >= 4) return { bar: 'bg-emerald-500', text: 'text-emerald-600', bg: 'bg-emerald-50' }
  if (score >= 3) return { bar: 'bg-amber-500',  text: 'text-amber-600',  bg: 'bg-amber-50' }
  if (score >= 2) return { bar: 'bg-orange-500', text: 'text-orange-600', bg: 'bg-orange-50' }
  if (score >= 1) return { bar: 'bg-red-500',    text: 'text-red-600',    bg: 'bg-red-50' }
  return { bar: 'bg-gray-300', text: 'text-gray-500', bg: 'bg-gray-50' }
}

// ─── KPI card with animated value ──────────────────────────────────
function KpiCard({ icon: Icon, label, value, sub, accent }) {
  const numeric = typeof value === 'number'
    ? value
    : parseFloat(String(value).replace(/[^0-9.-]/g, '')) || 0
  const animated = useCountAnimation(numeric, 1200)
  const formatted = typeof value === 'number'
    ? Math.round(animated).toLocaleString()
    : String(value).replace(/[\d,.]+/, Math.round(animated).toLocaleString())

  return (
    <div className="relative card p-4 overflow-hidden group hover:shadow-md transition-shadow">
      <div className={clsx('absolute -right-6 -top-6 w-20 h-20 rounded-full opacity-10 bg-gradient-to-br', accent)} />
      <div className="relative">
        <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center mb-3 bg-gradient-to-br', accent)}>
          <Icon size={16} className="text-white" />
        </div>
        <p className="text-[11px] text-gray-500 font-bold uppercase tracking-widest">{label}</p>
        <p className="text-xl font-bold text-gray-900 mt-1 truncate">{formatted}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5 truncate">{sub}</p>}
      </div>
    </div>
  )
}

// ─── RFM single-pillar card ────────────────────────────────────────
function RfmPillar({ icon: Icon, label, score, caption, scaleLabel }) {
  const c = scoreColor(score)
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={clsx('w-7 h-7 rounded-lg flex items-center justify-center', c.bg)}>
            <Icon size={13} className={c.text} />
          </div>
          <span className="text-xs font-bold text-gray-700 uppercase tracking-wide">{label}</span>
        </div>
        <span className={clsx('text-xs font-bold', c.text)}>{score}/5</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden mb-2">
        <div className={clsx('h-full rounded-full transition-all duration-700', c.bar)}
             style={{ width: `${(score / 5) * 100}%` }} />
      </div>
      <p className="text-[12px] text-gray-500 leading-relaxed">{caption}</p>
      <p className="text-[11px] text-gray-400 mt-1.5">{scaleLabel}</p>
    </div>
  )
}

/**
 * The customer profile itself, with no opinion about how it is being shown.
 *
 * Rendered two ways: as the /customers/:id page, and inside the slide-over on
 * the customer table. Extracted rather than duplicated because it is ~600 lines
 * of RFM tiles, spend history and order pagination, and two copies would drift
 * apart the first time either was touched.
 *
 * The route is deliberately kept alongside the sheet. A sheet cannot be
 * bookmarked, shared in Slack, or survive a refresh — losing /customers/:id to
 * gain a panel would be a straight downgrade for anyone who links to a customer.
 */
// Payment and fulfilment are different questions — "have they paid" and "has it
// gone out" — so they get the same chip but never share one.
function StatusChip({ kind, value }) {
  const label = (value || (kind === 'ship' ? 'unfulfilled' : 'unknown')).replace(/_/g, ' ')
  const tone = kind === 'ship'
    ? (value === 'fulfilled' ? 'bg-green-500/10 text-green-600'
      : value === 'partial' ? 'bg-amber-500/10 text-amber-600'
      : 'bg-gray-500/10 text-gray-500')
    : ({ paid: 'bg-green-500/10 text-green-600',
         partially_paid: 'bg-blue-500/10 text-blue-500',
         partially_refunded: 'bg-amber-500/10 text-amber-600',
         pending: 'bg-amber-500/10 text-amber-600',
         refunded: 'bg-red-500/10 text-red-500',
         voided: 'bg-red-500/10 text-red-500' }[value] || 'bg-gray-500/10 text-gray-500')
  return (
    <span className={clsx('inline-block text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded', tone)}>
      {label}
    </span>
  )
}

function Section({ title, children, className }) {
  return (
    <div className={className}>
      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-gray-400 mb-2.5">{title}</p>
      {children}
    </div>
  )
}

// ─── Expanded order ──────────────────────────────────────────
// Limited by what orders_cache holds: line TITLES, but no per-line price or
// quantity. So this shows order-level money, which reconciles, and lists the
// items without inventing figures against them.
function OrderDetail({ order: o }) {
  const cur = o.currency || 'KES'
  const money = v => `${cur} ${formatKES(v)}`

  // gross - discounts + delivery = total. Verified on 133,360 of 133,360
  // orders. Tax is deliberately absent: gross_sales is total_line_items_price
  // and this store prices VAT-inclusive, so the VAT is already inside gross.
  // Adding it as a fourth line reconciles only 2.3% of orders.
  const lines = [
    { label: `Items (${o.items ?? o.products?.length ?? 0})`, value: o.gross_sales, sign: 1 },
    { label: 'Discounts', value: o.discounts, sign: -1, hideIfZero: true },
    { label: 'Delivery', value: o.shipping, sign: 1, zeroLabel: 'Free' },
  ].filter(l => l.value !== null && l.value !== undefined && !(l.hideIfZero && !l.value))

  // Does it add up for THIS order? If a row ever fails to reconcile the panel
  // says so rather than showing a breakdown that quietly disagrees with the
  // total printed beside it.
  const sum = lines.reduce((a, l) => a + l.sign * (l.value || 0), 0)
  const reconciles = Math.abs(sum - (o.total || 0)) <= 1

  return (
    <div className="bg-[var(--surface-2)] px-2 pb-5 pt-1">
      <div className="pl-[21px] pr-1">
        {(o.cancelled_at || o.is_test) && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2">
            <AlertCircle size={13} className="text-red-500 shrink-0 mt-px" />
            <p className="text-[11px] text-red-500 leading-relaxed">
              {o.is_test && 'Test order. '}
              {o.cancelled_at && `Cancelled ${formatFullDate(o.cancelled_at)}. `}
              Listed for completeness, excluded from spend totals.
            </p>
          </div>
        )}

        <div className="grid gap-6 sm:grid-cols-2">
          <Section title="Breakdown">
            <dl className="space-y-2">
              {lines.map(l => (
                <div key={l.label} className="flex justify-between gap-4 text-xs">
                  <dt className="text-gray-500">{l.label}</dt>
                  <dd className="text-gray-900 font-medium tabular-nums shrink-0">
                    {l.value === 0 && l.zeroLabel
                      ? l.zeroLabel
                      : `${l.sign < 0 ? '−' : ''}${money(l.value)}`}
                  </dd>
                </div>
              ))}
              <div className="flex justify-between gap-4 pt-2.5 mt-2.5 border-t border-gray-200">
                <dt className="text-xs font-bold text-gray-900">Total charged</dt>
                <dd className="text-sm font-bold text-gray-900 tabular-nums shrink-0">{money(o.total)}</dd>
              </div>
              {!!o.refunded && (
                <div className="flex justify-between gap-4 text-xs pt-2 border-t border-gray-200">
                  <dt className="text-red-500 font-semibold">Refunded since</dt>
                  <dd className="text-red-500 font-semibold tabular-nums shrink-0">−{money(o.refunded)}</dd>
                </div>
              )}
            </dl>

            {o.tax !== null && o.tax !== undefined && (
              <p className="text-[11px] text-gray-400 leading-relaxed mt-2.5">
                Includes {money(o.tax)} VAT, already inside the item price.
              </p>
            )}
            {!reconciles && (
              <p className="text-[11px] text-amber-600 leading-relaxed mt-2">
                These lines sum to {money(sum)}, not the total charged. Treat the
                total as authoritative and re-sync this order.
              </p>
            )}

            <div className="flex gap-6 mt-5">
              {[['Payment', 'pay', o.financial_status],
                ['Fulfilment', 'ship', o.fulfillment_status]].map(([label, kind, value]) => (
                <div key={label}>
                  <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{label}</p>
                  <StatusChip kind={kind} value={value} />
                </div>
              ))}
            </div>
          </Section>

          <Section title={`Items in this order${o.products?.length ? ` (${o.products.length})` : ''}`}>
            {o.products?.length > 0 ? (
              <ol className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {o.products.map((name, i) => (
                  <li key={i} className="flex gap-2 text-xs text-gray-600 leading-relaxed">
                    <span className="text-gray-400 tabular-nums shrink-0">{i + 1}</span>
                    <span>{name}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-xs text-gray-400">No line items recorded.</p>
            )}
            {o.products?.length > 0 && o.items != null && o.products.length !== o.items && (
              <p className="text-[11px] text-gray-400 mt-3">
                {o.items} units across {o.products.length} lines.
              </p>
            )}
          </Section>
        </div>
      </div>
    </div>
  )
}

// A score of 5 does not mean "top 20%" when a tie group is bigger than a fifth
// of the base — 54% of buyers have exactly one order and all of them score 1.
// The stored percentile is the only honest way to caption a pillar.
function pctCaption(pct, verb) {
  if (pct == null) return 'Not scored yet'
  if (pct >= 100) return `Ahead of every other buyer — ${verb} all of them`
  if (pct <= 0) return `At the bottom of the base — nobody ${verb} less`
  return `${verb.charAt(0).toUpperCase()}${verb.slice(1)} ${pct}% of buyers`
}

// Klaviyo list memberships are real but they are not about the customer — they
// are about which email segment the marketing tool put them in. Kept, ranked
// last, and folded behind a count so the tags that describe the person are the
// ones on screen.
function TagRow({ tags }) {
  const [showLists, setShowLists] = useState(false)
  const isList = t => /^klaviyo_list/i.test(t)
  const signal = tags.filter(t => !isList(t))
  const lists = tags.filter(isList)
  const shown = showLists ? [...signal, ...lists] : signal.slice(0, 12)
  const hiddenSignal = showLists ? 0 : Math.max(0, signal.length - 12)

  return (
    <div className="mt-5 pt-4 border-t border-gray-100">
      <div className="flex items-start gap-2">
        <span className="text-[11px] font-bold uppercase tracking-widest text-gray-400 mt-1 shrink-0">Tags</span>
        <div className="flex flex-wrap gap-1.5 items-center">
          {shown.map((t, i) => (
            <span key={i} className={clsx(
              'inline-flex items-center text-[12px] px-2 py-0.5 rounded-md',
              isList(t) ? 'bg-gray-500/10 text-gray-500' : 'bg-gray-100 text-gray-700'
            )}>
              {t}
            </span>
          ))}
          {hiddenSignal > 0 && (
            <span className="text-[12px] text-gray-500 font-semibold px-1">+{hiddenSignal} more</span>
          )}
          {lists.length > 0 && (
            <button
              type="button"
              onClick={() => setShowLists(v => !v)}
              className="text-[12px] text-gray-500 hover:text-gray-900 underline underline-offset-2 px-1"
            >
              {showLists
                ? 'Hide email list memberships'
                : `${lists.length} email list membership${lists.length === 1 ? '' : 's'}`}
            </button>
          )}
          {signal.length === 0 && !showLists && (
            <span className="text-[12px] text-gray-400">No descriptive tags</span>
          )}
        </div>
      </div>
    </div>
  )
}


export function CustomerDetailView({ customerId, onClose }) {
  const id = customerId
  const navigate = useNavigate()

  const [customer, setCustomer] = useState(null)
  const [orders, setOrders] = useState([])
  const [expandedOrder, setExpandedOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(1)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const [cData, oData] = await Promise.all([
          getCustomer(id),
          getCustomerOrders(id),
        ])
        if (cancelled) return
        setCustomer(cData.customer)
        setOrders(oData.orders || [])
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [id])

  // The monthly rollup that used to live here is gone. It summed every order
  // in the list, voided and pending included, so it disagreed with the KPI
  // above it. The series now comes from /profile as spend_over_time, computed
  // over paid orders only and gap-filled, and is drawn by CustomerProfileExtras.


  // Pagination
  const totalPages = Math.max(1, Math.ceil(orders.length / ORDERS_PER_PAGE))
  const pagedOrders = useMemo(() => {
    const start = (page - 1) * ORDERS_PER_PAGE
    return orders.slice(start, start + ORDERS_PER_PAGE)
  }, [orders, page])

  // Reset page when orders change
  useEffect(() => { setPage(1) }, [orders.length])

  if (loading) {
    return (
      <div className="space-y-6 w-full">
        <div className="card h-48 bg-gray-50 animate-pulse rounded-2xl" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="card h-28 bg-gray-50 animate-pulse" />)}
        </div>
        <div className="card h-72 bg-gray-50 animate-pulse" />
      </div>
    )
  }

  if (error || !customer) {
    return (
      <div className="space-y-4 w-full">
        <button onClick={onClose} className="btn-ghost flex items-center gap-2 text-xs">
          <ArrowLeft size={13} /> Back
        </button>
        <div className="card p-12 text-center">
          <AlertCircle size={36} className="text-red-400 mx-auto mb-3" />
          <p className="text-sm font-medium text-gray-900">{error || 'Customer not found'}</p>
        </div>
      </div>
    )
  }

  const meta = SEGMENT_META[customer.segment] || SEGMENT_META.regular
  const SegIcon = meta.icon
  const initials = ((customer.first_name?.[0] || customer.name?.[0] || '?') + (customer.last_name?.[0] || '')).toUpperCase()

  const recScore = customer.rfm_r ?? 0
  const freqScore = customer.rfm_f ?? 0
  const monScore = customer.rfm_m ?? 0
  const rfmTotal = recScore + freqScore + monScore

  // Next milestone copy.
  //
  // The tone is the colour of the segment the milestone points AT, not the one
  // the customer is in now — "2 more orders to reach Loyal" is tinted Loyal, so
  // the badge shows where they are heading. Taken from SEGMENT_META rather than
  // written out, because these were hardcoded to the old palette and stayed
  // green/pink/amber after it changed; a hint that names Loyal in its text and
  // shows a different colour beside it is worse than an uncoloured one.
  const toneFor = (seg) => `${SEGMENT_META[seg].color} ${SEGMENT_META[seg].bg}`

  // Only where there is a distance to measure.
  //
  // Every branch below used to produce something, and four of them were a fixed
  // sentence per segment: VIP got "VIP — protect this relationship", at_risk got
  // "Win-back campaign needed". That is a lookup on one field, rendered as
  // advice, two inches under a badge showing the same field. It cannot be wrong
  // and so it cannot be useful — the same reason Suggested Action was removed.
  //
  // What survives computes how far the customer is from the next threshold,
  // which is a fact about this person and is not shown anywhere else.
  let nextMilestone = null
  const LOYAL_ORDERS = 5
  if (customer.segment === 'never_bought') {
    nextMilestone = { label: 'No orders yet — first purchase moves them to New',
                      icon: Sparkles, tone: toneFor('new') }
  } else if (customer.segment === 'new' || customer.segment === 'regular') {
    const more = LOYAL_ORDERS - (customer.total_orders || 0)
    if (more > 0) {
      nextMilestone = { label: `${more} more order${more === 1 ? '' : 's'} to reach Loyal`,
                        icon: Heart, tone: toneFor('loyal') }
    }
  } else if (customer.segment === 'loyal' && customer.vip_threshold > 0) {
    const gap = customer.vip_threshold - (customer.total_spent || 0)
    if (gap > 0) {
      nextMilestone = { label: `KES ${formatKES(gap)} more spend to reach VIP`,
                        icon: Crown, tone: toneFor('vip') }
    }
  }


  return (
    <div className="space-y-6 w-full">
      {/* The "All Customers" back button is gone. The detail opens as a
          slide-over with the table still visible behind it and its own close
          control in the header, so a second way out was one control too many. */}

      {/* ─── HERO BANNER ────────────────────────────────────── */}
      <div className="relative card overflow-hidden">
        {/* Gradient accent stripe */}
        <div className={clsx('absolute inset-x-0 top-0 h-1 bg-gradient-to-r', meta.accent)} />

        <div className="p-5 sm:p-6">
          <div className="flex flex-col md:flex-row md:items-start gap-5">
            {/* Avatar */}
            <div className="relative shrink-0">
              <div className={clsx(
                'w-20 h-20 sm:w-24 sm:h-24 rounded-2xl flex items-center justify-center text-3xl font-bold text-white shadow-lg bg-gradient-to-br ring-1',
                meta.accent, meta.ring,
              )}>
                {initials}
              </div>
              <div className={clsx(
                'absolute -bottom-1 -right-1 w-7 h-7 rounded-full flex items-center justify-center shadow-md bg-white border',
                meta.border,
              )}>
                <SegIcon size={13} className={meta.color} />
              </div>
            </div>

            {/* Identity */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 truncate">{customer.name}</h1>
                <span className={clsx('inline-flex items-center gap-1 text-[12px] font-bold px-2 py-0.5 rounded-md', meta.bg, meta.color)}>
                  <SegIcon size={10} />
                  {meta.label}
                </span>
                {/* "Marketing opt-in" said neither what was opted into nor by
                    whom. It reads as blanket permission to contact this person,
                    and it is not: it mirrors Shopify's
                    email_marketing_consent.state, so it covers EMAIL only.
                    Nothing here implies consent to message them on Instagram or
                    WhatsApp, which is what this product actually does.

                    It also only rendered when true, so "not subscribed" and
                    "never synced" looked identical — an absent badge on 40% of
                    customers meaning either. Both states now show. */}
                <span
                  title="From Shopify's email marketing consent. Covers email only — not Instagram or WhatsApp."
                  className={clsx(
                    'inline-flex items-center gap-1 text-[12px] font-medium px-2 py-0.5 rounded-md border',
                    customer.accepts_marketing
                      ? 'bg-green-500/10 text-green-600 border-green-500/20'
                      : 'bg-gray-500/10 text-gray-500 border-gray-500/20'
                  )}
                >
                  {customer.accepts_marketing ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
                  Email marketing: {customer.accepts_marketing ? 'subscribed' : 'not subscribed'}
                </span>
              </div>

              {/* Contact line */}
              <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3 text-xs text-gray-600">
                {customer.email && (
                  <a href={`mailto:${customer.email}`} className="flex items-center gap-1.5 hover:text-brand-600 transition-colors">
                    <Mail size={12} /> {customer.email}
                  </a>
                )}
                {customer.phone && (
                  <a href={`tel:${customer.phone}`} className="flex items-center gap-1.5 hover:text-brand-600 transition-colors">
                    <Phone size={12} /> {customer.phone}
                  </a>
                )}
                {customer.location && (
                  <span className="flex items-center gap-1.5">
                    <MapPin size={12} /> {customer.location}
                  </span>
                )}
                {customer.created_at && (
                  <span className="flex items-center gap-1.5">
                    <Calendar size={12} /> Joined {formatFullDate(customer.created_at)}
                  </span>
                )}
              </div>

              {/* Next milestone callout */}
              {nextMilestone && (
                <div className={clsx('inline-flex items-center gap-1.5 mt-4 px-3 py-1.5 rounded-lg text-xs font-semibold', nextMilestone.tone)}>
                  <nextMilestone.icon size={12} />
                  {nextMilestone.label}
                </div>
              )}

              {/* Email action */}
              {customer.email && (
                <div className="mt-4">
                  
                  <a href={`mailto:${customer.email}`}
                    className="inline-flex items-center gap-2 bg-black hover:bg-gray-800 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors"
                  >
                    <Mail size={13} />
                    Email {customer.first_name || customer.name?.split(' ')[0] || 'customer'}
                  </a>
                </div>
              )}
            </div>
          </div>

          {/* Tags.
              slice(0, 12) took whatever order Shopify sent. 43% of all tag
              values store-wide are klaviyo_list_* memberships — plumbing from
              the email tool — and "klaviyo_list_sz profiles" alone sits on 54%
              of every customer. On this customer they filled four of the seven
              visible slots and pushed "2 refunds" and "Gold VIP" out of view.
              Nothing is hidden; the list memberships just stop going first. */}
          {customer.tags?.length > 0 && (
            <TagRow tags={customer.tags} />
          )}
        </div>
      </div>

      {/* ─── KPI CARDS ──────────────────────────────────────── */}
      {/* Three cards, not four. Lifetime Spend is gone: the Monetary pillar in
          the RFM breakdown immediately below already states the same figure
          ("KES 4,752,031 lifetime spend"), and the header carries the segment
          badge that the number determines. Twice on one screen, two inches
          apart. */}
      <div className="grid grid-cols-3 gap-3">
        <KpiCard icon={ShoppingBag} label="Total Orders" value={customer.total_orders || 0}
                 sub={customer.first_order_date ? `First ${formatFullDate(customer.first_order_date)}` : 'No orders yet'}
                 accent="from-blue-400 to-blue-600" />
        {/* The subtitle used to read "Across 529 orders" while the figure was
            total_spent (net of refunds, paid orders only) divided by 529. Only
            336 of those were paid, so the card asserted a denominator that was
            not the one used and came out 58% low. aov_basis says which
            denominator the server could actually use. */}
        <KpiCard icon={Repeat} label="Average Order Value" value={`KES ${formatKES(customer.aov)}`}
                 sub={customer.aov_basis === 'paid'
                        ? `Across ${formatCount(customer.aov_orders)} paid orders`
                        : customer.aov_basis === 'all'
                          ? `Across all ${formatCount(customer.aov_orders)} orders — paid count not yet synced`
                          : '—'}
                 accent="from-violet-400 to-violet-600" />
        {/* Was "3d ago" over "3 days ago". */}
        <KpiCard icon={Clock} label="Last Order" value={customer.last_order_date ? formatDateAgo(customer.last_order_date) : 'Never'}
                 sub={customer.last_order_date ? formatFullDate(customer.last_order_date) : 'Yet to convert'}
                 accent="from-amber-400 to-amber-600" />
      </div>

      {/* ─── RFM BREAKDOWN ──────────────────────────────────── */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <Target size={14} className="text-brand-500" /> RFM Score Breakdown
          </h2>
          <span className="text-xs text-gray-500">
            Total <span className="font-bold text-gray-900">{rfmTotal}</span><span className="text-gray-400">/15</span>
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* The captions restated the two KPI cards an inch above — "529
              lifetime orders" under Total Orders 529, "Last purchase 3 days
              ago" under Last Order 3d ago. Three lines of screen saying a
              number twice.

              They now show the percentile, which is what the score actually
              encodes and appears nowhere else. It also replaces a scaleLabel
              that was repeated verbatim three times and was not true: "top 20%
              = 5" is wrong wherever a tie group is bigger than a fifth of the
              base, and 54% of buyers are tied at one order. */}
          <RfmPillar icon={Clock} label="Recency" score={recScore}
                     caption={pctCaption(customer.rfm_r_pct, 'bought more recently than')}
                     scaleLabel={customer.last_order_date
                       ? 'Ranked against every buyer'
                       : 'No purchase history'} />
          <RfmPillar icon={Repeat} label="Frequency" score={freqScore}
                     caption={pctCaption(customer.rfm_f_pct, 'has more orders than')}
                     scaleLabel="Ranked against every buyer" />
          <RfmPillar icon={TrendingUp} label="Monetary" score={monScore}
                     caption={pctCaption(customer.rfm_m_pct, 'has spent more than')}
                     scaleLabel="Ranked against every buyer" />
        </div>
      </div>

      {/* ─── SUGGESTED ACTION · SPEND BY BRAND · TOP ITEMS ──── */}
      <CustomerProfileExtras customerId={id} />

      {/* The Spending Trend chart moved into CustomerProfileExtras, which is
          where the corrected server-side series is already fetched. Keeping it
          here meant a second component re-deriving the same numbers by hand. */}

      {/* ─── ORDER HISTORY ──────────────────────────────────── */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <ShoppingBag size={14} className="text-brand-500" /> Order History
          </h2>
          {orders.length > 0 && (
            <span className="text-xs text-gray-500">
              <span className="font-bold text-gray-900">{formatCount(orders.length)}</span> total
            </span>
          )}
        </div>

        {orders.length === 0 ? (
          <div className="text-center py-12">
            <Package size={28} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500 font-medium">No orders yet</p>
            <p className="text-xs text-gray-400 mt-1">
              {customer.total_orders > 0
                ? 'Shopify shows orders but local cache is empty — try syncing orders'
                : 'This customer has not placed any orders yet'}
            </p>
          </div>
        ) : (
          <>
            {/* A list, not a table.
                The table was min-w-[720px] inside a slide-over about 530px
                wide, so it scrolled sideways permanently and the expanded panel
                — living in a colSpan cell — inherited that width and had its
                right-hand column cut off mid-word. A list has no column widths
                to satisfy, so it fits the sheet and the full page alike. */}
            <div className="divide-y divide-gray-100 border-t border-gray-100">
              {pagedOrders.map(o => {
                const open = expandedOrder === o.id
                return (
                  <div key={o.id}>
                    <button
                      type="button"
                      onClick={() => setExpandedOrder(open ? null : o.id)}
                      aria-expanded={open}
                      className={clsx(
                        'w-full text-left px-2 py-3 transition-colors',
                        // Not bg-gray-50/70. index.css darkens .bg-gray-50 and
                        // .hover\:bg-gray-50:hover, but an opacity modifier compiles
                        // to .hover\:bg-gray-50\/70:hover, which those selectors do
                        // not match - so it fell through to raw Tailwind #f9fafb and
                        // flashed near-white on a black row. The variable is correct
                        // in both themes and needs no override to exist.
                        open ? 'bg-[var(--surface-2)]' : 'hover:bg-[var(--surface-2)]'
                      )}
                    >
                      <div className="flex items-baseline gap-2">
                        <ChevronRight
                          size={13}
                          className={clsx('text-gray-400 shrink-0 transition-transform self-center',
                                          open && 'rotate-90')}
                        />
                        <span className="text-sm font-bold text-gray-900">#{o.order_number}</span>
                        <span className="text-[11px] text-gray-400">{formatFullDate(o.date)}</span>
                        <span className="flex-1" />
                        <span className="text-sm font-bold text-gray-900 tabular-nums shrink-0">
                          {o.currency || 'KES'} {formatKES(o.total)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 pl-[21px]">
                        <p className="text-xs text-gray-500 truncate flex-1 min-w-0">
                          {o.items} item{o.items === 1 ? '' : 's'}
                          {o.products?.length > 0 && ` · ${o.products[0]}`}
                          {o.products?.length > 1 && ` +${o.products.length - 1}`}
                        </p>
                        <div className="flex gap-1 shrink-0">
                          <StatusChip kind="pay" value={o.financial_status} />
                          <StatusChip kind="ship" value={o.fulfillment_status} />
                        </div>
                      </div>
                    </button>
                    {open && <OrderDetail order={o} />}
                  </div>
                )
              })}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100 flex-wrap gap-3">
                <p className="text-xs text-gray-500">
                  Showing {(page - 1) * ORDERS_PER_PAGE + 1}–{Math.min(page * ORDERS_PER_PAGE, orders.length)} of {formatCount(orders.length)}
                </p>
                <div className="flex gap-1 items-center">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40">
                    <ChevronLeft size={14} />
                  </button>

                  {(() => {
                    const delta = 1
                    const left = Math.max(2, page - delta)
                    const right = Math.min(totalPages - 1, page + delta)
                    const pages = [1]
                    if (left > 2) pages.push('...')
                    for (let i = left; i <= right; i++) pages.push(i)
                    if (right < totalPages - 1) pages.push('...')
                    if (totalPages > 1) pages.push(totalPages)

                    return pages.map((p, i) =>
                      p === '...' ? (
                        <span key={`el-${i}`} className="px-2 text-xs text-gray-400">…</span>
                      ) : (
                        <button key={p} onClick={() => setPage(p)}
                                className={clsx(
                                  'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                                  page === p ? 'bg-black text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                )}>
                          {p}
                        </button>
                      )
                    )
                  })()}

                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                          className="btn-ghost px-2 py-1 text-xs disabled:opacity-40">
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}


/**
 * Route wrapper for /customers/:id — the shareable, refreshable URL.
 */
export default function CustomerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  return <CustomerDetailView customerId={id} onClose={() => navigate('/customers')} />
}
