import {
  MessageSquare, Inbox, Bot, UserCheck, XCircle, Flag, Target, UserRound, Activity,
  AlertTriangle, AlertCircle, Info, Instagram, Smartphone, ShoppingBag,
  Download, FileText, File, Calendar, CalendarRange, Clock, TrendingUp as ChartTrendingUp, ChevronDown, X, Music,
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import clsx from 'clsx'
import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { getAnalyticsSummary, getAlerts, getMyLogs } from '../api/dashboard'
import { SkeletonCard } from '../components/Skeleton'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { useTimeAgo } from '../hooks/useTimeAgo'
import { exportAnalyticsCSV, exportAnalyticsPDF } from '../utils/reportExport'
import { parseBackendTime } from '../utils/time'
import { useAuth } from '../context/AuthContext'

// Fully-rounded ("pill") bar — all four corners, unlike default bars whose
// bottom sits flat on the axis. Radius auto-caps at half the width/height so
// short bars stay lozenge-shaped instead of over-rounding.
const RoundedBar = (props) => {
  const { x, y, width, height, fill } = props
  if (height <= 0 || width <= 0) return null
  const r = Math.min(width / 2, height / 2, 14)
  return (
    <path
      d={`
        M${x + r},${y}
        h${width - 2 * r}
        a${r},${r} 0 0 1 ${r},${r}
        v${height - 2 * r}
        a${r},${r} 0 0 1 ${-r},${r}
        h${-(width - 2 * r)}
        a${r},${r} 0 0 1 ${-r},${-r}
        v${-(height - 2 * r)}
        a${r},${r} 0 0 1 ${r},${-r}
        z`}
      fill={fill}
    />
  )
}

// Custom tooltip to ensure text is visible
const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        background: '#000000',
        border: 'none',
        borderRadius: '8px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        padding: '8px 12px'
      }}>
        {payload.map((entry, idx) => {
          const isTikTok = entry.name.includes('TikTok')
          return (
            <p key={idx} style={{ color: isTikTok ? '#ffffff' : (entry.color || '#ffffff'), fontSize: 10, fontFamily: 'Quicksand', margin: '2px 0' }}>
              {entry.name}: <span style={{ fontWeight: 'bold' }}>{entry.value}</span>
            </p>
          )
        })}
      </div>
    )
  }
  return null
}

// The -100 border shades are deliberate: index.css softens border-red-100 /
// -amber-100 / -green-100 for dark mode but has no override for the -200
// shades, so those rendered as a bright light line against a dark card and
// read as a heavy 2px rule. The backgrounds already carry the severity, so
// the border only needs to define the edge.
const alertStyles = {
  error:   { icon: AlertCircle,   cls: 'border-red-100 bg-red-50 text-red-600'       },
  warning: { icon: AlertTriangle, cls: 'border-amber-100 bg-amber-50 text-amber-600' },
  info:    { icon: Info,          cls: 'border-blue-100 bg-blue-50 text-blue-600'    },
}

// Mirrors NO_REPLY_LABELS in app/services.py — keep the two in sync.
// 'no_reason_recorded' is synthesised by the analytics layer for conversations
// no log accounts for; it is deliberately conspicuous.
const NO_REPLY_LABELS = {
  duplicate_webhook:           'Duplicate webhook',
  ai_master_switch_off:        'AI master switch off',
  settings_unreadable:         'Settings unreadable',
  channel_disabled:            'Channel disabled',
  conversation_ai_off:         'AI off for this chat',
  not_a_question:              "Comment wasn't a question",
  superseded_by_newer_message: 'Answered as part of a later message',
  dispatch_failed:             'Send to platform failed',
  pipeline_exception:          'Pipeline error',
  no_reason_recorded:          'No reason recorded',
}

// Below this many conversations a rate is theatre: at 7, one conversation
// swings it 14 points and the trend reads "↑129%". Arithmetically correct,
// practically meaningless. Shared by the KPI cards and the AI Performance
// card so the same metric can't be guarded in one place and not the other.
const SMALL_SAMPLE = 10

// How often Live Activity refetches. Short enough to deserve the "Live"
// badge, long enough not to hammer the API from an idle dashboard.
const ACTIVITY_POLL_MS = 20000
// Rows rendered in the feed — a glance at what's happening, not a log tail.
// The rest is a click away via "View All". Also the fetch size: asking for 50
// and showing a fraction just wasted the request.
const ACTIVITY_FEED_LIMIT = 12

const CHANNEL_META = {
  instagram: { name: 'Instagram', color: '#ec4899', icon: Instagram },
  whatsapp:  { name: 'WhatsApp',  color: '#22c55e', icon: Smartphone },
  facebook:  { name: 'Facebook',  color: '#3b82f6', icon: MessageSquare },
  tiktok:    { name: 'TikTok',    color: '#111111', icon: Music },
  other:     { name: 'Other',     color: '#6b7280', icon: Inbox },
}

// The verdict that makes a channel row actionable instead of decorative.
// Order matters — the first condition that trips is the one worth acting on.
const channelStatus = (c) => {
  if (c.inbound === 0)
    return { label: 'No traffic', cls: 'bg-gray-100 text-gray-500' }
  // No AI-eligible inbound at all: the AI was switched off for everything
  // that arrived here, so there's nothing to grade — it's a config choice.
  if (c.response_rate == null)
    return { label: 'AI off here', cls: 'bg-gray-100 text-gray-600' }
  if (c.handled_convos > 0 && c.escalated / c.handled_convos > 0.3)
    return { label: 'High escalation', cls: 'bg-purple-50 text-purple-700' }
  if (c.response_rate < 0.5)
    return { label: 'Low AI coverage', cls: 'bg-red-50 text-red-700' }
  if (c.avg_response_time_ms != null && c.avg_response_time_ms > 5000)
    return { label: 'Slow replies', cls: 'bg-amber-50 text-amber-700' }
  return { label: 'Healthy', cls: 'bg-green-50 text-green-700' }
}

const channelIcon = (ch) => {
  if (ch === 'instagram_dm' || ch === 'instagram_comment') return <Instagram size={13} className="text-pink-500" />
  if (ch === 'whatsapp')       return <Smartphone size={13} className="text-green-500" />
  if (ch === 'facebook_dm' || ch === 'facebook_comment')
    return <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded text-white font-black text-[9px]" style={{ background: '#1877F2' }}>f</span>
  if (ch === 'tiktok_dm' || ch === 'tiktok_comment')
    return <span className="inline-flex items-center justify-center w-3.5 h-3.5 rounded font-black text-[9px]" style={{ background: '#000000', color: '#ffffff' }}>♪</span>
  if (ch === 'shopify')        return <ShoppingBag size={13} className="text-emerald-500" />
  if (ch === 'alert')          return <AlertTriangle size={13} className="text-amber-500" />
  return <Bot size={13} className="text-brand-500" />
}

