import { useState, useEffect, useRef, useCallback, useContext, Fragment } from 'react'
import {
  Instagram, Smartphone, MessageCircle, Bot, User, UserCheck,
  RefreshCw, Edit, Send, ArrowLeft, Info, Loader2, Users, X, Trash2,
  CheckCircle2, RotateCcw, ExternalLink, MessageSquare, Zap, Clock, Search,
  AlertCircle, ImageOff, Inbox,
} from 'lucide-react'
import clsx from 'clsx'
import ChannelIcon from '../components/ChannelIcon'
import {
  listConversations, getConversation, sendReply, toggleAI, markRead,
  assignConversation, unassignConversation, listAgents, deleteMessage, editMessage,
  fetchInstagramMedia, updateConversationStatus,
  searchShopifyCustomers, linkShopifyCustomer, unlinkShopifyCustomer,
} from '../api/messages'
import { SkeletonCard } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'
import { useAuth } from '../context/AuthContext'
import { parseBackendTime, formatTimeOfDay, formatTimeAgo, formatDateAgo } from '../utils/time'

// Conversations carry `platform` (an alias of the DB `channel`) for display.
//
// The local FbIcon/TikTokIcon and this mapping are gone — Dashboard.jsx and
// Channels.jsx each had their own, with different glyphs and sizes for the same
// channel. ChannelIcon is the one definition.
const platformIcon = (p) => <ChannelIcon channel={p} size="xs" bare />

const platformLabel = (p) => {
  if (p === 'instagram_dm')      return 'Instagram DM'
  if (p === 'instagram_comment') return 'IG Comment'
  if (p === 'whatsapp')          return 'WhatsApp'
  if (p === 'facebook_dm')       return 'Facebook DM'
  if (p === 'facebook_comment')  return 'FB Comment'
  if (p === 'tiktok_dm')         return 'TikTok DM'
  if (p === 'tiktok_comment')    return 'TikTok Comment'
  return p
}

// Day bucketing for the chat thread. Local dates, so "Today" means the
// reader's today rather than UTC's.
const dayKey = (iso) => {
  const d = iso ? parseBackendTime(iso) : null
  return d ? `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}` : null
}

const formatDayLabel = (iso) => {
  const d = iso ? parseBackendTime(iso) : null
  if (!d) return ''
  const today = new Date()
  const yest = new Date(today); yest.setDate(yest.getDate() - 1)
  if (dayKey(iso) === `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`) return 'Today'
  if (dayKey(iso) === `${yest.getFullYear()}-${yest.getMonth()}-${yest.getDate()}`) return 'Yesterday'
  const sameYear = d.getFullYear() === today.getFullYear()
  return d.toLocaleDateString('en-KE', {
    weekday: 'short', day: 'numeric', month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  })
}

const statusBadge = (s) => {
  const baseClass = "text-[11px] font-semibold px-1.5 py-0.5 rounded-md"
  if (s === 'ai_replied')     return <span className={`${baseClass} bg-brand-100 text-brand-600`}>AI Replied</span>
  if (s === 'active')         return <span className={`${baseClass} bg-brand-100 text-brand-600`}>Active</span>
  if (s === 'human_override') return <span className={`${baseClass} bg-amber-100 text-amber-600`}>Human</span>
  if (s === 'resolved')       return <span className={`${baseClass} bg-gray-100 text-gray-600`}>Resolved</span>
  if (s === 'pending')        return <span className={`${baseClass} bg-red-100 text-red-600`}>Pending</span>
}

// Flags a conversation that needs human intervention, and how urgent.
// The ONLY signal that a human is needed is the AI being off on this
// conversation — same thing the handler badge shows as "Human Agent".
// (A manual human reply flips status to 'human_override' but leaves the AI
// on; that's still Claude-handled, so it must never be flagged.)
function attentionInfo(conv) {
  if (!conv || conv.status === 'resolved') return null
  if (conv.ai_enabled) return null        // AI still handling it → no flag
  const escalated = conv.handoff_reason === 'ai_detected'
  const queued = !conv.assigned_to
  if (escalated) return { urgent: true, badge: 'Escalated' }
  if (queued)    return { urgent: true, badge: 'In queue' }
  return { urgent: false, badge: null }   // handed off but assigned — border only
}

// Status filters for the conversation list. Each is a plain question about
// where a conversation stands, rather than the old single "needs attention"
// toggle whose rule you had to know in advance.
// The buckets themselves now live in SQL (app/messages.py::_bucket_filter);
// keeping a second copy here is what let the two definitions drift apart.

// Rows per page in the conversation list.
const PAGE_SIZE = 20

// How often the open conversation re-fetches.
//
// It used to be a flat 3s setInterval that ran forever — 20 requests a minute
// per open chat, per agent, whether or not anyone was looking at the screen.
// Gunicorn here runs 2 workers x 4 threads = 8 concurrent slots, so ten agents
// with a chat open was 200 req/min of pure polling before anyone did any work.
//
// Now: 3s while the conversation is live, dropping to 20s once nothing has
// changed for two minutes, and stopping altogether while the tab is hidden.
// Switching back to the tab refreshes immediately and resets to fast.
const POLL_FAST_MS = 3000
const POLL_SLOW_MS = 20000
const POLL_IDLE_BEFORE_BACKOFF = 40      // 40 x 3s = 2 minutes

const STATUS_FILTERS = [
  { key: 'unclaimed', label: 'Unclaimed',  dot: 'bg-red-500'   },
  { key: 'human',     label: 'With agent', dot: 'bg-amber-500' },
  { key: 'ai',        label: 'AI handling', dot: 'bg-brand-500',
    // Renamed while the master switch is off. "AI handling 37" is a false
    // statement then: nothing is handling them, and because Unclaimed requires
    // ai_enabled = false they are not offered to agents either.
    offLabel: 'Stalled · AI off', offDot: 'bg-red-500' },
  { key: 'resolved',  label: 'Resolved',   dot: 'bg-gray-400'  },
]

// First name only. "Brian" is what a colleague is called; "Brian Otieno" is
// what a form field is called, and neither the full name nor an email fits in a
// badge this size.
const firstName = (person) => {
  if (!person) return null
  const full = (person.full_name || '').trim()
  if (full) return full.split(/\s+/)[0]
  // No name on the account — the email's local part is still a person, where
  // "Unknown" would be a dead end.
  const local = (person.email || '').split('@')[0]
  return local ? local.charAt(0).toUpperCase() + local.slice(1) : null
}

// `terse` drops the "Unclaimed" case, for the list row where the attention
// badge beside it already says "In queue" — two chips saying the same thing is
// noise, not emphasis.
const handlerBadge = (conv, { terse = false } = {}) => {
  const baseClass = "text-[11px] font-semibold px-1.5 py-0.5 rounded-md"
  if (conv.status === 'resolved') {
    return <span className={`${baseClass} bg-gray-100 text-gray-600`}>Resolved</span>
  }
  if (!conv.ai_enabled) {
    // Who has it, by name. "Human Agent" was the same word whether someone had
    // claimed the conversation or nobody had — so an unclaimed thread sat in
    // the queue wearing a badge that said an agent was on it. The two states
    // are now visibly different, which is the whole point of the badge.
    const who = firstName(conv.assignee)
    if (who) return <span className={`${baseClass} bg-amber-100 text-amber-700`}>{who}</span>
    return terse
      ? null
      : <span className={`${baseClass} bg-red-100 text-red-700`}>Unclaimed</span>
  }
  return <span className={`${baseClass} bg-brand-100 text-brand-700`}>AI</span>
}

