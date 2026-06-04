import { useState, useEffect, useCallback } from 'react'
import {
  Instagram, Smartphone, MessageCircle, Bot, User, UserCheck,
  RefreshCw, Edit, Send, ArrowLeft, Info, Loader2,
} from 'lucide-react'
import clsx from 'clsx'
import {
  listConversations, getConversation, sendReply, toggleAI, markRead,
} from '../api/messages'

const FbIcon = () => (
  <span className="inline-flex items-center justify-center w-3 h-3 rounded text-white font-black text-[8px]"
    style={{ background: '#1877F2' }}>f</span>
)

const TikTokIcon = () => (
  <span className="inline-flex items-center justify-center w-3 h-3 rounded text-white font-black text-[8px]"
    style={{ background: '#000000' }}>♪</span>
)

// Conversations carry `platform` (an alias of the DB `channel`) for display.
const platformIcon = (p) => {
  if (p === 'instagram_dm')      return <Instagram size={12} className="text-pink-500" />
  if (p === 'instagram_comment') return <MessageCircle size={12} className="text-pink-500" />
  if (p === 'whatsapp')          return <Smartphone size={12} className="text-green-500" />
  if (p === 'facebook_dm')       return <FbIcon />
  if (p === 'facebook_comment')  return <FbIcon />
  if (p === 'tiktok_dm')         return <TikTokIcon />
  if (p === 'tiktok_comment')    return <TikTokIcon />
}

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

const statusBadge = (s) => {
  const baseClass = "text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
  if (s === 'ai_replied')     return <span className={`${baseClass} bg-brand-100 text-brand-600`}>AI Replied</span>
  if (s === 'active')         return <span className={`${baseClass} bg-brand-100 text-brand-600`}>Active</span>
  if (s === 'human_override') return <span className={`${baseClass} bg-amber-100 text-amber-600`}>Human</span>
  if (s === 'resolved')       return <span className={`${baseClass} bg-gray-100 text-gray-600`}>Resolved</span>
  if (s === 'pending')        return <span className={`${baseClass} bg-red-100 text-red-600`}>Pending</span>
}

const handlerBadge = (conv) => {
  const baseClass = "text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
  // If AI is disabled, it's being handled by a human agent
  if (!conv.ai_enabled) {
    return <span className={`${baseClass} bg-amber-100 text-amber-600`}>Human Agent</span>
  }
  // Otherwise it's being handled by Claude AI
  return <span className={`${baseClass} bg-brand-100 text-brand-600`}>Claude</span>
}