// Separate component for activity item to use the useTimeAgo hook
function ActivityItem({ item }) {
  const timeAgoStr = useTimeAgo(item.created_at)
  const isFault = item.level === 'error' || item.level === 'critical'

  const body = (
    <>
      <div className={clsx(
        'mt-0.5 shrink-0 w-5 h-5 rounded-lg flex items-center justify-center flex-shrink-0',
        isFault ? 'bg-red-50' : 'bg-gray-50'
      )}>
        {isFault ? <AlertCircle size={13} className="text-red-500" /> : channelIcon(item.channel)}
      </div>
      <div className="flex-1 min-w-0">
        <p className={clsx('text-sm leading-relaxed break-words',
                           isFault ? 'text-red-700 font-medium' : 'text-gray-800')}>
          {item.text}
        </p>
      </div>
      <span className="text-xs text-gray-400 shrink-0 font-medium whitespace-nowrap ml-2">{timeAgoStr}</span>
    </>
  )

  // Events tied to a conversation open it; system-level ones stay inert.
  if (item.conversation_id) {
    return (
      <a
        href={`/messages?conversation=${item.conversation_id}`}
        className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0 -mx-2 px-2 rounded-lg hover:bg-gray-50 transition-colors"
      >
        {body}
      </a>
    )
  }
  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0">
      {body}
    </div>
  )
}

// One row of the System Alerts panel. Shows how many times a fault has
// recurred and when it was last seen — without those, three identical rows of
// the same error looked like three separate problems, and a month-old failure
// looked as urgent as one from a minute ago.
function AlertRow({ alert }) {
  const lastSeen = useTimeAgo(alert.last_seen)
  const { icon: Icon, cls } = alertStyles[alert.severity] || alertStyles.info

  const inner = (
    <>
      <Icon size={13} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="leading-snug break-words">{alert.title}</p>
        <p className="mt-0.5 opacity-70 font-normal">
          {alert.detail || alert.source}
          {alert.count > 1 && <> · {alert.count}×</>}
          {alert.last_seen && <> · {lastSeen}</>}
        </p>
      </div>
    </>
  )

  const cn = clsx('flex items-start gap-2.5 p-3 rounded-lg border text-xs font-medium', cls)
  return alert.href
    ? <a href={alert.href} className={clsx(cn, 'hover:brightness-95 transition-all')}>{inner}</a>
    : <div className={cn}>{inner}</div>
}