// Bare URLs in message text → clickable links. Split on the global regex,
// test with a non-global one (a /g regex is stateful across .test calls).
const URL_SPLIT_RE = /(https?:\/\/[^\s<>()"']+)/g
const IS_URL_RE = /^https?:\/\//

// ── Per-comment post preview ──────────────────────────────────────
// A tiny cache so multiple comments on the same post don't refetch.
const _mediaCache = new Map()


// ── Shopify customer link ─────────────────────────────────────────────────
// The one join in this product a machine cannot make. An IGSID, a phone number
// and an email share no key, so a person who can see both sides says who this
// is, and we record who said it.
function ShopifyLinkCard({ conv }) {
  // Owns the linked customer locally.
  //
  // It first called setActiveConv from the page component — which is not in
  // scope here: this renders inside ContextContent, a module-level component
  // that receives only `conv`. The card threw "setActiveConv is not defined"
  // the moment anyone linked or unlinked.
  //
  // Local state rather than drilling a setter through ContextContent: the card
  // is the only thing that changes this value, and the prop would exist purely
  // to hand it back up to be handed down again.
  const [linked, setLinked] = useState(conv.linked_customer || null)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Debounced, because this runs while a customer is waiting and the table has
  // 162,186 rows — a query per keystroke would make the agent wait too.
  useEffect(() => {
    setLinked(conv.linked_customer || null)
    setOpen(false); setQ(''); setResults([])
  }, [conv.id, conv.linked_customer])

  useEffect(() => {
    if (!open || q.trim().length < 2) { setResults([]); return }
    const t = setTimeout(() => {
      searchShopifyCustomers(q.trim())
        .then(d => setResults(d.customers || []))
        .catch(e => setError(e.message))
    }, 250)
    return () => clearTimeout(t)
  }, [q, open])

  const doLink = async (shopifyId) => {
    setBusy(true); setError(null)
    try {
      const d = await linkShopifyCustomer(conv.id, shopifyId)
      setLinked(d.linked_customer)
      setOpen(false); setQ(''); setResults([])
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const doUnlink = async () => {
    setBusy(true); setError(null)
    try {
      await unlinkShopifyCustomer(conv.id)
      setLinked(null)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <header className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-100 bg-gray-50">
        <Users size={11} className="text-gray-400" />
        <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">Shopify customer</h3>
      </header>
      <div className="px-3 py-2.5 space-y-3">
      {linked && !linked.stale ? (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-gray-900">{linked.name}</p>
          {linked.email && <p className="text-[11px] text-gray-500 break-all">{linked.email}</p>}
          <div className="flex items-center justify-between gap-2 pt-1">
            <span className="text-[11px] text-gray-500">Spent</span>
            {/* Shopify's figure, unmodified. */}
            <span className="text-xs font-semibold text-gray-900">
              KES {new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(linked.total_spent || 0)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-gray-500">Orders</span>
            <span className="text-xs font-semibold text-gray-900">{linked.total_orders}</span>
          </div>
          <button onClick={doUnlink} disabled={busy}
            className="text-[11px] text-gray-400 hover:text-red-600 transition-colors pt-1 disabled:opacity-50">
            {busy ? 'Removing…' : 'Not this person? Unlink'}
          </button>
        </div>
      ) : linked?.stale ? (
        /* Linked to an id the cache has not re-fetched. Saying "not linked"
           here would invite a second link to the same person. */
        <div className="space-y-1.5">
          <p className="text-[11px] text-amber-600">
            Linked to Shopify customer {linked.shopify_customer_id}, but that record
            isn't in our cache yet — run a customer sync.
          </p>
          <button onClick={doUnlink} disabled={busy}
            className="text-[11px] text-gray-400 hover:text-red-600 transition-colors">Unlink</button>
        </div>
      ) : !open ? (
        <button onClick={() => setOpen(true)}
          className="text-xs text-brand-600 hover:text-brand-700 font-semibold transition-colors">
          + Link to a Shopify customer
        </button>
      ) : (
        <div className="space-y-2">
          <input
            autoFocus
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Name, email or phone…"
            className="w-full px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white text-xs text-gray-900 placeholder-gray-400 focus:outline-none focus:border-brand-500"
          />
          <div className="max-h-52 overflow-y-auto space-y-1">
            {results.map(c => (
              <button key={c.shopify_customer_id} onClick={() => doLink(c.shopify_customer_id)}
                disabled={busy}
                className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50">
                <p className="text-xs font-semibold text-gray-900 truncate">{c.name}</p>
                <p className="text-[11px] text-gray-500 truncate">{c.email || c.phone || '—'}</p>
                {/* Spend and order count shown while choosing, because two
                    people share a name far more often than they share a
                    purchase history. */}
                <p className="text-[11px] text-gray-400">
                  {c.total_orders} orders · KES {new Intl.NumberFormat('en-KE', { maximumFractionDigits: 0 }).format(c.total_spent || 0)}
                </p>
              </button>
            ))}
            {q.trim().length >= 2 && results.length === 0 && (
              <p className="text-[11px] text-gray-400 px-2 py-1">No match in the customer cache.</p>
            )}
          </div>
          <button onClick={() => { setOpen(false); setQ('') }}
            className="text-[11px] text-gray-400 hover:text-gray-600">Cancel</button>
        </div>
      )}
      {error && <p className="text-[11px] text-red-600 mt-1.5">{error}</p>}
      </div>
    </section>
  )
}

function CommentPostPreview({ mediaId }) {
  const [post, setPost] = useState(() => _mediaCache.get(mediaId) || null)
  // Why the fetch failed, so the card can say so. It used to `.catch(() => {})`
  // — which meant a failing lookup left the skeleton pulsing forever, and the
  // agent had no way to tell "still loading" from "this will never arrive".
  const [failed, setFailed] = useState(null)
  // ALL hooks live above the early returns below. React counts hook calls per
  // render and errors (#300, "rendered fewer hooks than expected") the moment a
  // render takes a path that skips one — which is what an early return added
  // above a useState does. Crashed the whole page as soon as a post lookup
  // failed, i.e. exactly when the new error state was meant to show.
  const [imgFailed, setImgFailed] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!mediaId || _mediaCache.has(mediaId)) return
    let cancelled = false
    fetchInstagramMedia(mediaId)
      .then(data => {
        if (cancelled) return
        if (data?.error) { setFailed(data.error); return }
        _mediaCache.set(mediaId, data)
        setPost(data)
      })
      .catch(err => { if (!cancelled) setFailed(err?.message || 'Could not load the post') })
    return () => { cancelled = true }
  }, [mediaId])

  if (failed && !post) {
    return (
      <div className="w-[22rem] max-w-full mb-2 rounded-xl border border-dashed border-gray-300 px-3 py-2.5">
        <p className="text-xs font-semibold text-gray-500">Original post unavailable</p>
        <p className="text-[11px] text-gray-400 mt-0.5 leading-snug break-words">{failed}</p>
      </div>
    )
  }

  if (!post) {
    return (
      <div className="w-[22rem] max-w-full mb-2 rounded-xl border border-gray-200 p-3 space-y-2">
        <div className="h-3 w-24 rounded bg-gray-100 animate-pulse" />
        <div className="h-28 rounded-lg bg-gray-100 animate-pulse" />
      </div>
    )
  }

  // VIDEO and CAROUSEL_ALBUM have no media_url that renders as a still, so the
  // thumbnail is the only usable image for them.
  const image = post.media_type === 'IMAGE'
    ? (post.media_url || post.thumbnail_url)
    : (post.thumbnail_url || post.media_url)
  const caption = (post.caption || '').trim()
  // Captions run long. Show the opening and let it be opened out, rather than
  // either truncating to 40 characters — which told an agent nothing — or
  // letting a 2,000-character caption push the actual comment off screen.
  const isLong = caption.length > 320
  const shown = expanded || !isLong ? caption : caption.slice(0, 320).trimEnd()

  return (
    <div className="w-[22rem] max-w-full mb-2 rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-100">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
            <Instagram size={12} className="text-gray-400" />
          </span>
          <span className="text-xs font-bold text-gray-700 truncate">Original post</span>
        </div>
        {post.permalink && (
          <a
            href={post.permalink}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-[11px] font-semibold text-brand-600 hover:text-brand-700 shrink-0"
          >
            Open <ExternalLink size={11} />
          </a>
        )}
      </div>

      {/* Instagram serves media from signed CDN links that expire, so an older
          post reliably 404s. A broken-image icon would read as our bug; this
          says what happened and offers the one thing that still works. Same
          reasoning as Attachment below. */}
      {image && !imgFailed ? (
        <img
          src={image}
          alt=""
          onError={() => setImgFailed(true)}
          className="w-full max-h-64 object-cover bg-gray-50"
          loading="lazy"
        />
      ) : (
        <a
          href={post.permalink || '#'}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex items-center justify-center gap-1.5 m-3 rounded-lg border border-dashed border-gray-300 py-6 text-[12px] text-gray-400 hover:border-gray-400 hover:text-gray-500 transition-colors"
        >
          Media unavailable — view on the platform <ExternalLink size={11} />
        </a>
      )}

      {caption && (
        <div className="px-3 py-2.5">
          {/* whitespace-pre-line keeps the paragraph breaks the caption was
              written with. Collapsing them turned a structured caption into
              one grey slab. */}
          <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-line break-words">
            <CaptionText text={shown} />
            {isLong && !expanded && '\u2026'}
          </p>
          {isLong && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setExpanded(v => !v) }}
              className="mt-1 text-[11px] font-semibold text-gray-400 hover:text-brand-600 transition-colors"
            >
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// Hashtags, @mentions and links picked out of a caption. They are how an IG
// caption is actually read — the tags at the end are a block of metadata, not
// a sentence — and running them together as flat grey text is what made the
// old preview unreadable at any length.
const CAPTION_SPLIT_RE = /(https?:\/\/[^\s<>()"']+|[#@][\w.]+)/g

function CaptionText({ text }) {
  return String(text || '').split(CAPTION_SPLIT_RE).map((part, i) => {
    if (!part) return null
    if (IS_URL_RE.test(part)) {
      return (
        <a key={i} href={part} target="_blank" rel="noopener noreferrer"
           onClick={(e) => e.stopPropagation()}
           className="text-brand-600 hover:underline break-all">{part}</a>
      )
    }
    if (part[0] === '#' || part[0] === '@') {
      return <span key={i} className="text-brand-600 font-medium">{part}</span>
    }
    return part
  })
}

// Bold the searched term inside a match snippet. Split on the term rather
// than using dangerouslySetInnerHTML — the term comes from the search box, so
// injecting it as markup would be an XSS hole opened by the user typing.
// One image in a message bubble.
//
// A bare <img> was a bad fit here because these URLs expire. Instagram and
// Facebook serve attachments from signed CDN links with a lifetime, so a photo
// a customer sent last month renders as a broken-image icon — and when the
// message text is the placeholder "[Sent a photo]" (which the bubble hides),
// the whole bubble came out completely empty. An agent scrolling back saw a
// blank gap with no way to tell whether something failed or nothing was there.
function Attachment({ url, onOpen }) {
  const [state, setState] = useState('loading')

  if (state === 'error') {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="flex items-center gap-2 rounded-xl border border-dashed border-gray-300 px-3 py-2.5 max-w-[220px] hover:border-gray-400 transition-colors"
      >
        <ImageOff size={14} className="text-gray-400 shrink-0" />
        <span className="text-[12px] text-gray-500 leading-snug">
          Image unavailable
          <span className="block text-[11px] text-gray-400">
            The link from the platform has expired — open directly
          </span>
        </span>
      </a>
    )
  }

  return (
    <div className="relative max-w-[220px] w-full">
      {state === 'loading' && (
        <div className="absolute inset-0 rounded-xl bg-gray-100 animate-pulse" />
      )}
      <img
        src={url}
        alt="attachment"
        onClick={onOpen}
        onLoad={() => setState('ok')}
        onError={() => setState('error')}
        className={clsx(
          'rounded-xl w-full object-cover cursor-zoom-in hover:opacity-90 transition-opacity',
          state === 'loading' && 'opacity-0'
        )}
        loading="lazy"
      />
    </div>
  )
}

// A search term goes straight into a RegExp, so every character that means
// something to the engine has to be neutralised first. Typing "20%" or "(sale)"
// would otherwise throw and blank the whole list.
const escapeRegExp = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function Highlighted({ text, term }) {
  const t = (term || '').trim()
  if (!t) return <>{text}</>
  const parts = String(text).split(new RegExp('(' + escapeRegExp(t) + ')', 'ig'))
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === t.toLowerCase()
          ? <mark key={i} className="bg-brand-200 text-gray-900 rounded-sm px-0.5">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </>
  )
}

function Linkified({ text, on = 'light' }) {
  return (
    <>
      {String(text).split(URL_SPLIT_RE).map((part, i) =>
        IS_URL_RE.test(part) ? (
          <a
            key={i}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className={clsx(
              'underline underline-offset-2 break-all font-medium',
              on === 'ai'    && 'link-on-ai',
              on === 'agent' && 'link-on-agent',
              on === 'light' && 'text-brand-600 hover:text-brand-700'
            )}
          >
            {part}
          </a>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  )
}

export default function Messages() {
  const { user } = useAuth()
  const [selected, setSelected]         = useState(null)   // null = show list on mobile
  const [showContext, setShowContext]   = useState(false)  // mobile context panel toggle
  const [channelFilter, setChannelFilter] = useState('all') // filters by DB `channel`
  // Platform and surface are asked separately now — see the two rows in the
  // list header. The server takes them as independent params.
  const [platformFilter, setPlatformFilter] = useState('all')  // instagram | facebook | …
  const [surfaceFilter, setSurfaceFilter] = useState('all')    // dm | comment
  const [channelCounts, setChannelCounts] = useState({})       // { instagram_dm: 20, … }
  // Same shape, different scope: counted with the surface filter lifted, so the
  // DMs/Comments row can respect the chosen platform without zeroing itself.
  const [surfaceChannelCounts, setSurfaceChannelCounts] = useState({})
  const [channelAvailability, setChannelAvailability] = useState({}) // { tiktok: false, … }
  const [statusFilter, setStatusFilter] = useState(null)        // null | unclaimed | human | ai | resolved
  const [page, setPage] = useState(1)
  const [totalConvos, setTotalConvos] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const [statusCounts, setStatusCounts] = useState(null)         // server-side, whole set
  // Whether the master switch is off, and how many conversations it queued.
  const [aiGloballyOffCounts, setAiGloballyOffCounts] = useState(null)

  const [assignedFilter, setAssignedFilter] = useState(null)    // null | 'me' | 'unassigned' (set by deep links)
  // Two states on purpose. `searchInput` is what you see in the box and updates
  // on every keystroke; `search` is what the server is asked about and lags it
  // by 300ms. Without the gap, typing "dress" fired five requests, and now that
  // search reaches into message bodies each one scans every message row.
  const [searchInput, setSearchInput]   = useState('')
  const [search, setSearch]             = useState('')

  // Settle the typing before asking the server.
  //
  // Must sit AFTER the two useState lines above, not before them. A hook's
  // dependency array is evaluated during render, so `[searchInput]` reads the
  // binding right then — and a `const` cannot be read before its declaration
  // is reached. Placed above, this threw "Cannot access 'searchInput' before
  // initialization" and took the whole page down. The build cannot catch it:
  // it is legal JavaScript that only fails when it runs.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => clearTimeout(t)
  }, [searchInput])

  const [conversations, setConversations] = useState([])
  const [allChannels, setAllChannels] = useState(['all']) // Track all channels - only set once
  const [activeConv, setActiveConv]       = useState(null) // full conv w/ messages

  const [loadingList, setLoadingList]   = useState(true)
  const [loadingConv, setLoadingConv]   = useState(false)
  const [listError, setListError]       = useState(null)
  const [convError, setConvError]       = useState(null)

  // A send that failed, kept so it can be retried verbatim.
  // Failures used to be written into convError — the same state the *conversation
  // failed to load* path uses. Its Retry button re-fetches the thread, so the
  // one button offered after a failed send did nothing about the message that
  // hadn't been sent, and the error panel elbowed the thread down the screen.
  const [sendError, setSendError]       = useState(null)
  const [reassignedError, setReassignedError] = useState(false)  // Track if conv was reassigned

  const [replyText, setReplyText]       = useState('')
  const [sending, setSending]           = useState(false)
  const [resolving, setResolving]       = useState(false)
  // Refs update synchronously; `sending` state doesn't close the gate fast
  // enough when two triggers land in the same tick (double Enter, or Enter
  // plus the button), which sent the same reply twice.
  const sendingRef = useRef(false)
  const [isInitialLoad, setIsInitialLoad] = useState(true) // flag for auto-select on first load

  // Assignment UI
  const [agents, setAgents]             = useState([]) // list of active agents
  const [showAssignDropdown, setShowAssignDropdown] = useState(false)
  const [assigningConvId, setAssigningConvId] = useState(null)

  const [replyContext, setReplyContext] = useState(null) // { id, text, from }
  const [editingMsgId, setEditingMsgId] = useState(null)
  const [editText, setEditText] = useState('')

  const [postContext, setPostContext] = useState(null)
  const [loadingPost, setLoadingPost] = useState(false)
  const [lightbox, setLightbox] = useState(null)   // expanded attachment url

  const [toast, setToast] = useState(null)

  // Global AI master switch (Settings → Automated AI replies). When it's off
  // every conversation behaves as AI-off regardless of its own flag, so the
  // manual reply bar must appear. Re-checked on a slow interval so flipping
  // the switch reaches open tabs without a reload.
  // Set from the conversation-counts poll below, which every role can read.
  // It used to be fetched from the admin-only settings endpoint here, so for
  // agents it never became true.
  const [aiGloballyOff, setAiGloballyOff] = useState(false)

  const showToast = (text, type = 'info') => {
    setToast({ text, type })
    setTimeout(() => setToast(t => (t && t.text === text ? null : t)), 5000)
  }

  const { confirm } = useContext(ConfirmationContext)

  // Channels available for the filter row (derived from what we loaded).
  // Keep all channels even when filtering, so filters don't disappear
  const channels = allChannels

  // ── Load the conversation list (re-runs on filter / search change) ────────
  // Paged. The list previously requested page 1 / 20 rows and offered no way
  // to reach the rest — with 46 conversations, 26 were simply unreachable
  // through the UI, with nothing on screen to suggest they existed.
  const loadList = useCallback(async () => {
    setLoadingList(true)
    setListError(null)
    try {
      // Canonical contract: send `channel` (not `platform`); response is
      // { conversations, total, page, per_page }.
      const data = await listConversations({
        channel: channelFilter, platform: platformFilter, surface: surfaceFilter,
        search,
        page: 1,
        per_page: PAGE_SIZE,
        bucket: statusFilter || null,
        assigned_to: assignedFilter || null,
      })
      setConversations(data.conversations || [])
      setTotalConvos(data.total ?? (data.conversations || []).length)
      setPage(1)
    } catch (err) {
      setListError(err.message)
    } finally {
      setLoadingList(false)
    }
  }, [channelFilter, platformFilter, surfaceFilter, search, statusFilter, assignedFilter])

  const loadMore = useCallback(async () => {
    if (loadingMore) return
    setLoadingMore(true)
    try {
      const next = page + 1
      const data = await listConversations({
        channel: channelFilter, platform: platformFilter, surface: surfaceFilter,
        search, page: next, per_page: PAGE_SIZE,
        bucket: statusFilter || null,
        assigned_to: assignedFilter || null,
      })
      const incoming = data.conversations || []
      // Merge by id — a conversation can move between pages while you're
      // reading (a new message reorders the list), which would otherwise
      // duplicate it.
      setConversations(prev => {
        const seen = new Set(prev.map(c => c.id))
        return [...prev, ...incoming.filter(c => !seen.has(c.id))]
      })
      setTotalConvos(data.total ?? totalConvos)
      setPage(next)
    } catch { /* leave the list as-is; the button stays available */ }
    finally { setLoadingMore(false) }
  }, [channelFilter, platformFilter, surfaceFilter, search, statusFilter, assignedFilter, page, loadingMore, totalConvos])

  useEffect(() => {
    // Load conversations on initial mount and when filters change
    const t = setTimeout(loadList, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [loadList, search, channelFilter, platformFilter, surfaceFilter, statusFilter, assignedFilter])

  // Status counts come from the server so the chips describe the whole inbox
  // rather than the page you happen to have loaded.
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const { getConversationCounts } = await import('../api/messages')
        const counts = await getConversationCounts({
          channel: channelFilter, platform: platformFilter, surface: surfaceFilter,
          search, bucket: statusFilter || null, assigned_to: assignedFilter || null,
        })
        if (!cancelled) {
          setStatusCounts(counts.by_status || null)
          setAiGloballyOffCounts({
            off: !!counts.ai_globally_off,
            queued: counts.ai_auto_paused || 0,
          })
          // Same flag drives the per-conversation AI toggle. It used to come
          // from GET /api/settings, which is admin-only — so for an agent that
          // call 403'd, the catch left the flag false, and the toggle stayed
          // live. An agent could switch AI on for a chat while the master
          // switch was off, which filed it under "AI", removed it from every
          // human queue, and guaranteed no reply. This endpoint already
          // carries the flag and every role can read it.
          setAiGloballyOff(!!counts.ai_globally_off)
          setChannelCounts(counts.by_channel || {})
          setSurfaceChannelCounts(counts.by_surface_channel || counts.by_channel || {})
          setChannelAvailability(counts.channels || {})
        }
      } catch { /* chips fall back to counting the loaded page */ }
    }
    load()
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, 15000)
    return () => { cancelled = true; clearInterval(t) }
  }, [channelFilter, platformFilter, surfaceFilter, search, statusFilter, assignedFilter])

  // ── Poll the conversation list for new conversations / messages.
  // Silent refresh: doesn't toggle loadingList so the list never flickers.
  useEffect(() => {
    const silentRefresh = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        // Refresh page 1 only and MERGE, so polling can't throw away pages the
        // user has already loaded — replacing wholesale would have snapped a
        // scrolled list back to the first 20 every 10 seconds.
        const data = await listConversations({
          channel: channelFilter, platform: platformFilter, surface: surfaceFilter,
          search, page: 1, per_page: PAGE_SIZE,
        bucket: statusFilter || null,
        assigned_to: assignedFilter || null,
      })
        const fresh = data.conversations || []
        setTotalConvos(data.total ?? totalConvos)
        setConversations(prev => {
          if (prev.length <= fresh.length) return fresh
          const byId = new Map(fresh.map(c => [c.id, c]))
          const updated = prev.map(c => byId.get(c.id) || c)
          const known = new Set(prev.map(c => c.id))
          return [...fresh.filter(c => !known.has(c.id)), ...updated]
        })
      } catch {
        // Silent fail — the visible list should never crash on poll error
      }
    }
    const timer = setInterval(silentRefresh, 10000)
    return () => clearInterval(timer)
  }, [channelFilter, platformFilter, surfaceFilter, search, statusFilter, assignedFilter, totalConvos])

  // Typing indicator: show ~3s after a new inbound message arrives,
  // OR until the AI reply appears (whichever first).
  const [aiTyping, setAiTyping] = useState(false)

  // Consecutive polls that found nothing new. Drives the backoff above.
  const pollIdleRef = useRef(0)

  // ── Poll the active conversation every 5s so new inbound messages appear
  // without clicking back into the thread. Silent — no loading state.
  useEffect(() => {
    if (!selected) return
    const silentRefresh = async () => {
      try {
        const data = await getConversation(selected)
        setActiveConv(prev => {
          if (!prev) return data.conversation
          const newMsgs = data.conversation.messages || []
          const oldMsgs = prev.messages || []

          // Keep what we have only if the server response is genuinely STALE —
          // meaning it is missing a message we already hold — not merely
          // shorter. This was `newMsgs.length < oldMsgs.length`, which is the
          // same test only while the local list is free of duplicates. Once a
          // duplicate crept in, the local list stayed permanently longer, the
          // guard fired on every poll, and the server was never allowed to
          // correct it. Comparing ids cannot be fooled that way: a duplicate is
          // the same id twice and collapses into the Set, so a healthy response
          // is accepted and the extra row disappears on the next tick.
          const oldIds = new Set(oldMsgs.map(m => m.id).filter(id => id != null))
          const newIds = new Set(newMsgs.map(m => m.id).filter(id => id != null))
          const responseIsStale = [...oldIds].some(id => !newIds.has(id))
          if (responseIsStale) return prev

          // Detect new messages — find any NEW inbound that wasn't there before.
          // We can't just check the last message because the poll might catch
          // both the inbound AND the AI's outbound reply in the same cycle.
          if (newMsgs.length > oldMsgs.length) {
            const oldIds = new Set(oldMsgs.map(m => m.id))
            const newOnes = newMsgs.filter(m => !oldIds.has(m.id))
            const hasNewInbound = newOnes.some(m => m.from === 'user')
            const hasNewOutbound = newOnes.some(m => m.from === 'ai' || m.from === 'human')

            if (hasNewInbound && !hasNewOutbound && data.conversation.ai_enabled) {
              // New inbound alone — show typing indicator
              setAiTyping(true)
              setTimeout(() => setAiTyping(false), 5000)
            } else if (hasNewOutbound) {
              // AI/human reply arrived — clear typing
              setAiTyping(false)
            }
          }

          if (newMsgs.length !== oldMsgs.length) pollIdleRef.current = 0

          return { ...prev, ...data.conversation }
        })
      } catch {
        // Silent fail
      }
    }

    let cancelled = false
    let timer = null

    // Self-scheduling rather than setInterval: the delay has to be able to
    // change between ticks, and setInterval can't do that. It also can't skip
    // a tick, so a slow response would stack requests on top of each other.
    const tick = async () => {
      if (cancelled || document.hidden) return
      pollIdleRef.current += 1
      await silentRefresh()
      schedule()
    }

    const schedule = () => {
      if (cancelled || document.hidden) return
      clearTimeout(timer)
      timer = setTimeout(tick, pollIdleRef.current >= POLL_IDLE_BEFORE_BACKOFF
        ? POLL_SLOW_MS
        : POLL_FAST_MS)
    }

    // A hidden tab shows nobody anything, so polling it is pure waste. Coming
    // back deserves fresh data at once, not after another interval.
    const onVisibility = () => {
      clearTimeout(timer)
      if (document.hidden) return
      pollIdleRef.current = 0
      silentRefresh().then(schedule)
    }

    document.addEventListener('visibilitychange', onVisibility)
    pollIdleRef.current = 0
    schedule()

    return () => {
      cancelled = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [selected])

  // Fetch the IG post info when an IG-comment conversation is opened.
  // Show the post the MOST RECENT comment is on — a customer can comment on
  // several different posts, and the context should follow their latest one.
  const latestCommentMediaId = (() => {
    const inbound = (activeConv?.messages || []).filter(m => m.from === 'user' && m.media_id)
    return inbound.length ? inbound[inbound.length - 1].media_id : null
  })()

  useEffect(() => {
    setPostContext(null)
    if (!activeConv) return
    if (!activeConv.platform?.includes('comment')) return
    if (!latestCommentMediaId) return

    setLoadingPost(true)
    fetchInstagramMedia(latestCommentMediaId)
      .then(data => setPostContext(data))
      .catch(err => console.warn('Failed to load post context:', err))
      .finally(() => setLoadingPost(false))
  }, [activeConv?.id, activeConv?.platform, latestCommentMediaId])

  // Auto-scroll to latest message when active conversation updates.
  const messagesEndRef = useRef(null)
  useEffect(() => {
    const el = messagesEndRef.current
    if (!el) return
    // Double rAF so it runs after layout settles — on mobile the thread view
    // mounts a frame later than desktop's two-pane, so a bare call fires too early.
    const id = requestAnimationFrame(() =>
      requestAnimationFrame(() => el.scrollIntoView({ behavior: 'smooth', block: 'end' }))
    )
    return () => cancelAnimationFrame(id)
  }, [activeConv?.id, activeConv?.messages?.length, aiTyping])

  // Esc closes the expanded attachment.
  useEffect(() => {
    if (!lightbox) return
    const onKey = (e) => { if (e.key === 'Escape') setLightbox(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [lightbox])

  // Load all channels on mount
  useEffect(() => {
    const loadAllChannels = async () => {
      try {
        const data = await listConversations({
          channel: 'all',
          page: 1,
          per_page: 100,
        bucket: statusFilter || null,
        assigned_to: assignedFilter || null,
      })
        const uniqueChannels = new Set(['all'])
        data.conversations?.forEach(c => uniqueChannels.add(c.platform))
        setAllChannels(Array.from(uniqueChannels))
      } catch (err) {
        console.error('Failed to load channels:', err)
      }
    }
    loadAllChannels()
  }, [])

  // Load agents for assignment (supervisor/admin only)
  useEffect(() => {
    if (user?.role === 'supervisor' || user?.role === 'admin') {
      const loadAgentsList = async () => {
        try {
          const data = await listAgents()
          setAgents(data.agents || [])
        } catch (err) {
          console.error('Failed to load agents:', err)
        }
      }
      loadAgentsList()
    }
  }, [user?.role])

  // Never auto-open a conversation — the agent chooses. Auto-opening the top
  // one silently marked it read and killed its unread/attention signal.
  useEffect(() => {
    if (isInitialLoad) setIsInitialLoad(false)
  }, [isInitialLoad])

  // ── Deep links from the Dashboard ─────────────────────────────────────────
  // /messages?conversation=57       → open that thread
  // /messages?assigned_to=unassigned → show only the unclaimed queue
  // /messages?assigned_to=me         → show only what's assigned to me
  //
  // Live Activity rows and the alert panel link here. Without this the page
  // read no query string at all, so every one of those links just dumped you
  // on the inbox and left you to find the conversation yourself.
  const [deepLinkDone, setDeepLinkDone] = useState(false)
  useEffect(() => {
    if (deepLinkDone || loadingList) return
    const params = new URLSearchParams(window.location.search)
    const convId = parseInt(params.get('conversation'), 10)
    const assigned = params.get('assigned_to')

    if (Number.isFinite(convId)) {
      // Open from the list when it's there, but don't require it — a
      // conversation outside the loaded page still opens by id.
      const match = conversations.find(c => c.id === convId)
      openConversation(match || { id: convId, unread_count: 0 })
    }
    if (assigned === 'unassigned' || assigned === 'me') {
      setAssignedFilter(assigned)
    }
    setDeepLinkDone(true)
  }, [deepLinkDone, loadingList, conversations])   // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load a single conversation's full thread ──────────────────────────────
  const openConversation = useCallback(async (conv) => {
    setSelected(conv.id)
    setLoadingConv(true)
    setConvError(null)
    setReassignedError(false)
    setActiveConv(null)
    try {
      const data = await getConversation(conv.id)   // { conversation: {...} }
      setActiveConv(data.conversation)
      if (conv.unread_count > 0) {
        markRead(conv.id).catch(() => {})
        setConversations(prev =>
          prev.map(c => (c.id === conv.id ? { ...c, unread: false, unread_count: 0 } : c)))
      }
    } catch (err) {
      // Check if this is a 403 Forbidden error (conversation reassigned)
      if (err.status === 403 || err.message?.includes('Forbidden')) {
        setReassignedError(true)
        setConvError(null)
      } else {
        setConvError(err.message)
        setReassignedError(false)
      }
    } finally {
      setLoadingConv(false)
    }
  }, [])

  const backToList = () => {
    setSelected(null)
    setActiveConv(null)
    setSendError(null)
  }

  // Every filter — channel, status bucket, and the assignment deep-link from
  // the Dashboard — is now applied in SQL and arrives already narrowed.
  //
  // All three used to be re-applied here over `conversations`, which holds one
  // page of 20. So the chip counted the whole inbox server-side while the list
  // filtered a single page, and they disagreed as soon as the inbox was larger
  // than a page: "Resolved 27" above a list of 11, "Unclaimed 2" above "No
  // unclaimed conversations." A filter that only searches what you've already
  // scrolled past isn't a filter.
  const filteredConversations = conversations

  // Empty-state copy quotes the server's counts, not the loaded page, for the
  // same reason.
  const inboxSummary = {
    open:      (statusCounts?.unclaimed ?? 0) + (statusCounts?.human ?? 0) + (statusCounts?.ai ?? 0),
    unclaimed: statusCounts?.unclaimed ?? 0,
    ai:        statusCounts?.ai ?? 0,
  }

  // Effective AI state for the open conversation — the global master switch
  // overrides the per-conversation flag.
  const aiActive = !!activeConv?.ai_enabled && !aiGloballyOff
  const isResolved = activeConv?.status === 'resolved'

  // ── Toggle AI for the active conversation ─────────────────────────────────
  const handleToggleAI = async () => {
    if (!activeConv) return
    
    const confirmed = await confirm({
      title: activeConv.ai_enabled ? 'Disable AI?' : 'Enable AI?',
      message: activeConv.ai_enabled
        ? 'AI will be disabled for this conversation. You will handle replies manually.'
        : 'AI will be enabled again for this conversation.',
      confirmText: activeConv.ai_enabled ? 'Disable' : 'Enable',
      cancelText: 'Cancel',
      isDangerous: activeConv.ai_enabled,
    })

    if (!confirmed) return

    const next = !activeConv.ai_enabled
    // Optimistic in BOTH places. Only activeConv was updated before, so the
    // header said "AI paused" while the row in the list still showed the AI
    // handler badge — the same conversation described two ways on one screen.
    setActiveConv(c => ({ ...c, ai_enabled: next }))
    setConversations(list => list.map(c =>
      c.id === activeConv.id ? { ...c, ai_enabled: next } : c))
    try {
      const data = await toggleAI(activeConv.id, next) // { conversation: {...} }
      setActiveConv(c => ({ ...c, ...data.conversation }))
      setConversations(list => list.map(c =>
        c.id === activeConv.id ? { ...c, ...data.conversation } : c))
    } catch (err) {
      // Reverting in silence was the dangerous part: the agent saw the AI go
      // quiet, started typing a manual reply, and the AI was still live and
      // answering underneath them. A failed toggle has to be announced.
      setActiveConv(c => ({ ...c, ai_enabled: !next }))
      setConversations(list => list.map(c =>
        c.id === activeConv.id ? { ...c, ai_enabled: !next } : c))
      showToast(
        next
          ? 'Could not switch the AI back on — it is still paused for this chat.'
          : 'Could not pause the AI — it is STILL replying to this customer.',
        'warning'
      )
    }
  }

  // ── Resolve / re-open the active conversation ─────────────────────────────
  const handleToggleResolved = async () => {
    if (!activeConv || resolving) return
    const next = isResolved ? 'active' : 'resolved'

    // Only confirm on resolve. Re-opening is harmless and instantly undoable.
    if (next === 'resolved') {
      const ok = await confirm({
        title: 'Mark as resolved?',
        message: 'This closes the conversation. It stays searchable, and you can re-open it at any time.',
        confirmText: 'Resolve',
        cancelText: 'Cancel',
      })
      if (!ok) return
    }

    const previous = activeConv.status
    setResolving(true)
    setActiveConv(c => ({ ...c, status: next }))                       // optimistic
    setConversations(list => list.map(c =>
      c.id === activeConv.id ? { ...c, status: next } : c))            // keep the list in step
    try {
      const data = await updateConversationStatus(activeConv.id, next)
      const fresh = data.conversation || {}
      setActiveConv(c => ({ ...c, ...fresh }))
      setConversations(list => list.map(c =>
        c.id === activeConv.id ? { ...c, ...fresh } : c))
    } catch (err) {
      // The button silently flipped back and the only trace was a console line
      // no agent will ever open.
      setActiveConv(c => ({ ...c, status: previous }))                 // revert both
      setConversations(list => list.map(c =>
        c.id === activeConv.id ? { ...c, status: previous } : c))
      showToast(
        next === 'resolved'
          ? 'Could not mark this resolved — it is still open.'
          : 'Could not re-open this conversation — it is still marked resolved.',
        'warning'
      )
    } finally {
      setResolving(false)
    }
  }

  // ── Send a manual reply ───────────────────────────────────────────────────
const handleSend = async (retryOf = null) => {
    const content = retryOf ? retryOf.content : replyText.trim()
    const ctx = retryOf ? retryOf.replyContext : replyContext
    if (!content || !activeConv || sendingRef.current) return
    sendingRef.current = true
    setSending(true)
    setSendError(null)
    try {
      // If replying to a specific message, prepend a quote line so the
      // customer sees what we're responding to. Truncate long quotes.
      let outgoing = content
      if (ctx) {
        const quoted = ctx.text.length > 100
          ? `${ctx.text.substring(0, 100)}…`
          : ctx.text
        outgoing = `Replying to: "${quoted}"\n⠀\n${content}`
      }

      // Canonical: sendReply(id, content, sender='human')
      // -> { message, conversation }
      const data = await sendReply(activeConv.id, outgoing, 'human', ctx?.id ?? null)
      setActiveConv(c => {
        // Append only if the poll hasn't already brought this message in.
        // The thread refetches every few seconds, so a poll landing between
        // the server saving the reply and this setState leaves the message
        // already present — and appending it again showed the agent two
        // identical outbound rows for a single message that Instagram, quite
        // correctly, only ever received once.
        const existing = c.messages || []
        const already = data.message?.id != null
          && existing.some(m => m.id === data.message.id)
        return {
          ...c,
          ...data.conversation,
          messages: already ? existing : [...existing, data.message],
        }
      })
      // Reflect the new last message + status in the list.
      setConversations(prev => prev.map(c =>
        c.id === activeConv.id
          ? {
              ...c,
              lastMessage: data.conversation.lastMessage,
              status: data.conversation.status,
              time: data.conversation.time,
            }
          : c))
      setReplyText('')
      setReplyContext(null)
      if (data.delivered === false) {
        showToast('Saved, but Instagram did not accept it — the customer has NOT received this.', 'warning')
      }
    } catch (err) {
      // Hold the exact message so Retry resends THIS text. The composer keeps
      // its contents too, so nothing the agent typed is lost either way.
      setSendError({ message: err.message, content, replyContext: ctx })
    } finally {
      sendingRef.current = false
      setSending(false)
    }
  }

  // ── Assign conversation to agent ───────────────────────────────────────────
  const handleAssign = async (agentId) => {
    if (!activeConv) return

    if (activeConv.ai_enabled) {
      const confirmed = await confirm({
        title: 'Turn the AI off and assign?',
        message: 'The AI is handling this conversation. Assigning it to an agent means switching the AI off here first.',
        confirmText: 'Disable AI',
        cancelText: 'Cancel',
        isDangerous: false,
      })
      if (confirmed) {
        handleToggleAI()
      }
      return
    }

    setAssigningConvId(activeConv.id)
    try {
      const data = await assignConversation(activeConv.id, agentId)
      setActiveConv(data.conversation)
      setConversations(prev => prev.map(c =>
        c.id === activeConv.id ? { ...c, ...data.conversation } : c
      ))
      setShowAssignDropdown(false)

      const conv = data.conversation
      const name = conv.assignee?.full_name || 'That agent'
      if (conv.assignee_presence === 'offline') {
        showToast(`Assigned, but ${name} is offline — they may not see it right away.`, 'warning')
      } else if (typeof conv.assignee_open_load === 'number' && conv.assignee_open_load >= 10) {
        showToast(`Assigned — ${name} now has ${conv.assignee_open_load} open chats. Consider spreading the load.`, 'warning')
      }
    } catch (err) {
      setConvError(err.message)
    } finally {
      setAssigningConvId(null)
    }
  }

  // ── Unassign conversation ──────────────────────────────────────────────────
  const handleUnassign = async () => {
    if (!activeConv) return
    const confirmed = await confirm({
      title: 'Remove assignment?',
      message: `Unassign this conversation from ${activeConv.assignee?.full_name || 'the current agent'}?`,
      confirmText: 'Unassign',
      isDangerous: false,
    })
    if (!confirmed) return

    setAssigningConvId(activeConv.id)
    try {
      const data = await unassignConversation(activeConv.id)
      setActiveConv(data.conversation)
      setConversations(prev => prev.map(c =>
        c.id === activeConv.id ? { ...c, ...data.conversation } : c
      ))
    } catch (err) {
      setConvError(err.message)
    } finally {
      setAssigningConvId(null)
    }
  }

  // Chip rows, folded from one per-channel count so both rows and the list can
  // never disagree. Platforms are derived from what actually exists in the
  // inbox rather than hardcoded — a channel nobody has ever messaged on is a
  // chip that always reads 0.
  const PLATFORM_LABELS = { instagram: 'Instagram', facebook: 'Facebook', whatsapp: 'WhatsApp', tiktok: 'TikTok' }

  const platformChips = (() => {
    const totals = {}
    for (const [ch, n] of Object.entries(channelCounts)) {
      const p = ch.split('_')[0]
      totals[p] = (totals[p] || 0) + n
    }
    // Every platform the system knows about, not only those with traffic — a
    // channel you haven't connected is exactly the one you need to be told
    // about, and hiding it makes the inbox look like the whole world.
    // Connected-but-quiet and not-connected are then distinguished by the
    // empty state rather than by a chip silently missing.
    for (const p of Object.keys(channelAvailability)) {
      if (!(p in totals)) totals[p] = 0
    }
    const all = Object.values(totals).reduce((a, b) => a + b, 0)
    return [
      { key: 'all', label: 'All channels', count: all },
      ...Object.entries(totals)
        .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
        .map(([p, n]) => ({
          key: p,
          label: PLATFORM_LABELS[p] || p,
          count: n,
          connected: channelAvailability[p] !== false,
        })),
    ]
  })()

  const surfaceTabs = (() => {
    let dm = 0, comment = 0
    for (const [ch, n] of Object.entries(surfaceChannelCounts)) {
      if (ch.endsWith('_comment')) comment += n
      else dm += n            // whatsapp and any future bare channel are DMs
    }
    return [
      { key: 'all', label: 'All', count: dm + comment },
      { key: 'dm', label: 'DMs', count: dm },
      { key: 'comment', label: 'Comments', count: comment },
    ]
  })()

  // ── Conversation list panel ──────────────────────────────────────────────
  const ConvList = (
    <div className={clsx(
      'border-r border-gray-100 flex flex-col bg-white',
      'w-full lg:w-80 lg:shrink-0',
      selected ? 'hidden lg:flex' : 'flex',
    )}>
      <div className="px-3 pt-3 pb-2.5 space-y-2.5">
        <input
          className="input w-full text-xs rounded-xl"
          placeholder="Search conversations…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        {/* PLATFORM — where it came from.
            Was one row mixing platform and surface ("Instagram DM",
            "Facebook DM"), which made the two impossible to ask separately:
            you could not see everything from Instagram, or every comment
            across channels. They are now two rows, and the server filters on
            each independently. */}
        <div className="flex gap-1.5 overflow-x-auto hide-scrollbar sm:flex-wrap">
          {platformChips.map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setPlatformFilter(key)}
              className={clsx(
                'text-[12px] px-2.5 py-1 rounded-full font-semibold transition-all whitespace-nowrap shrink-0 sm:shrink inline-flex items-center gap-1.5',
                platformFilter === key
                  ? 'bg-brand-500 text-black'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              )}
            >
              {label}
              {count > 0 && (
                <span className={clsx(
                  // Circle, not a rounded square. min-w + aspect keeps it round
                  // at one digit and lets it become a pill at three, rather than
                  // clipping — 8 and 128 both have to fit.
                  'text-[11px] font-bold tabular-nums leading-none rounded-full',
                  'min-w-[16px] h-[16px] px-1 inline-flex items-center justify-center',
                  platformFilter === key ? 'bg-black/15' : 'bg-gray-200 text-gray-500'
                )}>{count}</span>
              )}
            </button>
          ))}
        </div>
        {/* Status filters. These replace the old "Needs attention" toggle,
            which was one opaque switch hiding a rule you had to already know
            ("AI is off for this conversation"). These say what they select,
            show how many are in each, and can be combined with the channel
            filter above.

            Counts come from the server over the whole scoped inbox, computed
            with the same predicate that filters the list — see _bucket_filter
            in app/messages.py. Both used to be worked out here in the browser
            over one loaded page, which is how a chip could read 27 above a
            list of 11. */}
        {aiGloballyOffCounts?.off && (statusCounts?.ai > 0 || aiGloballyOffCounts.queued > 0) && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <p className="text-[12px] font-bold text-amber-800">AI is off for the whole platform</p>
            <p className="text-[12px] text-amber-700 mt-0.5 leading-snug">
              {statusCounts?.ai > 0
                ? `${statusCounts.ai} conversation${statusCounts.ai === 1 ? '' : 's'} still marked for the AI — nobody is answering ${statusCounts.ai === 1 ? 'it' : 'them'} until it is switched back on or they are queued for agents in Settings.`
                : `${aiGloballyOffCounts.queued} conversation${aiGloballyOffCounts.queued === 1 ? '' : 's'} queued for agents while the AI is off.`}
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5 pt-2.5 border-t border-gray-100">
          {STATUS_FILTERS.map((f) => {
            const stalled = f.key === 'ai' && aiGloballyOffCounts?.off
            const { key } = f
            const label = stalled ? f.offLabel : f.label
            const dot = stalled ? f.offDot : f.dot
            // Server count over the whole scoped set. No loaded-page fallback:
            // the list now arrives already narrowed to the active bucket, so
            // counting it would report 0 for every OTHER chip. Blank until the
            // first counts call lands is honest; a wrong number is not.
            const n = statusCounts?.[key]
            const active = statusFilter === key
            return (
              <button
                key={key}
                onClick={() => setStatusFilter(active ? null : key)}
                className={clsx(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[12px] font-semibold transition-colors',
                  active ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
                title={active ? 'Clear this filter' : `Show only ${label.toLowerCase()}`}
              >
                <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', dot)} />
                {label}
                {n != null && (
                  <span className={clsx('tabular-nums', active ? 'text-white/70' : 'text-gray-400')}>{n}</span>
                )}
              </button>
            )
          })}
        </div>

        {/* SURFACE — a DM and a public comment are different jobs. A comment is
            visible to everyone who sees the post, so it is often the more
            urgent of the two; a segmented control rather than another chip row
            because these three are mutually exclusive and always present. */}
        <div className="pt-2.5 border-t border-gray-100">
        <div className="flex rounded-xl bg-gray-100 p-0.5 gap-0.5">
          {surfaceTabs.map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setSurfaceFilter(key)}
              className={clsx(
                'flex-1 text-[12px] font-semibold py-1.5 rounded-lg transition-all inline-flex items-center justify-center gap-1.5',
                surfaceFilter === key
                  ? 'bg-brand-500 text-black shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              {label}
              {count > 0 && (
                <span className={clsx(
                  'text-[11px] font-bold tabular-nums',
                  surfaceFilter === key ? 'text-black/55' : 'text-gray-400'
                )}>{count}</span>
              )}
            </button>
          ))}
        </div>
        </div>
      </div>
      {/* A deep link silently hiding most of the inbox would look like an
          empty inbox. Say what's filtered, and make it one click to clear. */}
      {assignedFilter && (
        <div className="mx-2 mb-2 flex items-center justify-between gap-2 rounded-lg bg-brand-50 border border-brand-100 px-3 py-2">
          <span className="text-[12px] font-semibold text-brand-700 truncate">
            Showing {assignedFilter === 'me' ? 'your conversations' : 'unassigned only'}
          </span>
          <button
            onClick={() => setAssignedFilter(null)}
            className="text-[12px] font-semibold text-brand-700 hover:text-brand-800 shrink-0"
          >
            Clear
          </button>
        </div>
      )}
      <div className="flex-1 overflow-y-auto hide-scrollbar px-2 pb-3 space-y-1">
        {loadingList && (
          <div className="p-2 sm:p-3 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <SkeletonCard key={i} className="h-20" />
            ))}
          </div>
        )}
        {listError && !loadingList && (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-red-500 mb-3 font-medium">{listError}</p>
            <button onClick={loadList} className="text-xs text-black font-semibold hover:text-gray-700">Retry</button>
          </div>
        )}
        {/* A platform that isn't connected gets its own answer.
            "No conversations" is true but useless there — it reads as "nobody
            has messaged you on TikTok" when the real answer is "we aren't
            listening to TikTok". One is a quiet day, the other is a setup step,
            and they want opposite responses. */}
        {!loadingList && !listError && filteredConversations.length === 0
          && platformFilter !== 'all' && channelAvailability[platformFilter] === false && (
          <div className="px-6 py-12 text-center">
            <div className="w-12 h-12 rounded-2xl bg-brand-50 text-brand-600 flex items-center justify-center mx-auto mb-3">
              <Inbox size={20} />
            </div>
            <p className="text-sm font-bold text-gray-900">
              {PLATFORM_LABELS[platformFilter] || platformFilter} isn’t connected yet
            </p>
            <p className="text-xs text-gray-500 mt-1.5 leading-relaxed max-w-[15rem] mx-auto">
              Once {PLATFORM_LABELS[platformFilter] || platformFilter} is connected in Settings,
              messages and comments from it will appear here.
            </p>
            {/* Admins only — Settings is admin-gated, so offering the link to
                an agent sends them to a 403. They can see WHY the list is
                empty, which is the part that was missing. */}
            {user?.role === 'admin' && (
              <a
                href="/settings?tab=channels"
                className="mt-3 inline-block text-xs font-semibold text-brand-600 hover:text-brand-700"
              >
                Open channel settings
              </a>
            )}
          </div>
        )}

        {!loadingList && !listError && filteredConversations.length === 0
          && !(platformFilter !== 'all' && channelAvailability[platformFilter] === false) && (
          <div className="px-6 py-12 text-center">
            <p className="text-xs text-gray-500">
              {statusFilter
                ? `No ${STATUS_FILTERS.find(f => f.key === statusFilter)?.label.toLowerCase()} conversations`
                : 'No conversations'}
              {platformFilter !== 'all' && ` in ${PLATFORM_LABELS[platformFilter] || platformFilter}`}
              {surfaceFilter !== 'all' && ` (${surfaceFilter === 'dm' ? 'DMs' : 'comments'})`}
              {search && ` matching “${search}”`}.
            </p>
            {/* An empty bucket now means the bucket is genuinely empty — the
                filter runs in SQL over the whole inbox. But channel and search
                narrow it further, so when one of those is what emptied the
                list, offer the way back rather than leaving a dead end. */}
            {(channelFilter !== 'all' || platformFilter !== 'all' || surfaceFilter !== 'all' || search || statusFilter) && (
              <button
                onClick={() => {
                  setStatusFilter(null); setChannelFilter('all')
                  setPlatformFilter('all'); setSurfaceFilter('all')
                  setSearchInput(''); setSearch('')
                }}
                className="mt-2 text-xs font-semibold text-brand-600 hover:text-brand-700"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}
        {!loadingList && !listError && filteredConversations.map((conv) => {
          const attn = attentionInfo(conv)
          const isActive = activeConv?.id === conv.id
          return (
          <button
            key={conv.id}
            onClick={() => openConversation(conv)}
            className={clsx(
              'w-full text-left rounded-2xl px-3 py-3 transition-all relative group',
              isActive
                ? 'bg-brand-500/10 ring-1 ring-brand-500/30'
                : 'hover:bg-gray-50'
            )}
          >
            <div className="flex items-start gap-2.5">
              {/* Avatar. Urgency shows as a dot on the corner rather than a
                  left rule — keeps the row edge clean. */}
              <div className="relative shrink-0">
                <div className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center transition-colors">
                  {platformIcon(conv.platform)}
                </div>
                {attn && (
                  <span className={clsx(
                    'absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full',
                    attn.urgent ? 'bg-red-500' : 'bg-amber-400'
                  )} />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className={clsx(
                    'text-[14px] truncate',
                    conv.unread_count > 0 ? 'font-bold text-gray-900' : 'font-semibold text-gray-900'
                  )}>
                    {conv.handle}
                  </span>
                  <span className="text-[12px] text-gray-400 shrink-0 whitespace-nowrap">
                    {conv.last_message_at ? formatTimeAgo(conv.last_message_at) : conv.time}
                  </span>
                </div>

                <p className={clsx(
                  'text-xs truncate mt-1',
                  conv.unread_count > 0 ? 'text-gray-700' : 'text-gray-500'
                )}>
                  {conv.lastMessage}
                </p>

                {/* Search now matches anything ever said in the thread, so a
                    row can match on a line that isn't the one displayed above.
                    Showing the matched line — and who said it — is what stops
                    the agent opening every result to find which one they
                    meant. The server only sends this when the visible line
                    doesn't already contain the term. */}
                {conv.match_snippet && (
                  <p className="text-[12px] text-gray-500 mt-1 pl-2 border-l-2 border-brand-300 line-clamp-2">
                    <span className="font-semibold text-gray-400">
                      {conv.match_from === 'customer' ? 'They said: ' : 'We said: '}
                    </span>
                    <Highlighted text={conv.match_snippet} term={search} />
                  </p>
                )}

                <div className="flex items-center gap-1.5 mt-2">
                  {conv.platform && conv.platform.includes('comment') && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-purple-100 text-purple-700 uppercase tracking-wide shrink-0">
                      Comment
                    </span>
                  )}
                  {attn?.badge && (
                    <span className={clsx(
                      'text-[11px] font-bold px-1.5 py-0.5 rounded-md',
                      // Green, not red. "Urgent" means look at this now — it
                      // does not have to mean something has gone wrong, and a
                      // customer with their wallet out is the best kind of
                      // urgent there is.
                      attn.good ? 'bg-brand-100 text-brand-700'
                        : attn.urgent ? 'bg-red-100 text-red-700'
                        : 'bg-amber-100 text-amber-700'
                    )}>
                      {attn.badge}
                    </span>
                  )}
                  {handlerBadge(conv, { terse: true })}
                  {conv.unread_count > 0 && (
                    <span className="ml-auto min-w-5 h-5 px-1.5 rounded-full bg-brand-500 text-black text-[11px] font-bold flex items-center justify-center shrink-0">
                      {conv.unread_count > 99 ? '99+' : conv.unread_count}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </button>
          )
        })}

        {/* Load more. Without this the inbox silently ended at 20 rows — no
            control, no count, nothing to indicate more existed. Hidden while
            a status filter is active, since that filters the loaded set and
            paging through it would be misleading. */}
        {!loadingList && !listError && !statusFilter && conversations.length < totalConvos && (
          <div className="px-2 py-3">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="w-full py-2.5 rounded-xl border border-gray-200 text-xs font-semibold text-gray-600 hover:text-gray-900 hover:border-gray-300 hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {loadingMore
                ? 'Loading…'
                : `Load more · showing ${conversations.length} of ${totalConvos}`}
            </button>
          </div>
        )}
      </div>
    </div>
  )

  // ── Chat thread panel ────────────────────────────────────────────────────
  const ChatPanel = (
    <div className={clsx(
      'flex-1 flex flex-col min-w-0 min-h-0 bg-gray-50',
      !selected ? 'hidden lg:flex' : 'flex',
    )}>
      {/* Empty state. A bare line of grey text wasted the largest area on the
          page — this puts the two numbers worth knowing before you pick a
          conversation, and a way straight to the one that needs you most. */}
      {!selected && (
        <div className="hidden lg:flex flex-1 items-center justify-center p-8">
          <div className="text-center max-w-sm">
            <div className="w-14 h-14 rounded-2xl bg-white border border-gray-200 flex items-center justify-center mx-auto mb-4 shadow-sm">
              <MessageCircle size={24} className="text-gray-300" />
            </div>
            <p className="text-base font-semibold text-gray-700">
              {inboxSummary.unclaimed > 0
                ? `${inboxSummary.unclaimed} conversation${inboxSummary.unclaimed === 1 ? '' : 's'} waiting to be picked up`
                : inboxSummary.open > 0
                  ? 'Nothing waiting — pick a conversation to read'
                  : 'Inbox clear'}
            </p>
            <p className="text-sm text-gray-500 mt-1.5 leading-relaxed">
              {inboxSummary.open > 0
                ? <>{inboxSummary.open} open, {inboxSummary.ai} being handled by the AI.</>
                : 'Nothing open right now. New messages appear here as they arrive.'}
            </p>
            {inboxSummary.unclaimed > 0 && (
              <button
                onClick={() => setStatusFilter('unclaimed')}
                className="mt-4 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-gray-900 text-white text-xs font-semibold hover:bg-gray-800 transition-colors"
              >
                Show unclaimed →
              </button>
            )}
          </div>
        </div>
      )}

      {selected && loadingConv && (
        <div className="flex-1 flex flex-col p-2 sm:p-3 space-y-2">
          <div className="h-12 bg-gray-100 rounded-lg animate-pulse" />
          <div className="flex-1 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className={clsx('flex', i % 2 === 0 ? 'justify-start' : 'justify-end')}>
                <div className={clsx('w-48 h-12 rounded-2xl animate-pulse', i % 2 === 0 ? 'bg-gray-100' : 'bg-gray-200')} />
              </div>
            ))}
          </div>
        </div>
      )}

      {selected && !loadingConv && reassignedError && (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-4">
          <div className="text-center max-w-sm">
            <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center mx-auto mb-3">
              <Info size={24} className="text-amber-600" />
            </div>
            <h3 className="text-sm font-bold text-gray-900 mb-1">Conversation Unavailable</h3>
            <p className="text-xs text-gray-600 mb-4">
              This conversation was reassigned to another agent and is no longer accessible to you.
            </p>
            <button
              onClick={() => {
                backToList()
                setReassignedError(false)
              }}
              className="text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors"
            >
              Return to conversations
            </button>
          </div>
        </div>
      )}

      {selected && !loadingConv && convError && !reassignedError && (
        <div className="flex-1 flex flex-col items-center justify-center gap-2">
          <p className="text-xs text-red-500">{convError}</p>
          <button onClick={() => openConversation(selected)} className="text-xs text-brand-600 font-medium">Retry</button>
        </div>
      )}

      {selected && !loadingConv && activeConv && (
        <>
        
          {/* The post this comment thread hangs off.
              The old version was a purple-to-pink pastel gradient with
              text-purple-700 on top. Those utilities have no dark-mode mapping
              (index.css remaps bg-white/bg-gray-* and text-gray-*, nothing
              else), so in dark mode it painted dark text on a dark surface and
              the caption was unreadable. Rebuilt out of dark-aware utilities
              only, and reshaped: the caption is the point — an agent reads it
              to understand what the customer is replying TO — so it gets room
              to breathe instead of being squeezed onto one truncated line
              between a label and a link. */}
          {activeConv.platform?.includes('comment') && (loadingPost || postContext) && (
            <div className="px-3 md:px-4 py-2.5 border-b border-gray-100 bg-gray-50">
              {loadingPost ? (
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Loader2 size={12} className="animate-spin" />
                  Loading the post this comment is on…
                </div>
              ) : postContext && (
                <div className="flex items-start gap-3">
                  {(postContext.thumbnail_url || postContext.media_url) ? (
                    <button
                      onClick={() => postContext.permalink && window.open(postContext.permalink, '_blank')}
                      className="shrink-0 relative group rounded-lg overflow-hidden border border-gray-200"
                      title="Open this post on Instagram"
                    >
                      <img
                        src={postContext.thumbnail_url || postContext.media_url}
                        alt="Post"
                        className="w-11 h-11 object-cover"
                        onError={(e) => { e.currentTarget.style.display = 'none' }}
                      />
                      <span className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                        <ExternalLink size={13} className="text-white opacity-0 group-hover:opacity-100 transition-opacity" />
                      </span>
                    </button>
                  ) : (
                    <div className="w-11 h-11 rounded-lg bg-gray-100 border border-gray-200 flex items-center justify-center shrink-0">
                      <Instagram size={15} className="text-gray-400" />
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-1">
                      <MessageSquare size={11} className="text-gray-400 shrink-0" />
                      <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">
                        Replying to a comment on
                      </span>
                    </div>
                    <p className="text-xs text-gray-700 leading-relaxed line-clamp-2">
                      {postContext.caption || <span className="italic text-gray-400">This post has no caption</span>}
                    </p>
                  </div>

                  {postContext.permalink && (
                    <button
                      onClick={() => window.open(postContext.permalink, '_blank')}
                      className="shrink-0 self-center flex items-center gap-1 text-[12px] font-semibold text-gray-500 hover:text-gray-900 border border-gray-200 hover:border-gray-300 rounded-lg px-2 py-1.5 transition-colors"
                    >
                      <span className="hidden sm:inline">Open post</span>
                      <ExternalLink size={11} />
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
          <div className="flex items-center justify-between px-2 sm:px-3 md:px-4 py-2 sm:py-3 border-b border-gray-100 bg-white gap-1 sm:gap-2 min-h-[56px] sm:min-h-auto">
            {/* Left: Back button + Chat info */}
            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
              <button
                onClick={backToList}
                className="lg:hidden btn-ghost p-1.5 shrink-0"
                aria-label="Back to conversations"
              >
                <ArrowLeft size={16} />
              </button>
              {platformIcon(activeConv.platform)}
              <span className="text-sm font-bold text-gray-900 truncate">{activeConv.handle}</span>
              <span className="hidden sm:block text-xs text-gray-400 shrink-0">
                {platformLabel(activeConv.platform)}
              </span>
            </div>

            {/* Right: three controls, one per question an agent actually has —
                is the AI answering this? is it finished? who owns it? */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {/* ONE control for the AI, showing state and toggling it.
                  There used to be a button reading "⚠ AI Off" AND a separate
                  chip reading "AI Disabled" right beside it — the same fact
                  twice, in two different wordings, competing with Resolve and
                  Assign for the same strip of space. The dot carries the
                  state; the label says what clicking does. */}
              <button
                onClick={handleToggleAI}
                disabled={aiGloballyOff}
                title={aiGloballyOff
                  ? 'AI is switched off globally in Settings — this chat can only be answered by hand'
                  : (aiActive ? 'Stop the AI replying in this conversation'
                              : 'Let the AI reply in this conversation again')}
                className={clsx(
                  'flex items-center gap-2 text-xs font-semibold px-2.5 py-1.5 rounded-lg border transition-colors whitespace-nowrap disabled:cursor-not-allowed',
                  aiGloballyOff
                    ? 'border-gray-200 bg-gray-50 text-gray-400'
                    : aiActive
                      ? 'border-gray-200 text-gray-600 hover:text-gray-900 hover:border-gray-300'
                      : 'border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
                )}
              >
                <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0',
                  aiGloballyOff ? 'bg-gray-300' : aiActive ? 'bg-brand-500' : 'bg-amber-500')} />
                <span className="hidden sm:inline">
                  {aiGloballyOff ? 'AI off · global' : aiActive ? 'AI replying' : 'AI paused'}
                </span>
              </button>

              {/* Resolve / re-open. The backend, the status field and the API
                  client have all supported this from the start — nothing ever
                  called it, so no conversation could reach 'resolved' and
                  resolved_at stayed permanently null. That left every old
                  chat looking open forever, which is what made the agent
                  "awaiting reply" alert report waits of tens of thousands of
                  minutes. */}
              <button
                onClick={handleToggleResolved}
                disabled={resolving}
                className={clsx(
                  'flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed',
                  isResolved
                    ? 'border border-gray-200 text-gray-500 hover:text-gray-900 hover:border-gray-300'
                    : 'bg-gray-900 text-white hover:bg-black border border-transparent'
                )}
                title={isResolved ? 'Re-open this conversation' : 'Mark this conversation resolved'}
              >
                {isResolved && <RotateCcw size={13} />}
                <span className="hidden sm:inline">{isResolved ? 'Re-open' : 'Resolve'}</span>
                <span className="sm:hidden">{isResolved ? 'Re-open' : 'Done'}</span>
              </button>

              {/* Assignment button — supervisor/admin only */}
              {/* Claim — the agent's own route into an unclaimed conversation.
                  The Assign dropdown beside this is admin/supervisor only, so
                  an agent looking at the Unclaimed queue could read a waiting
                  customer and had no way to take them: the only path was asking
                  a supervisor. The backend already allowed self-claiming and
                  refuses anything else, so this was a missing button rather
                  than a missing rule.
                  Shown to everyone — a supervisor picking up a chat themselves
                  shouldn't have to assign it to themselves through a menu. */}
              {activeConv && !activeConv.assigned_to && (
                <button
                  onClick={() => handleAssign(user?.id)}
                  disabled={assigningConvId === activeConv.id || !user?.id}
                  className="text-xs font-semibold px-2 sm:px-3 py-1.5 rounded-lg border border-brand-500 bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors whitespace-nowrap flex items-center gap-1.5 disabled:opacity-50"
                  title="Take this conversation"
                >
                  <UserCheck size={13} />
                  <span>{assigningConvId === activeConv.id ? 'Claiming…' : 'Claim'}</span>
                </button>
              )}

              {(user?.role === 'supervisor' || user?.role === 'admin') && (
                <div className="relative">
                  <button
                    onClick={() => setShowAssignDropdown(s => !s)}
                    disabled={assigningConvId === activeConv.id}
                    className={clsx(
                      'text-xs font-semibold px-2 sm:px-3 py-1.5 rounded-lg border transition-colors whitespace-nowrap flex items-center gap-1.5',
                      'border-gray-200 text-gray-700 hover:bg-gray-50 hover:border-gray-300'
                    )}
                  >
                    <Users size={13} />
                    <span className="hidden sm:inline">Assign</span>
                    {activeConv.assigned_to && (
                      <span className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded text-[11px] font-bold">
                        {activeConv.assignee?.full_name}
                      </span>
                    )}
                  </button>

                  {/* Dropdown menu */}
                  {showAssignDropdown && (
                    <>
                      <div
                        className="fixed inset-0 z-30"
                        onClick={() => setShowAssignDropdown(false)}
                      />
                      <div className="absolute left-0 top-full mt-1 w-56 bg-white rounded-3xl shadow-lg border border-gray-200 z-40">
                        <div className="p-2 space-y-1 max-h-64 overflow-y-auto">
                          {agents && agents.length > 0 ? (
                            <>
                              {agents.map(agent => (
                                <button
                                  key={agent.id}
                                  onClick={() => handleAssign(agent.id)}
                                  disabled={assigningConvId === activeConv.id}
                                  className={clsx(
                                    'w-full text-left px-3 py-2 text-xs rounded-md transition-colors',
                                    activeConv.assigned_to === agent.id
                                      ? 'bg-green-50 text-green-700 font-semibold'
                                      : 'text-gray-700 hover:bg-gray-50'
                                  )}
                                >
                                  <div className="font-medium">{agent.full_name}</div>
                                  <div className="text-[12px] text-gray-400">{agent.email}</div>
                                </button>
                              ))}
                              
                              {activeConv.assigned_to && (
                                <>
                                  <div className="border-t border-gray-100 my-1" />
                                  <button
                                    onClick={handleUnassign}
                                    disabled={assigningConvId === activeConv.id}
                                    className="w-full text-left px-3 py-2 text-xs text-red-600 hover:bg-red-50 rounded-md transition-colors flex items-center gap-2"
                                  >
                                    <X size={12} />
                                    <span>Remove Assignment</span>
                                  </button>
                                </>
                              )}
                            </>
                          ) : (
                            <div className="px-3 py-4 text-center text-xs text-gray-400">
                              No active agents available
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

            </div>

            {/* Right: Context toggle */}
            <button
              onClick={() => setShowContext(s => !s)}
              className="lg:hidden btn-ghost p-1.5"
              aria-label="Show AI context"
            >
              <Info size={15} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-2 sm:p-3 md:p-4 space-y-3 sm:space-y-4">
            {(activeConv.messages || []).map((msg, i, arr) => (
              <Fragment key={msg.id}>
              {/* Day separator. The thread only ever showed a time of day, so a
                  reply sent three weeks after the question looked like it came
                  straight after it — and conversations now span weeks, since a
                  returning customer joins their open thread. */}
              {dayKey(msg.created_at) !== dayKey(arr[i - 1]?.created_at) && (
                <div className="flex items-center gap-3 pt-2 pb-1 first:pt-0">
                  <div className="flex-1 h-px bg-gray-200" />
                  <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide shrink-0">
                    {formatDayLabel(msg.created_at)}
                  </span>
                  <div className="flex-1 h-px bg-gray-200" />
                </div>
              )}
              <div className={clsx('flex group', msg.from === 'user' ? 'justify-start' : 'justify-end')}>
                <div className={clsx(
                  'max-w-[90%] sm:max-w-[75%] md:max-w-[70%] flex flex-col gap-1',
                  msg.from === 'user' ? 'items-start' : 'items-end'
                )}>
                  <div className="flex items-center gap-1 px-1 text-xs">
                    {msg.from === 'user'  && <User size={11} className="text-gray-400" />}
                    {msg.from === 'ai'    && <Bot size={11} className="text-brand-500" />}
                    {msg.from === 'human' && <UserCheck size={11} className="text-amber-500" />}
                    <span className="text-gray-400 font-medium truncate">
                      {/* The person, not their job title. In a thread three
                          agents have touched, "Agent" three times hides who
                          said what — which is exactly what you are reading the
                          history to find out. Falls back to "Agent" for older
                          messages sent before we recorded the sender. */}
                      {msg.from === 'user' ? 'Customer'
                        : msg.from === 'ai' ? 'AI'
                        : (firstName(msg.sender_user) || 'Agent')}
                      {' · '}{msg.created_at ? formatTimeOfDay(msg.created_at) : msg.time}
                    </span>
                    {/* An outbound row with no external_id never reached the
                        platform. Meta returns an id for anything it accepts, so
                        a blank one means the send failed — and until now the
                        bubble rendered identically to a delivered message. Every
                        comment reply during the FB_ACCESS_TOKEN outage looked
                        answered in here while the customer saw silence, and an
                        agent scrolling the thread had no way to tell.

                        Deliberately not applied to inbound (the customer's own
                        messages always carry one) or to older rows with a null
                        id from before we recorded it — hence the created_at
                        guard being absent: we only trust this for messages we
                        sent, where the field has always been written on success. */}
                    {msg.from !== 'user' && !msg.external_id && (
                      <span
                        title="This never reached the platform — the customer has not seen it"
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-200 text-[10px] font-bold uppercase tracking-wide shrink-0"
                      >
                        <AlertCircle size={9} /> Not delivered
                      </span>
                    )}
                  </div>
                  {editingMsgId === msg.id ? (
                    <div className="flex flex-col gap-2 w-full">
                      <textarea
                        className="px-3 py-2 rounded-xl text-xs sm:text-sm border border-amber-300 bg-amber-50 text-gray-800 focus:outline-none focus:border-amber-500 resize-none"
                        rows={3}
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        autoFocus
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={async () => {
                            const confirmed = await confirm({
                              title: 'Edit message?',
                              message: 'This will unsend the original from Instagram and send the new version. The customer will see two notifications.',
                              confirmText: 'Edit & Send',
                              cancelText: 'Cancel',
                              isDangerous: false,
                            })
                            if (!confirmed) return
                            try {
                              const result = await editMessage(msg.id, editText)
                              // The original is unsent before the replacement
                              // is sent. If the send failed the customer now
                              // has neither, and only this flag says so.
                              if (result?.delivered === false) {
                                showToast(
                                  'The original was removed from Instagram but the new version did NOT send. '
                                  + 'The customer currently sees nothing — send it again.',
                                  'warning'
                                )
                              }
                              setActiveConv(c => ({
                                ...c,
                                messages: (c.messages || []).map(m =>
                                  m.id === msg.id ? result.message : m
                                ),
                              }))
                              setEditingMsgId(null)
                              setEditText('')
                            } catch (err) {
                              setConvError(err.message)
                            }
                          }}
                          className="text-xs font-semibold px-3 py-1 rounded-lg bg-amber-500 text-white hover:bg-amber-600"
                        >
                          Save
                        </button>
                        <button
                          onClick={() => { setEditingMsgId(null); setEditText('') }}
                          className="text-xs font-semibold px-3 py-1 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      {msg.from === 'user' && msg.media_id && activeConv?.platform?.includes('comment') && (
                        <CommentPostPreview mediaId={msg.media_id} />
                      )}
                      <div className={clsx(
                        'px-3 sm:px-3.5 py-2 sm:py-2.5 rounded-2xl text-xs sm:text-sm leading-relaxed shadow-sm',
                        msg.from === 'user'  && 'bg-white text-gray-800 rounded-tl-sm border border-gray-100',
                        // AI is navy, a person is grey. gray-900 (#111827) and
                        // gray-800 (#1f2937) are both blue-tinted and sit two
                        // steps apart, so side by side they read as one colour
                        // — the whole point of colouring them differently is
                        // telling at a glance whether a customer got a person.
                        // neutral-700 is a TRUE grey with no blue in it, so the
                        // two are unmistakable in either theme.
                        msg.from === 'ai'    && 'bg-gray-900 text-white rounded-tr-sm',
                        msg.from === 'human' && 'bg-neutral-700 text-white rounded-tr-sm',
                      )}>

                      {msg.image_urls && msg.image_urls.length > 0 && (
                        <div className="flex flex-col gap-1.5 mb-1.5">
                          {msg.image_urls.map((url, i) => (
                            <Attachment key={i} url={url} onOpen={() => setLightbox(url)} />
                          ))}
                        </div>
                      )}
                      {msg.text && msg.text !== '[Sent a photo]' && (
                        <div className="whitespace-pre-wrap break-words">
                          <Linkified
                            text={msg.text}
                            on={msg.from === 'user' ? 'light' : msg.from === 'ai' ? 'ai' : 'agent'}
                          />
                        </div>
                      )}
                      </div>
                    </div>
                  )}
                  
                  {/* Action buttons - icons only */}
                  <div className={clsx(
                    'flex gap-2 px-1 text-xs flex-wrap'
                  )}>
                    {/* Reply button - always available for all messages */}
                    <button 
                      onClick={() => {
                        if (aiActive) {
                          confirm({
                            title: 'Turn the AI off to reply?',
                            message: 'The AI is answering this conversation. Replying by hand means switching it off here first.',
                            confirmText: 'Disable AI',
                            cancelText: 'Cancel',
                            isDangerous: false,
                          }).then(confirmed => {
                            if (confirmed) handleToggleAI()
                          })
                        } else {
                          setReplyContext({ id: msg.id, text: msg.text, from: msg.from })
                          setTimeout(() => {
                            const input = document.querySelector('input[placeholder="Reply…"]')
                            if (input) input.focus()
                          }, 50)
                        }
                      }}
                      className="text-gray-400 hover:text-blue-600 transition-colors"
                      title="Reply"
                    >
                      <MessageCircle size={13} /> 
                    </button>

                    {/* Edit + Delete - only for AI and Human messages */}
                    {(msg.from === 'ai' || msg.from === 'human') && (
                      <>
                        <button 
                          onClick={() => {
                            setEditingMsgId(msg.id)
                            setEditText(msg.text)
                          }}
                          className="text-gray-400 hover:text-amber-600 transition-colors"
                          title="Edit"
                        >
                          <Edit size={13} />
                        </button>

                        <button 
                          onClick={async () => {
                            const confirmed = await confirm({
                              title: 'Delete message?',
                              message: 'This will remove the message from the platform and unsend it from Instagram. Unsend only works within 24 hours of sending.',
                              confirmText: 'Delete',
                              cancelText: 'Cancel',
                              isDangerous: true,
                            })
                            if (!confirmed) return
                            try {
                              const result = await deleteMessage(msg.id)
                              setActiveConv(c => ({
                                ...c,
                                messages: (c.messages || []).filter(m => m.id !== msg.id),
                              }))
                              if (!result.ig_unsent && msg.channel === 'instagram_dm') {
                                // Soft notice — DB deleted but IG unsend failed
                                console.warn('Message removed from platform; IG unsend failed (likely past 24h window)')
                              }
                            } catch (err) {
                              setConvError(err.message)
                            }
                          }}
                          className="text-gray-400 hover:text-red-600 transition-colors"
                          title="Delete"
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
              </Fragment>
            ))}
            {(activeConv.messages || []).length === 0 && (
              <p className="text-center text-xs text-gray-400 py-8">No messages in this conversation.</p>
            )}

            {/* AI typing indicator */}
            {aiTyping && (
              <div className="flex justify-end">
                <div className="flex flex-col gap-1 items-end max-w-[70%]">
                  <div className="flex items-center gap-1.5 px-1 text-xs">
                    <Bot size={11} className="text-brand-500 shrink-0" />
                    <span className="text-gray-400 font-medium">Claude is replying</span>
                  </div>
                  {/* Sized to a one-line bubble so the thread doesn't jump when
                      the real message replaces it. */}
                  <div className="bg-gray-900 text-white px-4 py-3 rounded-2xl rounded-tr-sm shadow-sm">
                    <div className="flex items-center gap-1.5">
                      {[0, 1, 2].map(i => (
                        <span
                          key={i}
                          // bg-current, not bg-white/70. The old dots inherited
                          // the dark remap of bg-white/70 — 8% white — which on
                          // the lime bubble dark mode gives this element was
                          // effectively invisible: an empty pill. Riding on the
                          // text colour instead means they follow whatever the
                          // bubble's foreground already is, in either theme.
                          className="w-[7px] h-[7px] rounded-full bg-current animate-typing-dot"
                          style={{ animationDelay: `${i * 160}ms` }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Who closed this, and when.
                A resolved conversation just stopped mid-thread with nothing to
                say it was finished on purpose — you had to notice the status
                chip in the header and take it on faith. Reading back through a
                thread weeks later, "who decided this was done?" is one of the
                first questions asked, and the answer was already stored in the
                conversation; it simply was not shown anywhere. */}
            {activeConv?.status === 'resolved' && (
              <div className="flex items-center gap-3 pt-2 pb-1">
                <span className="h-px flex-1 bg-emerald-200" />
                <span className="flex flex-col items-center gap-0.5 shrink-0">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1">
                    <CheckCircle2 size={12} className="text-emerald-600" />
                    <span className="text-[11px] font-bold text-emerald-800">
                      Resolved{activeConv.resolver ? ` by ${firstName(activeConv.resolver)}` : ''}
                    </span>
                  </span>
                  {(activeConv.resolver?.email || activeConv.resolved_at) && (
                    <span className="text-[11px] text-gray-400">
                      {/* Date AND time. "Today" alone is useless a week later,
                          and the exact moment is what gets quoted back when
                          someone asks why a customer was closed off. */}
                      {[activeConv.resolver?.email,
                        activeConv.resolved_at
                          ? `${formatDateAgo(activeConv.resolved_at)} at ${formatTimeOfDay(activeConv.resolved_at)}`
                          : null]
                        .filter(Boolean).join(' · ')}
                    </span>
                  )}
                </span>
                <span className="h-px flex-1 bg-emerald-200" />
              </div>
            )}

            {/* Scroll anchor — auto-scrolls to here on new message */}
            <div ref={messagesEndRef} />
          </div>

          {/* Manual reply bar — shown when AI is disabled for this conversation */}
          {activeConv && !aiActive && (
            <div className="border-t border-gray-100 bg-white">
              {/* Reply context bar */}
              {replyContext && (
                <div className="px-3 md:px-4 pt-2 pb-1.5 flex items-start gap-2 border-l border-brand-500 bg-brand-50/40 mx-2 sm:mx-3 md:mx-4 mt-2 rounded-tr-md">
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] font-bold text-brand-600 uppercase tracking-wide mb-0.5">
                      Replying to {replyContext.from === 'user' ? 'Customer'
                        : replyContext.from === 'ai' ? 'AI'
                        : (firstName(replyContext.sender_user) || 'Agent')}
                    </p>
                    <p className="text-xs text-gray-700 truncate">
                      {replyContext.text}
                    </p>
                  </div>
                  <button
                    onClick={() => setReplyContext(null)}
                    className="text-gray-400 hover:text-gray-700 p-0.5 shrink-0"
                    title="Cancel reply"
                  >
                    <X size={13} />
                  </button>
                </div>
              )}

              {sendError && (
                <div className="mx-2 sm:mx-3 md:mx-4 mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2">
                  <div className="flex items-start gap-2">
                    <AlertCircle size={13} className="text-red-600 shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-red-800">Message not sent</p>
                      <p className="text-[12px] text-red-700 mt-0.5 leading-snug">
                        {sendError.message || 'The reply could not be delivered.'}
                      </p>
                      <p className="text-[12px] text-gray-600 mt-1 truncate italic">
                        “{sendError.content}”
                      </p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <button
                          onClick={() => handleSend(sendError)}
                          disabled={sending}
                          className="text-[12px] font-bold text-white bg-red-600 hover:bg-red-700 rounded-md px-2.5 py-1 disabled:opacity-50"
                        >
                          {sending ? 'Retrying…' : 'Retry'}
                        </button>
                        <button
                          onClick={() => setSendError(null)}
                          className="text-[12px] font-semibold text-gray-500 hover:text-gray-800"
                        >
                          Discard
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Reassignment can happen while this thread is open on screen.
                  Freezing the composer rather than hiding the conversation is
                  deliberate — the agent keeps the history they were working
                  from, and can hand over properly, but cannot add to a thread
                  somebody else now owns. Two people answering the same customer
                  with different information is the failure this prevents.
                  The server enforces it too; this is the courtesy half. */}
              {activeConv.can_reply === false ? (
                <div className="px-2 sm:px-3 md:px-4 py-3">
                  <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
                    <Info size={15} className="text-amber-600 shrink-0 mt-0.5" />
                    <div className="text-xs text-amber-900">
                      <p className="font-bold">This conversation isn’t assigned to you</p>
                      <p className="mt-0.5 text-amber-800">
                        You can read everything that happened here, but only the
                        assigned agent can reply. Ask a supervisor to reassign it
                        if you need to take it back.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
              <div className="px-2 sm:px-3 md:px-4 py-2 sm:py-3 flex gap-1.5 sm:gap-2">
                <input
                  className="input flex-1 text-xs sm:text-sm"
                  placeholder="Reply…"
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
                  disabled={sending}
                />
                <button
                  onClick={() => handleSend()}
                  disabled={sending || !replyText.trim()}
                  className="btn-primary flex items-center gap-1 px-2 sm:px-4 py-2 disabled:opacity-50 whitespace-nowrap text-xs sm:text-sm"
                >
                  {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                  <span className="hidden sm:inline">Send</span>
                </button>
              </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )

  // ── AI context panel ─────────────────────────────────────────────────────
  const ContextPanel = (
    <div className={clsx(
      'border-l border-gray-100 p-4 overflow-y-auto bg-white',
      'hidden lg:block lg:w-56 lg:shrink-0',
    )}>
      {activeConv && <ContextContent conv={activeConv} />}
    </div>
  )

  const MobileContextDrawer = showContext && activeConv && (
    <div className="lg:hidden fixed inset-0 z-40 flex">
      <div className="absolute inset-0 bg-black/40" onClick={() => setShowContext(false)} />
      <div className="relative ml-auto w-72 max-w-full h-full bg-white p-4 overflow-y-auto shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <p className="section-title">AI Context</p>
          <button onClick={() => setShowContext(false)} className="btn-ghost p-1">
            <ArrowLeft size={15} />
          </button>
        </div>
        <ContextContent conv={activeConv} />
      </div>
    </div>
  )

  return (
    <div className="flex flex-col h-full">
      {/* Header. No bg-white: every other page lets the app background show
          through, so this one had a pale slab behind its title that appeared
          nowhere else — and in dark mode `bg-white` isn't themed at all. */}
      <div className="px-4 md:px-6 lg:px-8 pt-3 lg:pt-4 pb-2 shrink-0">
        <h1 className="text-xl lg:text-2xl font-bold text-gray-900">Inbox</h1>
        <p className="text-xs lg:text-sm text-gray-500 mt-0.5">Manage customer conversations across all channels</p>
      </div>

      {toast && (
        <div className="fixed bottom-5 right-5 z-[60] max-w-xs">
          <div className={clsx(
            'flex items-start gap-2.5 px-4 py-3 rounded-xl shadow-lg border text-sm',
            toast.type === 'warning'
              ? 'bg-amber-50 border-amber-200 text-amber-800'
              : 'bg-white border-gray-200 text-gray-800'
          )}>
            <span className="flex-1 leading-snug">{toast.text}</span>
            <button onClick={() => setToast(null)} className="text-current opacity-40 hover:opacity-70 shrink-0">
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Expanded attachment */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[70] bg-black/85 flex items-center justify-center p-4 cursor-zoom-out"
          onClick={() => setLightbox(null)}
        >
          <img
            src={lightbox}
            alt="attachment"
            className="max-h-full max-w-full rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightbox(null)}
            className="absolute top-4 right-4 p-2 rounded-lg bg-white/10 text-white hover:bg-white/20 transition-colors"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>
      )}

      {/* Main content area with border - fills remaining space */}
      <div className="flex-1 flex flex-col gap-0 overflow-hidden px-4 md:px-6 lg:px-8 pb-3 lg:pb-4 min-h-0">
        <div className="flex-1 flex flex-col gap-0 overflow-hidden rounded-3xl border border-gray-200 bg-white min-h-0">
          {/* Main content area - responsive toggle for small screens */}
          <div className="flex-1 flex gap-0 overflow-hidden min-h-0">
            {/* On small/medium screens: show only ConvList by default, toggle to ChatPanel when selected */}
            <div className="lg:hidden flex-1 flex overflow-hidden min-h-0">
              {selected ? ChatPanel : ConvList}
            </div>
            
            {/* On large screens: show all three panels */}
            <div className="hidden lg:flex flex-1 gap-0 overflow-hidden min-h-0">
              {ConvList}
              {ChatPanel}
              {ContextPanel}
            </div>
          </div>

          {MobileContextDrawer}
        </div>
      </div>
    </div>
  )
}

// Extracted so it can be used in both desktop panel and mobile drawer
//
// Three cards, each answering one question an agent has before they type:
//   1. What did the AI make of this?    (intent, search keywords, reply speed)
//   2. What shape is this conversation? (age, volume, channel, last inbound)
//   3. Who is on it?                    (handler, assignee, escalation)
//
// Everything is derived from conv.messages, so it re-computes on every poll —
// a new message lands, the panel updates. Nothing renders a bare em-dash: a
// field with no value says why it has none, because a column of dashes makes a
// working panel look broken.
function ContextContent({ conv }) {
  const messages = conv.messages || []
  const lastInbound = [...messages].reverse().find(m => m.from === 'user')
  const lastAiReply = [...messages].reverse().find(m => m.from === 'ai')

  // Intent is stored pipe-joined ("greeting|order_status|complaint")
  const intents = (lastInbound?.intent || '')
    .split('|')
    .map(t => t.trim())
    .filter(Boolean)

  // product_keyword is the search term the AI derived from the customer — from
  // their words, a forwarded post's caption, or vision reading a photo. It is
  // NOT what the AI recommended (that is product_url, which to_dict does not
  // serialise). It earns its place by exposing the mis-read: when someone sends
  // a screenshot and gets the wrong dress back, this is the line that says why.
  // 'Unknown' is what vision writes when it cannot tell — noise, not data.
  const searchedFor = []
  for (let i = messages.length - 1; i >= 0; i--) {
    const kw = (messages[i].product_keyword || '').trim()
    if (kw && kw.toLowerCase() !== 'unknown' && !searchedFor.includes(kw)) {
      searchedFor.push(kw)
    }
  }

  const inboundCount = messages.filter(m => m.from === 'user').length
  const replyCount = messages.filter(m => m.from !== 'user').length
  const firstMessageAt = messages[0]?.created_at

  // Use the generator's own measured time. Deriving it from created_at was
  // wrong: the outbound row is created BEFORE the AI runs, so the gap was
  // really the debounce window, not the response time — which is why this read
  // ~8s while the dashboard average read ~2s.
  const ms = lastAiReply?.ai_response_time_ms
  const responseTime = ms == null ? null : (ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's')
  const speedTone = ms == null ? 'text-gray-400'
    : ms < 3000 ? 'text-green-600'
    : ms < 10000 ? 'text-amber-600'
    : 'text-red-500'

  const prettyIntent = (t) => t.replace(/_/g, ' ')

  const Card = ({ title, icon, children }) => (
    <section className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <header className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-100 bg-gray-50">
        {icon}
        <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wide">{title}</h3>
      </header>
      <div className="px-3 py-2.5 space-y-3">{children}</div>
    </section>
  )

  const Row = ({ label, children }) => (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-gray-500 shrink-0">{label}</span>
      <span className="text-xs text-gray-800 font-medium text-right min-w-0 truncate">{children}</span>
    </div>
  )

  return (
    <div className="space-y-3">
      {/* Escalation sits above everything: it changes what you do next. */}
      {conv.handoff_reason && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
          <p className="text-[11px] font-bold text-amber-700 uppercase tracking-wide mb-1">
            Handed to a human
          </p>
          <p className="text-xs text-amber-800">
            {conv.handoff_reason === 'keyword'
              ? 'The customer used a word we always escalate on'
              : conv.handoff_reason === 'intent'
                ? 'The AI judged this needed a person'
                : conv.handoff_reason === 'rule'
                  ? 'An escalation rule matched'
                  /* Not a judgement about the customer — a fault on our side.
                     Worth saying plainly, because the agent picking this up has
                     no AI summary to read and should not go looking for one. */
                  : conv.handoff_reason === 'ai_unavailable'
                    ? 'The AI could not answer — nothing was sent to the customer but the handoff line'
                    /* Deliberately says what it COULDN'T do, not what it thinks
                       the item is. Showing a guess here would anchor the agent
                       to the same wrong product the AI was about to name. */
                    : conv.handoff_reason === 'image_unconfirmed'
                      ? 'A photo we could not confidently identify — the AI did not guess'
                      : conv.handoff_reason === 'image_unmatched'
                        ? 'A photo that matched no product in the catalogue'
                        : conv.handoff_reason}
          </p>
        </div>
      )}

      {/* 1 — What the AI made of it */}
      <Card title="What the AI made of this" icon={<Bot size={11} className="text-gray-400" />}>
        <div>
          <p className="text-[11px] text-gray-400 font-semibold mb-1.5">Detected intent</p>
          {intents.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {intents.map(i => (
                <span
                  key={i}
                  className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-brand-50 text-brand-700 border border-brand-100 capitalize"
                >
                  {prettyIntent(i)}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[12px] text-gray-400 italic">
              Nothing classified on the last customer message
            </p>
          )}
        </div>

        <div>
          <p className="text-[11px] text-gray-400 font-semibold mb-1.5 flex items-center gap-1">
            <Search size={9} /> Searched the catalogue for
          </p>
          {searchedFor.length > 0 ? (
            <>
              <ul className="space-y-1">
                {searchedFor.slice(0, 4).map(kw => (
                  <li key={kw} className="text-xs text-gray-700 flex items-start gap-1.5">
                    <span className="text-gray-300 mt-0.5 shrink-0">&bull;</span>
                    <span className="truncate" title={kw}>{kw}</span>
                  </li>
                ))}
              </ul>
              {searchedFor.length > 4 && (
                <p className="text-[11px] text-gray-400 mt-1">
                  +{searchedFor.length - 4} more earlier in the thread
                </p>
              )}
              <p className="text-[11px] text-gray-400 mt-1.5 leading-relaxed">
                If this does not match what they asked for, that is why the
                recommendation was off.
              </p>
            </>
          ) : (
            <p className="text-[12px] text-gray-400 italic">
              No product search ran on this conversation
            </p>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="text-[11px] text-gray-400 font-semibold flex items-center gap-1">
            <Zap size={9} /> Last AI reply took
          </span>
          <span className={clsx('text-xs font-bold', speedTone)}>
            {responseTime || 'No AI reply yet'}
          </span>
        </div>
      </Card>

      {/* 2 — Shape of the conversation */}
      <Card title="This conversation" icon={<Clock size={11} className="text-gray-400" />}>
        <Row label="Messages">{inboundCount} in &middot; {replyCount} out</Row>
        {firstMessageAt && <Row label="Started">{formatDayLabel(firstMessageAt)}</Row>}
        <Row label="Channel">
          <span className="capitalize">{(conv.platform || 'unknown').replace(/_/g, ' ')}</span>
        </Row>
        {lastInbound?.text && (
          <div className="pt-1">
            <p className="text-[11px] text-gray-400 font-semibold mb-1">Last thing they said</p>
            <p className="text-xs text-gray-700 leading-relaxed line-clamp-3">
              {lastInbound.text}
            </p>
          </div>
        )}
      </Card>

      {/* Everything else this customer has talked to us about.
          Threads fork once a resolved conversation is old enough — correct,
          but without this a returning customer reads as a stranger. */}
      {(conv.earlier_conversations || []).length > 0 && (
        <Card title="Earlier conversations" icon={<Clock size={11} className="text-gray-400" />}>
          <ul className="space-y-2">
            {conv.earlier_conversations.slice(0, 5).map(ec => (
              <li key={ec.id}>
                <a
                  href={`/messages?conversation=${ec.id}`}
                  className="block rounded-lg border border-gray-200 px-2.5 py-2 hover:border-gray-300 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold text-gray-500 capitalize truncate">
                      {(ec.channel || '').replace(/_/g, ' ')}
                    </span>
                    <span className="text-[11px] text-gray-400 shrink-0">
                      {ec.last_message_at ? formatDayLabel(ec.last_message_at) : ''}
                    </span>
                  </div>
                  <p className="text-xs text-gray-700 truncate mt-0.5">
                    {ec.last_message || 'No messages'}
                  </p>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    {ec.message_count} message{ec.message_count === 1 ? '' : 's'}
                    {ec.status === 'resolved' ? ' · resolved' : ''}
                  </p>
                </a>
              </li>
            ))}
          </ul>
          {conv.earlier_conversations.length > 5 && (
            <p className="text-[11px] text-gray-400">
              +{conv.earlier_conversations.length - 5} more
            </p>
          )}
        </Card>
      )}

      <ShopifyLinkCard conv={conv} />

      {/* 3 — Ownership */}
      <Card title="Who is handling it" icon={<UserCheck size={11} className="text-gray-400" />}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-gray-500">Right now</span>
          {handlerBadge(conv)}
        </div>
        <Row label="Customer">{conv.handle || 'Unknown handle'}</Row>
        {conv.assignee ? (
          <div className="pt-1 border-t border-gray-100">
            <p className="text-[11px] text-gray-400 font-semibold mb-1">Assigned to</p>
            <p className="text-xs text-gray-800 font-medium truncate">
              {conv.assignee.full_name}
            </p>
            <p className="text-[11px] text-gray-400 truncate">{conv.assignee.email}</p>
          </div>
        ) : (
          <p className="text-[12px] text-gray-400 italic pt-1 border-t border-gray-100">
            Not assigned to anyone yet
          </p>
        )}
      </Card>
    </div>
  )
}