export default function Messages() {
  const [selected, setSelected]         = useState(null)   // null = show list on mobile
  const [showContext, setShowContext]   = useState(false)  // mobile context panel toggle
  const [channelFilter, setChannelFilter] = useState('all') // filters by DB `channel`
  const [attentionFilter, setAttentionFilter] = useState(false) // show only conversations needing attention
  const [search, setSearch]             = useState('')

  const [conversations, setConversations] = useState([])
  const [allChannels, setAllChannels] = useState(['all']) // Track all channels - only set once
  const [activeConv, setActiveConv]       = useState(null) // full conv w/ messages

  const [loadingList, setLoadingList]   = useState(true)
  const [loadingConv, setLoadingConv]   = useState(false)
  const [listError, setListError]       = useState(null)
  const [convError, setConvError]       = useState(null)

  const [replyText, setReplyText]       = useState('')
  const [sending, setSending]           = useState(false)
  const [isInitialLoad, setIsInitialLoad] = useState(true) // flag for auto-select on first load

  // Channels available for the filter row (derived from what we loaded).
  // Keep all channels even when filtering, so filters don't disappear
  const channels = allChannels

  // Debug: log active conversation state
  useEffect(() => {
    if (activeConv) {
      console.log('Active conversation updated:', {
        id: activeConv.id,
        ai_enabled: activeConv.ai_enabled,
        status: activeConv.status,
        handle: activeConv.handle
      })
    }
  }, [activeConv])

  // ── Load the conversation list (re-runs on filter / search change) ────────
  const loadList = useCallback(async () => {
    setLoadingList(true)
    setListError(null)
    try {
      // Canonical contract: send `channel` (not `platform`); response is
      // { conversations, total, page, per_page }.
      const data = await listConversations({
        channel: channelFilter,
        search,
        page: 1,
        per_page: 20,
      })
      setConversations(data.conversations || [])
    } catch (err) {
      setListError(err.message)
    } finally {
      setLoadingList(false)
    }
  }, [channelFilter, search])

  useEffect(() => {
    // Load conversations on initial mount and when filters change
    const t = setTimeout(loadList, search ? 300 : 0)
    return () => clearTimeout(t)
  }, [loadList, search, channelFilter])

  // Load all channels on mount
  useEffect(() => {
    const loadAllChannels = async () => {
      try {
        const data = await listConversations({
          channel: 'all',
          page: 1,
          per_page: 100,
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

  // Auto-select first conversation when conversations load (initial load only)
  useEffect(() => {
    if (conversations.length > 0 && !selected && isInitialLoad) {
      openConversation(conversations[0])
      setIsInitialLoad(false)
    }
  }, [conversations, selected, isInitialLoad])

  // ── Load a single conversation's full thread ──────────────────────────────
  const openConversation = useCallback(async (conv) => {
    setSelected(conv.id)
    setLoadingConv(true)
    setConvError(null)
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
      setConvError(err.message)
    } finally {
      setLoadingConv(false)
    }
  }, [])

  const backToList = () => {
    setSelected(null)
    setActiveConv(null)
  }

  // Filter conversations based on attention flag
  const filteredConversations = attentionFilter
    ? conversations.filter(c => !c.ai_enabled)
    : conversations

  // ── Toggle AI for the active conversation ─────────────────────────────────
  const handleToggleAI = async () => {
    if (!activeConv) return
    const next = !activeConv.ai_enabled
    setActiveConv(c => ({ ...c, ai_enabled: next }))   // optimistic
    try {
      const data = await toggleAI(activeConv.id, next) // { conversation: {...} }
      setActiveConv(c => ({ ...c, ...data.conversation }))
    } catch {
      setActiveConv(c => ({ ...c, ai_enabled: !next })) // revert
    }
  }

  // ── Send a manual reply ───────────────────────────────────────────────────
  const handleSend = async () => {
    const content = replyText.trim()
    if (!content || !activeConv || sending) return
    setSending(true)
    try {
      // Canonical: sendReply(id, content, sender='human')
      // -> { message, conversation }
      const data = await sendReply(activeConv.id, content, 'human')
      setActiveConv(c => ({
        ...c,
        ...data.conversation,
        messages: [...(c.messages || []), data.message],
      }))
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
    } catch (err) {
      setConvError(err.message)
    } finally {
      setSending(false)
    }
  }

  // ── Conversation list panel ──────────────────────────────────────────────
  const ConvList = (
    <div className={clsx(
      'border-r border-gray-100 flex flex-col bg-[#fafafa]',
      'w-full sm:w-72 md:w-64 md:shrink-0',
      selected ? 'hidden md:flex' : 'flex',
    )}>
      <div className="p-2 sm:p-3 border-b border-gray-100 space-y-2 sm:space-y-3">
        <input
          className="input w-full text-xs"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex gap-1 overflow-x-auto pb-1 -mx-2 px-2 sm:mx-0 sm:px-0 sm:flex-wrap sm:pb-0">
          {channels.map(p => (
            <button
              key={p}
              onClick={() => setChannelFilter(p)}
              className={clsx(
                'text-xs px-2 py-1 rounded-md font-medium transition-colors whitespace-nowrap shrink-0 sm:shrink',
                channelFilter === p
                  ? 'bg-gray-900 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              )}
            >
              {p === 'all' ? 'All' : platformLabel(p)}
            </button>
          ))}
        </div>
        <div className="w-full flex items-center justify-between px-2 sm:px-0 py-1.5">
          <span className="text-xs font-medium text-gray-600 truncate">⚠️ Needs Attention</span>
          <button
            onClick={() => setAttentionFilter(!attentionFilter)}
            className={clsx(
              'relative inline-flex w-8 h-5 rounded-full transition-colors duration-200 shrink-0 ml-2'
            )}
            style={{
              backgroundColor: attentionFilter ? '#1f2937' : '#d1d5db'
            }}
          >
            <span
              className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200"
              style={{ transform: attentionFilter ? 'translateX(12px)' : 'translateX(0px)' }}
            />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loadingList && (
          <div className="flex items-center justify-center py-10 text-gray-400">
            <Loader2 size={16} className="animate-spin mr-2" /> <span className="text-xs">Loading…</span>
          </div>
        )}
        {listError && !loadingList && (
          <div className="px-3 py-6 text-center">
            <p className="text-xs text-red-500 mb-2">{listError}</p>
            <button onClick={loadList} className="text-xs text-gray-900 font-medium">Retry</button>
          </div>
        )}
        {!loadingList && !listError && filteredConversations.length === 0 && (
          <p className="px-3 py-10 text-center text-xs text-gray-400">
            {attentionFilter ? 'No conversations needing attention.' : 'No conversations yet.'}
          </p>
        )}
        {!loadingList && !listError && filteredConversations.map((conv) => (
          <button
            key={conv.id}
            onClick={() => openConversation(conv)}
            className={clsx(
              'w-full text-left px-2 sm:px-3 py-2 sm:py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors relative',
              activeConv?.id === conv.id && 'bg-gray-100 border-l-2 border-l-gray-900'
            )}
          >
            {!conv.ai_enabled && (
              <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-amber-500" title="Needs attention" />
            )}
            <div className="flex items-center justify-between mb-1 gap-1">
              <div className="flex items-center gap-1.5 min-w-0">
                {platformIcon(conv.platform)}
                <span className="text-xs font-semibold text-gray-800 truncate">
                  {conv.handle}
                </span>
              </div>
              <span className="text-xs text-gray-400 shrink-0 ml-auto">{conv.time}</span>
            </div>
            <p className="text-xs text-gray-500 truncate">{conv.lastMessage}</p>
            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
              {statusBadge(conv.status)}
              {handlerBadge(conv)}
              {conv.unread_count > 0 && <span className="text-[10px] font-semibold text-brand-600 bg-brand-100 px-1.5 py-0.5 rounded-md">{conv.unread_count}</span>}
            </div>
          </button>
        ))}
      </div>
    </div>
  )

  // ── Chat thread panel ────────────────────────────────────────────────────
  const ChatPanel = (
    <div className={clsx(
      'flex-1 flex flex-col min-w-0 bg-[#f0f0f0]',
      !selected ? 'hidden md:flex' : 'flex',
    )}>
      {!selected && (
        <div className="hidden md:flex flex-1 items-center justify-center text-gray-400 text-sm">
          Select a conversation to get started.
        </div>
      )}

      {selected && loadingConv && (
        <div className="flex-1 flex items-center justify-center text-gray-400">
          <Loader2 size={18} className="animate-spin mr-2" /> Loading conversation…
        </div>
      )}

      {selected && !loadingConv && convError && (
        <div className="flex-1 flex flex-col items-center justify-center gap-2">
          <p className="text-xs text-red-500">{convError}</p>
          <button onClick={() => openConversation(selected)} className="text-xs text-brand-600 font-medium">Retry</button>
        </div>
      )}

      {selected && !loadingConv && activeConv && (
        <>
          {/* Chat header */}
          <div className="flex items-center justify-between px-2 sm:px-3 md:px-4 py-2 sm:py-3 border-b border-gray-100 bg-white gap-1 sm:gap-2 min-h-[56px] sm:min-h-auto">
            <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
              <button
                onClick={backToList}
                className="md:hidden btn-ghost p-1.5 shrink-0"
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

            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={handleToggleAI}
                className={clsx(
                  'text-xs font-semibold px-2 sm:px-3 py-1.5 rounded-lg border transition-colors whitespace-nowrap',
                  activeConv.ai_enabled
                    ? 'border-gray-200 text-gray-500 hover:text-gray-800 hover:border-gray-300'
                    : 'border-amber-300 bg-amber-50 text-amber-600'
                )}
              >
                <span className="sm:hidden">{activeConv.ai_enabled ? '⚙️' : '⚠️'}</span>
                <span className="hidden sm:inline">{activeConv.ai_enabled ? 'Disable AI' : '⚠ AI Off'}</span>
              </button>
              <button
                onClick={() => setShowContext(s => !s)}
                className="md:hidden btn-ghost p-1.5"
                aria-label="Show AI context"
              >
                <Info size={15} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-2 sm:p-3 md:p-4 space-y-3 sm:space-y-4">
            {(activeConv.messages || []).map((msg) => (
              <div key={msg.id} className={clsx('flex', msg.from === 'user' ? 'justify-start' : 'justify-end')}>
                <div className={clsx(
                  'max-w-[90%] sm:max-w-[75%] md:max-w-[70%] flex flex-col gap-1',
                  msg.from === 'user' ? 'items-start' : 'items-end'
                )}>
                  <div className="flex items-center gap-1 px-1 text-xs">
                    {msg.from === 'user'  && <User size={11} className="text-gray-400" />}
                    {msg.from === 'ai'    && <Bot size={11} className="text-brand-500" />}
                    {msg.from === 'human' && <UserCheck size={11} className="text-amber-500" />}
                    <span className="text-gray-400 font-medium truncate">
                      {msg.from === 'user' ? 'Customer' : msg.from === 'ai' ? 'AI' : 'Agent'}
                      {' · '}{msg.time}
                    </span>
                  </div>
                  <div className={clsx(
                    'px-3 sm:px-3.5 py-2 sm:py-2.5 rounded-2xl text-xs sm:text-sm leading-relaxed shadow-sm',
                    msg.from === 'user'  && 'bg-white text-gray-800 rounded-tl-sm border border-gray-100',
                    msg.from === 'ai'    && 'bg-brand-500 text-white rounded-tr-sm',
                    msg.from === 'human' && 'bg-amber-500 text-white rounded-tr-sm',
                  )}>
                    {msg.text}
                  </div>
                  {msg.from === 'ai' && (
                    <div className="flex gap-2 px-1 text-xs">
                      <button className="text-gray-400 hover:text-gray-600 flex items-center gap-1 font-medium">
                        <RefreshCw size={10} /> <span className="hidden sm:inline">Resend</span>
                      </button>
                      <button className="text-gray-400 hover:text-gray-600 flex items-center gap-1 font-medium">
                        <Edit size={10} /> <span className="hidden sm:inline">Edit</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {(activeConv.messages || []).length === 0 && (
              <p className="text-center text-xs text-gray-400 py-8">No messages in this conversation.</p>
            )}
          </div>

          {/* Manual reply bar — shown when AI is disabled for this conversation */}
          {activeConv && !activeConv.ai_enabled && (
            <div className="px-2 sm:px-3 md:px-4 py-2 sm:py-3 border-t border-gray-100 bg-white flex gap-1.5 sm:gap-2">
              <input
                className="input flex-1 text-xs sm:text-sm"
                placeholder="Reply…"
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
                disabled={sending}
              />
              <button
                onClick={handleSend}
                disabled={sending || !replyText.trim()}
                className="btn-primary flex items-center gap-1 px-2 sm:px-4 py-2 disabled:opacity-50 whitespace-nowrap text-xs sm:text-sm"
              >
                {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                <span className="hidden sm:inline">Send</span>
              </button>
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
      'hidden md:block md:w-56 md:shrink-0',
    )}>
      {activeConv && <ContextContent conv={activeConv} />}
    </div>
  )

  const MobileContextDrawer = showContext && activeConv && (
    <div className="md:hidden fixed inset-0 z-40 flex">
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
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Messages</h1>
        <p className="text-sm text-gray-500 mt-0.5">Manage customer conversations across all channels</p>
      </div>
      {MobileContextDrawer}
      <div className="flex h-[calc(100vh-8rem)] gap-0 card overflow-hidden border border-gray-100">
        {ConvList}
        {ChatPanel}
        {ContextPanel}
      </div>
    </>
  )
}

// Extracted so it can be used in both desktop panel and mobile drawer
function ContextContent({ conv }) {
  const lastMeta = (conv.messages || []).filter(m => m.meta).slice(-1)[0]

  return (
    <div className="space-y-4">
      {lastMeta && (
        <>
          <div>
            <p className="text-xs text-gray-400 font-medium mb-1">Intent</p>
            <span className="badge bg-brand-50 text-brand-600 border border-brand-100">
              {lastMeta.meta.intent || '—'}
            </span>
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium mb-1">Product</p>
            <p className="text-xs text-gray-800 font-semibold">{lastMeta.meta.product || '—'}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium mb-1">Stock</p>
            <p className="text-xs text-gray-800 font-semibold">{lastMeta.meta.stock ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 font-medium mb-1">Response Time</p>
            <p className="text-xs text-green-600 font-bold">{lastMeta.meta.responseTime || '—'}</p>
          </div>
        </>
      )}
      <div className="pt-3 border-t border-gray-100">
        <p className="section-title mb-2">Channel</p>
        <p className="text-xs text-gray-700 font-medium">{(conv.platform || '').replace('_', ' ')}</p>
      </div>
      <div className="pt-3 border-t border-gray-100">
        <p className="section-title mb-2">Status</p>
        {statusBadge(conv.status)}
      </div>
    </div>
  )
}