// Extracted so useCountAnimation is called once, unconditionally, at the top
// level of a component. Calling it inside .map() + an if/else (as before)
// breaks the Rules of Hooks — the animated value stopped re-targeting when
// the period filter changed, so the KPI cards looked frozen.
function StatCard({ label, icon: Icon, color, bg, kpiKey, isPercentage, goodDirection,
                    sampleKey, kpis, periodLabel }) {
  const prev = kpis.previous || {}
  const currentValue = kpiKey ? (kpis[kpiKey] ?? 0) : 0
  const previousValue = kpiKey ? (prev[kpiKey] ?? 0) : 0

  // A rate needs enough underlying conversations for a comparison to mean
  // anything. Without this the Success Rate card cheerfully reported
  // "↑ 128.6%" off 7 conversations, while the AI Performance card beside it
  // suppressed the very same trend — the same metric behaving two ways on one
  // screen. sampleKey names the denominator; counts don't need one.
  const sample = sampleKey ? (kpis[sampleKey] ?? 0) : null
  const prevSample = sampleKey ? (prev[sampleKey] ?? 0) : null
  const thinSample = sample !== null && (sample < SMALL_SAMPLE || prevSample < SMALL_SAMPLE)

  const animatedValue = useCountAnimation(
    isPercentage ? currentValue * 100 : currentValue,
    2000,
    !!isPercentage
  )

  const displayValue = isPercentage ? `${animatedValue.toFixed(1)}%` : animatedValue

  const change = currentValue - previousValue
  const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '→'

  // Colour says "is this good news?", not "did the number go up?". Rising
  // Failed Replies and rising Escalations were both painted green, which
  // rewarded exactly the wrong movement. 'neutral' metrics (raw human reply
  // volume) stay grey — they're neither good nor bad on their own.
  const movedWell =
    goodDirection === 'up'   ? change > 0 :
    goodDirection === 'down' ? change < 0 :
                               null
  const colorClass =
    change === 0 || movedWell === null ? 'text-gray-500' :
    movedWell                          ? 'text-green-600' :
                                         'text-red-600'

  // Rates show RELATIVE change — 10% → 13.5% reads "↑ 35%", i.e. a third
  // better than last period. That's a true percentage, so it avoids the
  // original trap of printing "↑ 3.5%" for what was a 3.5 percentage-POINT
  // move. With no previous value there's nothing to divide by, so say so
  // rather than render Infinity.
  const relativeChange = previousValue !== 0 ? (change / Math.abs(previousValue)) * 100 : null
  // toFixed(0), matching the AI Performance card — 128.6% and 129% for the same
  // metric on the same screen was just two roundings of one number.
  const changeDisplay = !isPercentage
    ? Math.abs(change)
    : relativeChange === null
      ? (change === 0 ? '0%' : 'new')
      : `${Math.abs(relativeChange).toFixed(0)}%`

  return (
    <div className="stat-card min-w-0">
      <div className="flex items-start justify-between gap-2">
        <div className={clsx('w-9 h-9 rounded-xl flex items-center justify-center shrink-0', bg)}>
          <Icon size={18} className={color} />
        </div>
        {thinSample ? (
          <span className="text-[10px] font-semibold whitespace-nowrap text-gray-400">—</span>
        ) : (
          <span className={`text-[10px] font-semibold whitespace-nowrap ${colorClass}`}>
            {arrow} {changeDisplay}
          </span>
        )}
      </div>
      <p className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mt-2 tabular-nums truncate">{displayValue}</p>
      <p className="text-sm text-gray-500 font-semibold truncate">{label}</p>
      <p className="text-[10px] text-gray-400 truncate">
        {thinSample ? `${sample} convos · too few to compare` : `vs ${periodLabel}`}
      </p>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [analyticsData, setAnalyticsData] = useState(null)
  const [systemAlerts, setSystemAlerts] = useState([])
  const [activityLogs, setActivityLogs] = useState([])
  const [loadingAnalytics, setLoadingAnalytics] = useState(true)
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [loadingActivity, setLoadingActivity] = useState(true)
  const [showChannelModal, setShowChannelModal] = useState(false)
  const [periodOpen, setPeriodOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  const [selectedChannel, setSelectedChannel] = useState('all')  // 'all' | channel key
  const [period, setPeriod] = useState('month')  // 'today' | 'week' | 'month' | 'custom'
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [rangeError, setRangeError] = useState(null)
  const [alertsError, setAlertsError] = useState(null)

  // These are CALENDAR periods resolved server-side in the business timezone —
  // today starts at local midnight, week at the start of the week, month on
  // the 1st. They used to be rolling 1/7/30-day windows, so "This month" on
  // the 3rd mostly showed last month.
  const PERIOD_LABELS = { today: 'Today', week: 'This week', month: 'This month' }
  const PREVIOUS_LABELS = { today: 'yesterday', week: 'last week', month: 'last month' }
  const PERIOD_OPTIONS = [
    { key: 'today',  label: 'Today',      icon: Clock },
    { key: 'week',   label: 'This week',  icon: Calendar },
    { key: 'month',  label: 'This month', icon: ChartTrendingUp },
    { key: 'custom', label: 'Custom',     icon: CalendarRange },
  ]

  const todayISO = new Date().toISOString().split('T')[0]
  const customReady = Boolean(customStart && customEnd && customStart <= customEnd)

  // Load analytics summary
  useEffect(() => {
    // A half-filled custom range isn't an error yet — the user is still
    // picking. Leave the last good data on screen rather than blanking it.
    if (period === 'custom' && !customReady) return

    const load = async () => {
      setLoadingAnalytics(true)
      try {
        const data = await getAnalyticsSummary(
          period === 'custom' ? { start: customStart, end: customEnd } : { period }
        )
        setAnalyticsData(data)
        setRangeError(null)
      } catch (err) {
        console.error('Failed to load analytics:', err)
        setRangeError(err.message)
      } finally {
        setLoadingAnalytics(false)
      }
    }
    load()
  }, [period, customStart, customEnd, customReady])

  // Load system alerts. Now /api/alerts, which returns FAULTS grouped by
  // source — the panel used to call /logs/system with no level filter and
  // render the last 3 rows of any severity, so it showed things like "Access
  // token obtained" while hundreds of errors sat unseen behind them.
  //
  // Still permission-gated (admin + supervisor). The 403 is surfaced rather
  // than swallowed: an empty panel reading "All systems normal" is a different
  // claim from "you aren't allowed to see this".
  useEffect(() => {
    let cancelled = false
    const load = async (isFirst) => {
      if (isFirst) setLoadingAlerts(true)
      try {
        // Capped at 3 — deliberately. The panel is a "what's on fire right
        // now" glance, and its height drives the right-hand column, which in
        // turn decides whether Live Activity beside it has dead space. Grouping
        // means 3 rows can still represent hundreds of occurrences; the rest is
        // on the Logs page.
        const data = await getAlerts({ limit: 3 })
        if (!cancelled) { setSystemAlerts(data.alerts || []); setAlertsError(null) }
      } catch (err) {
        console.error('Failed to load system alerts:', err)
        if (!cancelled) setAlertsError(err.message || 'Could not load system alerts')
      } finally {
        if (isFirst && !cancelled) setLoadingAlerts(false)
      }
    }
    load(true)
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load(false)
    }, ACTIVITY_POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  // Load activity feed, then keep it current. The panel has always shown a
  // pulsing "Live" badge but only ever fetched once on mount, so it was a
  // static snapshot that quietly went stale the longer the tab stayed open.
  useEffect(() => {
    let cancelled = false
    const load = async (isFirst) => {
      if (isFirst) setLoadingActivity(true)
      try {
        const data = await getMyLogs({ per_page: ACTIVITY_FEED_LIMIT })
        if (!cancelled) setActivityLogs(data.logs || [])
      } catch (err) {
        console.error('Failed to load activity logs:', err)
      } finally {
        if (isFirst && !cancelled) setLoadingActivity(false)
      }
    }
    load(true)
    const id = setInterval(() => {
      // Don't poll into a hidden tab — it just burns requests.
      if (document.visibilityState === 'visible') load(false)
    }, ACTIVITY_POLL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

// Stat card definitions — same for empty + populated; the render block
  // reads kpiKey from analyticsData.kpis directly.
  // goodDirection drives the arrow's colour — see StatCard. 'neutral' means
  // the metric carries no inherent verdict: more human replies isn't good or
  // bad on its own, it depends entirely on why.
  const getStatCards = () => [
    // Inbound
    { label: 'Inbound',         kpiKey: 'inbound_total',        icon: MessageSquare, color: 'text-blue-500',   bg: 'bg-blue-50',   goodDirection: 'up'      },
    // Outbound — split by who replied
    { label: 'AI Replies',      kpiKey: 'ai_replies_total',     icon: Bot,           color: 'text-brand-500',  bg: 'bg-brand-50',  goodDirection: 'up'      },
    { label: 'Human Replies',   kpiKey: 'human_replies_total',  icon: UserCheck,     color: 'text-indigo-500', bg: 'bg-indigo-50', goodDirection: 'neutral' },
    // Quality
    { label: 'Failed Replies',  kpiKey: 'failed_responses',     icon: XCircle,       color: 'text-red-500',    bg: 'bg-red-50',    goodDirection: 'down'    },
    { label: 'Escalated',       kpiKey: 'escalated_total',      icon: Flag,          color: 'text-purple-500', bg: 'bg-purple-50', goodDirection: 'down'    },
    // sampleKey ties the trend to the number of conversations behind the rate.
    { label: 'Success Rate',    kpiKey: 'ai_success_rate',      icon: Target,        color: 'text-green-500',  bg: 'bg-green-50',  goodDirection: 'up', isPercentage: true, sampleKey: 'ai_handled_total' },
  ]

  // /api/alerts already returns faults grouped, ranked and capped, so this is
  // a straight pass-through — no client-side slicing to re-guess with.
  const getSystemAlerts = () => systemAlerts

// Compose a natural-language sentence from a structured log row.
  const formatActivityText = (log) => {
    const src = (log.source || '').toLowerCase()
    const p = log.payload || {}

    const chanName = ({
      instagram_dm:      'Instagram DM',
      instagram_comment: 'Instagram comment',
      whatsapp:          'WhatsApp',
      facebook_dm:       'Facebook DM',
      facebook_comment:  'Facebook comment',
      tiktok_dm:         'TikTok DM',
      tiktok_comment:    'TikTok comment',
    })[p.channel] || p.channel

    const userRef = p.user_external_id
      ? `@${p.user_external_id}`
      : (p.handle ? `@${p.handle}` : 'a customer')

    // ── Inbound message
    if (src === 'services.inbound') {
      return `${userRef} sent a message on ${chanName || 'an unknown channel'}${p.preview ? `: "${p.preview.slice(0, 60)}${p.preview.length > 60 ? '…' : ''}"` : ''}`
    }

    // ── AI reply
    if (src === 'services.ai_reply') {
      return `AI responded via ${chanName} to ${userRef}`
    }

    // ── Intents detected
    if (src === 'services.intents') {
      const list = (p.intents || []).join(', ')
      return `Detected intents: ${list || 'unknown'} for ${userRef}`
    }

    // ── Template reply used
    if (src === 'services.template_reply') {
      return `Template reply sent to ${userRef} on ${chanName}`
    }

    // ── AI suppressed (legacy source, kept so old rows still read properly)
    if (src === 'services.ai_suppressed') {
      return `AI gated off for ${userRef} on ${chanName}`
    }

    // ── No reply went out, and why. Replaces services.ai_suppressed.
    if (src === 'services.no_reply_sent') {
      const why = NO_REPLY_LABELS[p.reason] || p.reason || 'unknown reason'
      return `No AI reply to ${userRef} on ${chanName} — ${why.toLowerCase()}`
    }

    // ── Pipeline blew up
    if (src === 'services.pipeline_exception') {
      return `Pipeline error on ${chanName} for ${userRef} — message saved, needs a manual reply`
    }

    // ── Sync failure
    if (src === 'sync_jobs.failed') {
      return `Sync failed: ${p.kind || 'job'}${p.error ? ` — ${String(p.error).slice(0, 60)}` : ''}`
    }

    // ── Shopify product lookup
    if (src === 'services.shopify_lookup') {
      const stock = p.stock_quantity
      const stockStr = stock == null ? 'untracked' : `${stock} units`
      return `Shopify stock checked: ${p.product_name || p.product_keyword} — ${stockStr}`
    }

    // ── Shopify sync
    if (src === 'integrations.shopify.sync') {
      return `Shopify sync completed — ${p.count || 0} ${p.kind || 'records'} updated`
    }

    // ── Shopify token
    if (src === 'integrations.shopify.token') {
      return `Shopify access token refreshed`
    }

    // ── Handoff
    if (src === 'handoff.triggered') {
      return `Conversation handed off to human — ${p.reason || 'rule'}${p.detail ? `: "${p.detail}"` : ''}`
    }
    // The emitted source is 'handoff.auto_assigned' (app/handoff.py); this
    // case previously matched 'handoff.auto_assign' and so never fired.
    if (src === 'handoff.auto_assigned' || src === 'handoff.auto_assign') {
      return `Auto-assigned to ${p.agent_name || p.agent_email}${p.reason ? ` (${p.reason})` : ''}`
    }

    // ── Manual assignment
    if (src === 'assignment.assigned') {
      const verb = p.is_reassign ? 'reassigned' : 'assigned'
      return `Conversation ${verb} to ${p.agent_name || p.agent_email}`
    }
    if (src === 'assignment.unassigned') {
      return `Conversation unassigned`
    }

    // ── AI failure
    if (src === 'ai.generator.failure') {
      const reasonLabels = {
        rate_limit: 'rate limit hit', timeout: 'timed out', auth: 'auth error',
        bad_request: 'bad request', api_error: 'Claude API error',
        network: 'network error', bad_output: 'malformed response', unknown: 'unknown error',
      }
      const r = reasonLabels[p.reason] || p.reason || 'unknown error'
      return `AI reply failed — ${r} (fell back to mock)`
    }

    // Fallback to the raw message (cleaned up)
    if (log.message) {
      return log.message.replace(/^\[(MOCK|DEBUG|INFO|TEST)\]\s*/i, '')
    }
    return log.source ? `${log.source} event` : 'System activity'
  }

  const getActivityFeed = () => {
    // Belt and braces — the fetch already asks for exactly this many, but the
    // slice keeps the panel bounded if the endpoint ever returns more.
    return activityLogs.slice(0, ACTIVITY_FEED_LIMIT).map(log => {
      // Prefer payload.channel (now richly populated); fall back to source-based guess.
      const src = (log.source || '').toLowerCase()
      let iconChannel = 'system'
      if (log.payload?.channel) iconChannel = log.payload.channel
      else if (src.includes('shopify')) iconChannel = 'shopify'
      else if (src.includes('handoff') || src.includes('assignment')) iconChannel = 'alert'
      else if (src.includes('meta')) iconChannel = 'instagram_dm'
      else if (src.includes('ai')) iconChannel = 'system'

      return {
        id: log.id,
        text: formatActivityText(log),
        channel: iconChannel,
        created_at: log.created_at,
        // Carried so a feed line can be opened, not just read. A fault you
        // can't navigate to is a notification, not a tool.
        conversation_id: log.conversation_id,
        level: log.level,
      }
    })
  }

  const statCardsData = getStatCards()
  const systemAlertsData = getSystemAlerts()
  const activityFeedData = getActivityFeed()

  // Per-channel health, computed server-side against the same window as the
  // KPI cards, so the sheet can't disagree with the page behind it.
  const channelPerf = analyticsData?.channel_performance || []

  // Tiles beside the graph. Sourced from channel_performance rather than
  // re-bucketing channel_split by name, so a new channel variant (say
  // 'instagram_story') can't quietly fall out of the totals.
  const perfByChannel = Object.fromEntries(channelPerf.map(c => [c.channel, c]))
  const channelTiles = ['instagram', 'whatsapp', 'facebook', 'tiktok'].map(key => ({
    key,
    ...CHANNEL_META[key],
    row: perfByChannel[key] || { inbound: 0, prev_inbound: 0, escalated: 0, response_rate: null, handled_convos: 0 },
  }))

  // Real channel totals from analytics, scoped to the selected period.
  const channelSplit = analyticsData?.channel_split || []
  const channelStats = [
    { label: 'Instagram', value: channelSplit.filter(c => c.name.includes('instagram')).reduce((s, c) => s + c.count, 0) },
    { label: 'WhatsApp',  value: channelSplit.find(c => c.name === 'whatsapp')?.count || 0 },
    { label: 'Facebook',  value: channelSplit.filter(c => c.name.includes('facebook')).reduce((s, c) => s + c.count, 0) },
    { label: 'TikTok',    value: channelSplit.filter(c => c.name.includes('tiktok')).reduce((s, c) => s + c.count, 0) },
  ]

 // Real per-channel-per-day data from analytics.weekly
  const weekly = analyticsData?.weekly || []
// Trim leading days where nothing happened so the chart doesn't waste space
  const firstActiveIdx = weekly.findIndex(w =>
    (w.instagram || 0) + (w.whatsapp || 0) + (w.facebook || 0) + (w.tiktok || 0) > 0
  )
  const trimmedWeekly = firstActiveIdx === -1 ? weekly : weekly.slice(firstActiveIdx)

  // Weekday names only stay unambiguous for a week or less; past that the axis
  // would repeat "Mon, Tue…" and a custom 3-week range would read as nonsense.
  const dateAxis = (analyticsData?.window_days || 0) > 7
  const chartData = trimmedWeekly.map(w => ({
    time: dateAxis
      ? (parseBackendTime(w.date)?.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) || w.day)
      : w.day,
    // Instagram
    instagram: w.instagram || 0,
    instagram_ai: w.instagram_ai || 0,
    instagram_human: w.instagram_human || 0,
    // WhatsApp
    whatsapp: w.whatsapp || 0,
    whatsapp_ai: w.whatsapp_ai || 0,
    whatsapp_human: w.whatsapp_human || 0,
    // Facebook
    facebook: w.facebook || 0,
    facebook_ai: w.facebook_ai || 0,
    facebook_human: w.facebook_human || 0,
    // TikTok
    tiktok: w.tiktok || 0,
    tiktok_ai: w.tiktok_ai || 0,
    tiktok_human: w.tiktok_human || 0,
  }))

  // "9 Jun" for a single day, "30 May – 18 Jun" for a range. Parsed as local
  // noon so a plain YYYY-MM-DD isn't dragged back a day by the UTC offset.
  const fmtDay = (iso) => {
    if (!iso) return ''
    const [y, m, d] = iso.split('-').map(Number)
    return new Date(y, m - 1, d, 12).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }
  const periodLabel = period !== 'custom'
    ? PERIOD_LABELS[period]
    : !customReady
      ? 'Custom range'
      : customStart === customEnd
        ? fmtDay(customStart)
        : `${fmtDay(customStart)} – ${fmtDay(customEnd)}`
  const previousLabel = period !== 'custom'
    ? PREVIOUS_LABELS[period]
    : (analyticsData?.window_days === 1
        ? 'the day before'
        : `the previous ${analyticsData?.window_days || ''} days`.replace('  ', ' '))

  // Slug comes from the window the API actually resolved, not from what's
  // typed in the pickers — mid-edit those disagree, and the filename must
  // describe the data inside the file.
  // Which lines the chart draws. "All" = one inbound series per channel, so
  // channels are comparable at a glance. A single channel = its three series,
  // so you can see whether AI or a human is carrying it.
  const chartSeries = selectedChannel === 'all'
    ? ['instagram', 'whatsapp', 'facebook', 'tiktok'].map(k => ({
        dataKey: k, name: CHANNEL_META[k].name, stroke: CHANNEL_META[k].color, dash: undefined,
      }))
    : [
        { dataKey: selectedChannel,             name: 'Inbound',      stroke: CHANNEL_META[selectedChannel].color, dash: undefined },
        { dataKey: `${selectedChannel}_ai`,     name: 'AI replies',   stroke: CHANNEL_META[selectedChannel].color, dash: '4 2' },
        { dataKey: `${selectedChannel}_human`,  name: 'Human replies', stroke: '#c7ea46',                          dash: '8 4' },
      ]

  const exportMeta = () => ({
    // A custom range's label IS its dates, and the exporter prints those
    // exactly (with the year) anyway — passing it too gives "Jun 10 (Jun 10,
    // 2026)". Named periods still get their friendly prefix.
    periodLabel: period === 'custom' ? '' : periodLabel,
    generatedAt: new Date().toLocaleString(),
    periodSlug: period === 'custom'
      ? (analyticsData?.window_start && analyticsData?.window_end
          ? `${analyticsData.window_start}_${analyticsData.window_end}`
          : 'custom')
      : period,
    dateSlug: new Date().toISOString().split('T')[0],
  })
  const exportToCSV = () => exportAnalyticsCSV(analyticsData || {}, exportMeta())
  const exportToPDF = () => exportAnalyticsPDF(analyticsData || {}, exportMeta())

  return (
    <div className="space-y-6 w-full">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Live overview of your AI support system</p>
        </div>
        
        {/* Period filters + Export */}
        <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
          {/* Desktop: Button group */}
          <div className="hidden sm:flex items-center gap-1.5 bg-white border border-gray-200 rounded-xl p-1.5 shadow-sm">
            {PERIOD_OPTIONS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setPeriod(key)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                  period === key
                    ? 'bg-black text-white shadow-md'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                )}
              >
                <Icon size={14} />
                <span>{label}</span>
              </button>
            ))}
          </div>

          {/* Mobile: Dropdown */}
          <div className="sm:hidden relative">
            <button onClick={() => setPeriodOpen(o => !o)} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors shadow-sm">
              <Clock size={14} />
              <span>{periodLabel}</span>
              <ChevronDown size={14} className={clsx('transition-transform', periodOpen && 'rotate-180')} />
            </button>
            {periodOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setPeriodOpen(false)} />
                <div className="absolute left-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
                  {PERIOD_OPTIONS.map(({ key, label, icon: Icon }) => (
                    <button
                      key={key}
                      onClick={() => { setPeriod(key); setPeriodOpen(false) }}
                  className={clsx(
                    'w-full text-left px-4 py-2.5 text-xs font-semibold flex items-center gap-2 transition-colors',
                    'first:rounded-t-lg last:rounded-b-lg',
                    period === key
                      ? 'bg-black text-white'
                      : 'text-gray-700 hover:bg-gray-50'
                  )}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
                </div>
              </>
            )}
          </div>

          {/* Export dropdown */}
          <div className="relative">
            {/* Disabled until a window has actually loaded — exporting mid-fetch
                would write out the previous period's numbers under this one's
                heading. */}
            <button
              onClick={() => setExportOpen(o => !o)}
              disabled={loadingAnalytics || !analyticsData}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-black text-white text-xs font-semibold hover:bg-gray-900 transition-colors shadow-sm disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-black"
            >
              <Download size={14} />
              <span>Export</span>
            </button>
            {exportOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setExportOpen(false)} />
                <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
                  <button onClick={() => { exportToCSV(); setExportOpen(false) }} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 first:rounded-t-lg">
                    <FileText size={13} />
                    Export as CSV
                  </button>
                  <button onClick={() => { exportToPDF(); setExportOpen(false) }} className="w-full text-left px-4 py-2.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2 last:rounded-b-lg">
                    <File size={13} />
                    Export as PDF
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Custom range picker — only while 'Custom' is the active period.
          Both ends are inclusive, so leaving them equal reports a single day. */}
      {period === 'custom' && (
        <div className="card p-4 flex flex-col sm:flex-row sm:items-end gap-3">
          <div className="flex-1 min-w-0">
            <label className="block text-[11px] font-semibold text-gray-700 mb-1.5">From</label>
            <input
              type="date"
              value={customStart}
              max={customEnd || todayISO}
              onChange={e => setCustomStart(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition"
            />
          </div>
          <div className="flex-1 min-w-0">
            <label className="block text-[11px] font-semibold text-gray-700 mb-1.5">To</label>
            <input
              type="date"
              value={customEnd}
              min={customStart || undefined}
              max={todayISO}
              onChange={e => setCustomEnd(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm text-gray-900 bg-white focus:outline-none focus:ring-1 focus:ring-brand-500/30 focus:border-brand-500 transition"
            />
          </div>
          <button
            type="button"
            onClick={() => { setCustomStart(todayISO); setCustomEnd(todayISO) }}
            className="shrink-0 px-3 py-2 rounded-lg border border-gray-200 text-xs font-semibold text-gray-600 hover:text-gray-900 hover:bg-gray-50 transition-colors"
          >
            Just today
          </button>
          <p className="text-[11px] text-gray-400 sm:ml-1 sm:pb-2.5 shrink-0">
            {rangeError
              ? <span className="text-red-600 font-medium">{rangeError}</span>
              : customReady
                ? `${analyticsData?.window_days ?? ''} day${analyticsData?.window_days === 1 ? '' : 's'} · vs ${previousLabel}`
                : 'Pick both dates'}
          </p>
        </div>
      )}

      {/* Agents' KPIs count only conversations assigned to them, while the
          activity feed also shows the unassigned queue they can pick up. Both
          are right — "what's mine" vs "what I can act on" — but nothing said
          so, which made a queued escalation appear in the feed and never in
          the Escalated count. */}
      {user?.role === 'agent' && (
        <p className="-mb-2 text-xs text-gray-400">
          Figures below cover <span className="font-semibold text-gray-500">your conversations</span> only
        </p>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCardsData.map((card) => (
          <StatCard
            key={`${card.label}-${period}`}
            {...card}
            kpis={analyticsData?.kpis || {}}
            periodLabel={previousLabel}
          />
        ))}
      </div>

      {/* Channel Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Graph: 3/4 width */}
        <div className="lg:col-span-3 card p-6">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-gray-900">Channel Performance</h2>
              <p className="text-xs text-gray-500 mt-1">
                {selectedChannel === 'all'
                  ? 'Inbound volume per channel — pick one to see how it’s being answered'
                  : `${CHANNEL_META[selectedChannel].name}: inbound vs AI replies vs human replies`}
              </p>
            </div>
            <button
              onClick={() => setShowChannelModal(true)}
              className="text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors whitespace-nowrap shrink-0"
            >
              View Details →
            </button>
          </div>

          {/* Channel selector. "All" compares channels against each other on a
              single series each; picking one switches to the diagnostic view
              of who is answering it. Showing all 12 series at once — 4
              channels x inbound/AI/human — was unreadable and told you
              nothing you could act on. */}
          <div className="flex flex-wrap items-center gap-1.5 mb-5">
            {[{ key: 'all', name: 'All channels', color: '#111111' },
              ...['instagram', 'whatsapp', 'facebook', 'tiktok'].map(k => ({ key: k, ...CHANNEL_META[k] }))
            ].map(({ key, name, color }) => {
              const active = selectedChannel === key
              return (
                <button
                  key={key}
                  onClick={() => setSelectedChannel(key)}
                  className={clsx(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors',
                    active ? 'bg-gray-900 text-white' : 'text-gray-600 hover:bg-gray-100'
                  )}
                >
                  {key !== 'all' && (
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ background: active ? '#fff' : color }}
                    />
                  )}
                  {name}
                </button>
              )
            })}
          </div>

          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 20, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid stroke="rgba(0,0,0,0.05)" vertical={false} strokeDasharray="0" />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 12, fill: '#a1a1aa', fontFamily: 'Quicksand' }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 12, fill: '#a1a1aa', fontFamily: 'Quicksand' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              {chartSeries.map(({ dataKey, name, stroke, dash }) => (
                <Line
                  key={dataKey}
                  type="natural"
                  dataKey={dataKey}
                  name={name}
                  stroke={stroke}
                  strokeWidth={2}
                  strokeDasharray={dash}
                  dot={false}
                  activeDot={{ r: 6 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          {/* Legend — mirrors whatever the selector is currently showing */}
          <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-5 mt-5 text-[11px]">
            {chartSeries.map(({ dataKey, name, stroke, dash }) => (
              <div key={dataKey} className="flex items-center gap-1.5">
                <svg width="16" height="2">
                  <line x1="0" y1="1" x2="16" y2="1" stroke={stroke} strokeWidth="2" strokeDasharray={dash} />
                </svg>
                <span className="text-gray-600 font-medium">{name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Stats: 1/4 width. Each tile carries the volume AND whether that
            volume is moving, so it's a signal rather than a decorated number.
            Clicking opens the sheet for the full per-channel breakdown. */}
        <div className="lg:col-span-1 space-y-3">
          {channelTiles.map(({ key, name, color, row }) => {
            const delta = row.inbound - row.prev_inbound
            const status = channelStatus(row)
            return (
              <button
                key={key}
                onClick={() => setShowChannelModal(true)}
                className="card w-full text-left p-4 hover:border-gray-300 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-600 truncate">{name}</span>
                  </span>
                  <span className={clsx(
                    'text-[10px] font-semibold tabular-nums shrink-0',
                    delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-600' : 'text-gray-400'
                  )}>
                    {delta > 0 ? '↑' : delta < 0 ? '↓' : '→'} {Math.abs(delta)}
                  </span>
                </div>
                <p className="text-2xl font-bold text-gray-900 mt-2 tabular-nums">{row.inbound}</p>
                <div className="flex items-center justify-between gap-2 mt-1">
                  <span className="text-[11px] text-gray-400 truncate">inbound · {periodLabel}</span>
                  {status.label !== 'Healthy' && (
                    <span className={clsx('shrink-0 px-1.5 py-0.5 rounded text-[9px] font-semibold', status.cls)}>
                      {status.label}
                    </span>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activity feed */}
        <div className="lg:col-span-2 card p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4 shrink-0">
            <h2 className="text-sm font-bold text-gray-900">Live Activity</h2>
            <span className="flex items-center gap-3">
              <a href="/logs" className="text-xs text-brand-600 hover:text-brand-700 font-semibold transition-colors">
                View All →
              </a>
              <span className="flex items-center gap-1.5 text-xs text-green-600 font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} />
              Live
              </span>
            </span>
          </div>
          {/* Fills the card, which the grid stretches to match the taller
              right-hand column. That only stays gap-free while the right
              column is roughly the height of this list — which is why System
              Alerts is capped at 3 rows. If that column grows again, the dead
              space comes back and the cap is the thing to revisit. */}
          <div className="flex-1 min-h-0 max-h-[600px] lg:max-h-none overflow-y-auto pr-2 -mr-2 custom-scrollbar">
            <div className="space-y-3">
              {loadingActivity ? (
                <div className="py-8 text-center text-xs text-gray-400">Loading activity…</div>
              ) : activityFeedData.length === 0 ? (
                <div className="py-8 text-center text-xs text-gray-400">No recent activity</div>
              ) : (
                activityFeedData.map((item) => (
                  <ActivityItem key={item.id} item={item} />
                ))
              )}
            </div>
          </div>
        </div>

        {/* Alerts + quick stats */}
        <div className="space-y-4">
          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              {/* An agent's alerts are their own queue and conversations, not
                  infrastructure — calling that "System Alerts" would be a
                  promise the panel doesn't keep for them. */}
              <h2 className="text-sm font-bold text-gray-900">
                {user?.role === 'agent' ? 'Needs Attention' : 'System Alerts'}
              </h2>
              <a href="/logs" className="text-xs text-brand-600 hover:text-brand-700 font-semibold transition-colors">
                View All →
              </a>
            </div>
            <div className="space-y-2.5">
              {loadingAlerts ? (
                <div className="py-6 text-center text-xs text-gray-400">Loading…</div>
              ) : alertsError ? (
                <div className="py-6 text-center text-xs text-gray-400">
                  {/^.*\b(403|forbidden|only admins)\b.*$/i.test(alertsError)
                    ? 'System alerts are visible to admins and supervisors'
                    : 'Couldn’t load system alerts'}
                </div>
              ) : systemAlertsData.length === 0 ? (
                <div className="py-6 text-center text-xs text-gray-400">
                  {user?.role === 'agent'
                    ? 'Nothing needs your attention'
                    : 'Nothing broken in the last 7 days'}
                </div>
              ) : (
                systemAlertsData.map((alert, i) => (
                  <AlertRow key={`${alert.kind}-${alert.source || 'queue'}-${i}`} alert={alert} />
                ))
              )}
            </div>
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <p className="section-title">AI Performance</p>
              <span className="text-[10px] font-semibold text-gray-400">{periodLabel}</span>
            </div>
            {(() => {
              const kpis = analyticsData?.kpis || {}
              const successRate = ((kpis.ai_success_rate || 0) * 100)
              const handled = kpis.ai_handled_total || 0
              const engaged = kpis.ai_engaged_total || 0
              const avgResponseMs = kpis.avg_response_time_ms
              const avgResponseStr = avgResponseMs == null
                ? '—'
                : avgResponseMs < 1
                  ? '<1ms'
                  : avgResponseMs < 1000
                    ? `${avgResponseMs}ms`
                    : `${(avgResponseMs / 1000).toFixed(1)}s`
              const escalated = kpis.escalated_total || 0
              const failed = kpis.failed_responses || 0
              // Computed server-side now. It used to divide human_override_total
              // (events timed by ai_disabled_at) by conversations_total
              // (conversations merely ACTIVE in the window) — two different
              // populations, so the rate could exceed 100%. It's now the share
              // of AI-on-duty conversations a human took over, the same
              // denominator as the success rate above it.
              const overrideRate = ((kpis.override_rate || 0) * 100).toFixed(1)
              const responseRate = ((kpis.ai_response_rate || 0) * 100).toFixed(1)

              // Trend on the headline number, same relative-% convention as the
              // KPI cards. The card carried no comparison at all, so a 57%
              // success rate read the same whether it had doubled or halved.
              const prevSuccess = (kpis.previous?.ai_success_rate || 0) * 100
              const delta = successRate - prevSuccess
              const relDelta = prevSuccess !== 0 ? (delta / prevSuccess) * 100 : null

              // Below this many conversations a percentage is theatre: at 7
              // handled, one conversation swings the rate 14 points and the
              // trend reads "↑129%". Arithmetically right, practically
              // meaningless — so show the fraction and drop the trend rather
              // than implying precision the sample can't carry.
              const SMALL_SAMPLE = 10
              const thinSample = handled > 0 && handled < SMALL_SAMPLE
              const prevHandled = kpis.previous?.ai_handled_total || 0
              const showTrend = relDelta !== null && Math.abs(delta) >= 0.05
                                && !thinSample && prevHandled >= SMALL_SAMPLE

              // Conversations the AI was on duty for and never answered, across
              // all channels. Summed from channel_performance, which covers
              // every channel including 'other', so it reconciles with the
              // handled figure beside it.
              const neverAnswered = channelPerf.reduce((s, c) => s + (c.no_reply_convos || 0), 0)

              return (
                <>
                  {/* Hero: success rate + progress + context */}
                  <div className="mb-4">
                    <div className="flex items-end justify-between mb-2">
                      <div>
                        <div className="flex items-baseline gap-2">
                          {/* The percentage is the metric — it stays the
                              headline at every sample size. A thin sample
                              suppresses the TREND (see showTrend), because a
                              comparison is what small numbers can't support;
                              the rate itself is still the thing you came to
                              read. Demoting it to "3/7" buried the number the
                              card exists to show. */}
                          <p className="text-3xl font-bold text-brand-500 leading-none">
                            {successRate.toFixed(1)}%
                          </p>
                          {showTrend && (
                            <span className={clsx(
                              'text-[11px] font-semibold',
                              delta > 0 ? 'text-green-600' : 'text-red-600'
                            )}>
                              {delta > 0 ? '↑' : '↓'} {Math.abs(relDelta).toFixed(0)}%
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-1.5 font-medium">
                          Success rate
                          {showTrend && <span className="text-gray-400"> · vs {previousLabel}</span>}
                          {thinSample && (
                            <span className="text-gray-400"> · too few to trend</span>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-brand-500 rounded-full transition-all" style={{ width: `${Math.min(successRate, 100)}%` }} />
                    </div>

                    {/* "3 of 5" and "1 of 5" sat in opposite corners with
                        nothing saying they described the SAME 5, so they read
                        as two unrelated facts. One stem, both facts hanging
                        off it, so the relationship is impossible to misread. */}
                    {handled > 0 && (
                      <div className="mt-3 text-[11px]">
                        <p className="text-gray-500">
                          Of the <span className="font-bold text-gray-900 tabular-nums">{handled}</span>
                          {' '}conversation{handled === 1 ? '' : 's'} the AI was on duty for:
                        </p>
                        <div className="mt-1.5 space-y-1">
                          <p className="flex items-center gap-2 text-gray-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />
                            <span><span className="font-bold text-gray-900 tabular-nums">{engaged}</span> handled successfully</span>
                          </p>
                          {neverAnswered > 0 && (
                            <button
                              type="button"
                              onClick={() => setShowChannelModal(true)}
                              className="flex items-center gap-2 text-left w-full hover:underline"
                            >
                              <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                              <span className={clsx(
                                neverAnswered / handled >= 0.25 ? 'font-semibold text-red-600' : 'text-gray-600'
                              )}>
                                <span className="font-bold tabular-nums">{neverAnswered}</span> never answered — nobody replied at all
                                <span className="text-gray-400 font-normal"> · see which →</span>
                              </span>
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Metrics strip */}
                  <div className="grid grid-cols-2 gap-x-4 gap-y-3 pt-3 border-t border-gray-100">
                    {[
                      { label: 'Response rate', value: `${responseRate}%`,   color: 'text-brand-600' },
                      { label: 'Avg response',  value: avgResponseStr,       color: 'text-gray-900'  },
                      { label: 'Override rate', value: `${overrideRate}%`,    color: 'text-amber-600' },
                      { label: 'Escalated',     value: escalated,            color: 'text-purple-600'},
                      { label: 'Failed',        value: failed,               color: failed > 0 ? 'text-red-600' : 'text-gray-900' },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="flex flex-col">
                        <span className={clsx('text-lg font-bold leading-none', color)}>{value}</span>
                        <span className="text-[11px] text-gray-500 mt-1">{label}</span>
                      </div>
                    ))}
                  </div>
                </>
              )
            })()}
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <p className="section-title">Conversion Rate</p>
              <span className="text-[10px] font-semibold text-gray-400">{periodLabel}</span>
            </div>
            {(() => {
              const conv = analyticsData?.conversion || {}
              const recommended = conv.recommended_conversations || 0
              const converted = conv.converted_conversations || 0
              const rate = (conv.conversion_rate || 0) * 100
              const revenue = conv.attributed_revenue || 0
              const orders = conv.attributed_orders || 0
              const rows = [
                { label: 'Recommended', value: recommended, total: null, color: 'bg-orange-500' },
                { label: 'Converted',   value: converted, total: recommended, color: 'bg-black' },
                { label: 'Conversion',  value: `${rate.toFixed(1)}%`, total: null, color: 'bg-orange-600' },
              ]
              return (
                <>
                  <div className="space-y-3">
                    {rows.map(({ label, value, total, color }) => (
                      <div key={label}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-xs font-medium text-gray-600">{label}</span>
                          <span className="text-xs font-bold text-gray-900">
                            {total ? `${value}/${total}` : value}
                          </span>
                        </div>
                        {total ? (
                          <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={clsx('h-full rounded-full transition-all', color)}
                              style={{ width: `${(value / total) * 100}%` }}
                            />
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-600">Revenue driven</span>
                    {/* Currency comes from the data, not a hardcoded "KES" —
                        totals used to be summed across currencies and labelled
                        KES regardless. Net of tax, using Shopify's own
                        total_tax per order. */}
                    <span className="text-sm font-bold text-gray-900">
                      {conv.revenue_currency || 'KES'} {Math.round(revenue).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-[10px] text-gray-400 mt-1">
                    {orders} attributed order{orders === 1 ? '' : 's'} · excl. tax
                  </p>
                  {conv.revenue_excluded_orders > 0 && (
                    <p className="text-[10px] text-amber-600 font-medium mt-1">
                      {conv.revenue_excluded_orders} order{conv.revenue_excluded_orders === 1 ? '' : 's'} in
                      another currency not included
                    </p>
                  )}
                </>
              )
            })()}
          </div>
        </div>
      </div>

      {/* Channel Performance Slide-over — portalled to <body> so `fixed`
          anchors to the viewport. Inside the Layout tree an ancestor creates
          a containing block, which was offsetting the sheet from the top. */}
      {showChannelModal && createPortal(
        <div className="fixed inset-0 z-50">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm animate-[fadeIn_.2s_ease-out]"
            onClick={() => setShowChannelModal(false)}
          />
          {/* Sheet */}
          <div
            className="absolute top-0 right-0 h-full w-full sm:max-w-xl lg:max-w-2xl bg-white shadow-2xl border-l border-gray-100 flex flex-col animate-[slideInRight_.28s_cubic-bezier(0.16,1,0.3,1)]"
          >
            {/* Header */}
            <div className="shrink-0 bg-white/90 backdrop-blur-xl border-b border-gray-100 px-5 sm:px-6 py-5 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h2 className="text-lg sm:text-xl font-semibold text-gray-900 truncate">Channel Performance</h2>
                <p className="text-sm text-gray-500 mt-1">Where the AI is coping, and where it isn’t • {periodLabel}</p>
              </div>
              <button
                onClick={() => setShowChannelModal(false)}
                className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all shrink-0"
                aria-label="Close"
              >
                <X size={20} />
              </button>
            </div>

            {/* Content — one row per channel, ranked by volume.
                Deliberately NOT a KPI grid: the four tiles that used to sit
                here (Total Inbound / AI Replies / Human Replies / Response
                Rate) restated the cards already on the page behind the sheet,
                and derived them by re-summing the chart series, so they
                silently dropped the 'other' bucket and could disagree with
                those cards. The sheet's job is the one thing the Dashboard
                can't tell you: WHICH channel needs attention. */}
            <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-5">
              {channelPerf.length === 0 ? (
                <p className="py-12 text-center text-sm text-gray-400">
                  No channel activity in this period.
                </p>
              ) : (
                <div className="divide-y divide-gray-100">
                  {channelPerf.map((c) => {
                    const meta = CHANNEL_META[c.channel] || CHANNEL_META.other
                    const Icon = meta.icon
                    const status = channelStatus(c)
                    const delta = c.inbound - c.prev_inbound
                    // Who is carrying this channel's replies.
                    const replies = c.ai_replies + c.human_replies
                    const aiShare = replies > 0 ? (c.ai_replies / replies) * 100 : 0

                    return (
                      <div key={c.channel} className="py-5 first:pt-0 last:pb-0">
                        {/* Identity + volume */}
                        <div className="flex items-start justify-between gap-3 mb-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div
                              className="w-9 h-9 rounded-xl flex items-center justify-center text-white shrink-0"
                              style={{ background: meta.color }}
                            >
                              <Icon size={17} />
                            </div>
                            <div className="min-w-0">
                              <h4 className="font-semibold text-gray-900 text-sm truncate">{meta.name}</h4>
                              <p className="text-[11px] text-gray-500">
                                {c.share}% of inbound
                              </p>
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="text-xl font-bold text-gray-900 leading-none tabular-nums">{c.inbound}</p>
                            <p className="text-[11px] mt-1 tabular-nums">
                              <span className={clsx(
                                'font-semibold',
                                delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-600' : 'text-gray-400'
                              )}>
                                {delta > 0 ? '↑' : delta < 0 ? '↓' : '→'} {Math.abs(delta)}
                              </span>
                              <span className="text-gray-400"> vs {previousLabel}</span>
                            </p>
                          </div>
                        </div>

                        {/* Who replied — AI vs human. A channel drifting to
                            human is the thing worth seeing at a glance. */}
                        {replies > 0 && (
                          <div className="mb-3">
                            <div className="flex h-1.5 rounded-full overflow-hidden bg-gray-100">
                              <div style={{ width: `${aiShare}%`, background: meta.color }} />
                              <div style={{ width: `${100 - aiShare}%`, background: '#c7ea46' }} />
                            </div>
                            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-gray-500 tabular-nums">
                              {/* Spelled out as REPLIES because the block
                                  below counts conversations — two units, one
                                  row, was exactly what made the old layout
                                  misread. */}
                              <span className="flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.color }} />
                                {c.ai_replies} AI replies
                              </span>
                              <span className="flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-brand-500" />
                                {c.human_replies} human replies
                              </span>
                            </div>
                          </div>
                        )}

                        {/* What became of every conversation the AI was on
                            duty for. The answered rate alone left the
                            remainder unexplained — and being a CONVERSATION
                            rate sitting beside message counts, it read as if
                            it were about messages. This spells out both. */}
                        {c.handled_convos > 0 && (
                          <div className="mb-3 rounded-xl bg-gray-50 px-3 py-2.5">
                            <p className="text-[11px] text-gray-500 mb-1.5">
                              <span className="font-bold text-gray-900 tabular-nums">{c.handled_convos}</span>
                              {' '}conversation{c.handled_convos === 1 ? '' : 's'} the AI was on duty for
                            </p>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                              <span className="flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                                <span className="font-bold text-gray-900 tabular-nums">{c.answered_convos}</span>
                                <span className="text-gray-500">answered by AI</span>
                              </span>
                              {c.human_convos > 0 && (
                                <span className="flex items-center gap-1.5">
                                  <span className="w-1.5 h-1.5 rounded-full bg-brand-500" />
                                  <span className="font-bold text-gray-900 tabular-nums">{c.human_convos}</span>
                                  <span className="text-gray-500">picked up by a human</span>
                                </span>
                              )}
                              {c.no_reply_convos > 0 && (
                                <span className="flex items-center gap-1.5">
                                  <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                                  <span className="font-bold text-red-600 tabular-nums">{c.no_reply_convos}</span>
                                  <span className="text-gray-500">never answered</span>
                                </span>
                              )}
                            </div>

                            {/* Why, then WHICH. Reasons come from
                                services.no_reply_sent so the system explains
                                its own silence; the list underneath names the
                                actual conversations, because a count of
                                dropped customers you can't open is a
                                statistic rather than a worklist. */}
                            {c.no_reply_convos > 0 && (
                              <div className="mt-2 pt-2 border-t border-gray-200/70">
                                <ul className="space-y-0.5">
                                  {Object.entries(c.no_reply_reasons || {})
                                    .sort((a, b) => b[1] - a[1])
                                    .map(([reason, n]) => (
                                      <li key={reason} className="text-[11px] text-gray-500 flex items-start gap-1.5">
                                        <span className="text-gray-300">↳</span>
                                        <span>
                                          <span className="font-bold text-gray-900 tabular-nums">{n}</span>
                                          {' '}
                                          <span className={reason === 'no_reason_recorded' ? 'text-red-600 font-medium' : ''}>
                                            {NO_REPLY_LABELS[reason] || reason}
                                          </span>
                                        </span>
                                      </li>
                                    ))}
                                </ul>

                                {(c.no_reply_sample || []).length > 0 && (
                                  <div className="mt-2 pt-2 border-t border-gray-200/70 space-y-1">
                                    {c.no_reply_sample.map(r => (
                                      <a
                                        key={r.conversation_id}
                                        href={`/messages?conversation=${r.conversation_id}`}
                                        className="flex items-center gap-2 rounded-lg px-2 py-1.5 -mx-1 hover:bg-white transition-colors group"
                                      >
                                        <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                                        <span className="text-[11px] font-semibold text-gray-900 truncate">
                                          @{r.handle || `conversation ${r.conversation_id}`}
                                        </span>
                                        <span className="text-[10px] text-gray-400 shrink-0 ml-auto">
                                          {r.last_message_at
                                            ? new Date(r.last_message_at + 'Z').toLocaleDateString('en-KE',
                                                { day: 'numeric', month: 'short' })
                                            : ''}
                                        </span>
                                        <span className="text-[10px] text-brand-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                          open →
                                        </span>
                                      </a>
                                    ))}
                                    {c.no_reply_convos > c.no_reply_sample.length && (
                                      <p className="text-[10px] text-gray-400 px-2 pt-0.5">
                                        + {c.no_reply_convos - c.no_reply_sample.length} more
                                      </p>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Speed and escalation. The answered RATE used to sit
                            here too — dropped, because the breakdown above now
                            says the same thing in whole conversations, without
                            a percentage to misread. */}
                        <div className="flex items-center gap-5 text-[11px]">
                          <div>
                            <span className="font-bold text-gray-900 tabular-nums">
                              {c.avg_response_time_ms == null
                                ? '—'
                                : c.avg_response_time_ms < 1000
                                  ? `${c.avg_response_time_ms}ms`
                                  : `${(c.avg_response_time_ms / 1000).toFixed(1)}s`}
                            </span>
                            <span className="text-gray-500"> avg reply</span>
                          </div>
                          <div>
                            <span className={clsx(
                              'font-bold tabular-nums',
                              c.escalated > 0 ? 'text-purple-600' : 'text-gray-900'
                            )}>{c.escalated}</span>
                            <span className="text-gray-500"> escalated</span>
                          </div>
                          <span className={clsx(
                            'ml-auto shrink-0 px-2 py-0.5 rounded-full text-[10px] font-semibold',
                            status.cls
                          )}>
                            {status.label}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}
