import { useState, useEffect, useCallback, useContext } from 'react'
import {
  Instagram, Smartphone, MessageCircle, Bot, User, UserCheck,
  RefreshCw, Edit, Send, ArrowLeft, Info, Loader2, Users, X,
} from 'lucide-react'
import clsx from 'clsx'
import {
  listConversations, getConversation, sendReply, toggleAI, markRead,
  assignConversation, unassignConversation, listAgents,
} from '../api/messages'
import { SkeletonCard } from '../components/Skeleton'
import { ConfirmationContext } from '../context/ConfirmationContext'
import { useAuth } from '../context/AuthContext'

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
  const { user } = useAuth()
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

  // Assignment UI
  const [agents, setAgents]             = useState([]) // list of active agents
  const [showAssignDropdown, setShowAssignDropdown] = useState(false)
  const [assigningConvId, setAssigningConvId] = useState(null)

  const { confirm } = useContext(ConfirmationContext)

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

  // Auto-select first conversation on desktop only (initial load only)
  useEffect(() => {
    const isDesktop = window.innerWidth >= 768 // md breakpoint
    if (conversations.length > 0 && !selected && isInitialLoad && isDesktop) {
      openConversation(conversations[0])
      setIsInitialLoad(false)
    } else if (isInitialLoad && !isDesktop) {
      // On mobile, just mark initial load as complete without auto-selecting
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

  // ── Assign conversation to agent ───────────────────────────────────────────
  const handleAssign = async (agentId) => {
    if (!activeConv) return
    setAssigningConvId(activeConv.id)
    try {
      const data = await assignConversation(activeConv.id, agentId)
      setActiveConv(data.conversation)
      setConversations(prev => prev.map(c =>
        c.id === activeConv.id ? { ...c, ...data.conversation } : c
      ))
      setShowAssignDropdown(false)
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
      title: 'Remove Assignment?',
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

  // ── Conversation list panel ──────────────────────────────────────────────
  const ConvList = (
    <div className={clsx(
      'border-r border-gray-100 flex flex-col bg-white',
      'w-full sm:w-80 md:w-72 md:shrink-0',
      selected ? 'hidden md:flex' : 'flex',
    )}>
      <div className="p-3 sm:p-4 border-b border-gray-100 space-y-3 sm:space-y-4">
        <input
          className="input w-full text-xs rounded-lg border border-gray-200 bg-gray-50 focus:bg-white"
          placeholder="Search conversations…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex gap-1 overflow-x-auto pb-2 -mx-3 px-3 sm:-mx-4 sm:px-4 sm:flex-wrap sm:pb-0">
          {channels.map(p => (
            <button
              key={p}
              onClick={() => setChannelFilter(p)}
              className={clsx(
                'text-xs px-2.5 py-1.5 rounded-lg font-medium transition-all whitespace-nowrap shrink-0 sm:shrink border',
                channelFilter === p
                  ? 'bg-black text-white border-black'
                  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
              )}
            >
              {p === 'all' ? 'All' : platformLabel(p)}
            </button>
          ))}
        </div>
        <div className="bg-gradient-to-r from-amber-50 to-orange-50 rounded-lg p-2 border border-amber-100">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-base shrink-0">⚠️</span>
              <span className="text-xs font-semibold text-amber-900">Needs Attention</span>
            </div>
            <button
              onClick={() => setAttentionFilter(!attentionFilter)}
              className={clsx(
                'relative inline-flex w-8 h-4 rounded-full transition-all duration-300 shrink-0'
              )}
              style={{
                backgroundColor: attentionFilter ? '#000000' : '#e5e7eb'
              }}
            >
              <span
                className="absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white shadow-sm transition-all duration-300"
                style={{ transform: attentionFilter ? 'translateX(12px)' : 'translateX(0px)' }}
              />
            </button>
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto pb-4">
        {loadingList && (
          <div className="p-3 sm:p-4 space-y-3">
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
        {!loadingList && !listError && filteredConversations.length === 0 && (
          <p className="px-4 py-12 text-center text-xs text-gray-400">
            {attentionFilter ? 'No conversations needing attention.' : 'No conversations yet.'}
          </p>
        )}
        {!loadingList && !listError && filteredConversations.map((conv) => (
          <button
            key={conv.id}
            onClick={() => openConversation(conv)}
            className={clsx(
              'w-full text-left px-3 sm:px-4 py-2.5 sm:py-3 border-b border-gray-100 hover:bg-gray-50 transition-all relative group',
              activeConv?.id === conv.id && 'bg-blue-50 border-l-3 border-l-black'
            )}
          >
            {!conv.ai_enabled && (
              <div className="absolute top-3 right-3 w-2.5 h-2.5 rounded-full bg-amber-500" style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }} title="Needs attention" />
            )}
            <div className="flex items-start justify-between gap-2 mb-1.5">
              <div className="flex items-center gap-2 min-w-0">
                <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-gray-100 group-hover:bg-gray-200 transition-colors shrink-0">
                  {platformIcon(conv.platform)}
                </div>
                <span className="text-xs font-semibold text-gray-900 truncate">
                  {conv.handle}
                </span>
              </div>
              <span className="text-xs text-gray-400 shrink-0 whitespace-nowrap">{conv.time}</span>
            </div>
            <p className="text-xs text-gray-600 truncate mb-2 line-clamp-1">{conv.lastMessage}</p>
            <div className="flex items-center gap-1.5 flex-wrap">
              {statusBadge(conv.status)}
              {handlerBadge(conv)}
              {conv.unread_count > 0 && (
                <span className="text-[10px] font-bold text-white bg-red-500 px-2 py-0.5 rounded-full">
                  {conv.unread_count}
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  )

  // ── Chat thread panel ────────────────────────────────────────────────────
  const ChatPanel = (
    <div className={clsx(
      'flex-1 flex flex-col min-w-0 bg-[#FAFAFA]',
      !selected ? 'hidden md:flex' : 'flex',
    )}>
      {!selected && (
        <div className="hidden md:flex flex-1 items-center justify-center text-gray-400 text-sm">
          Select a conversation to get started.
        </div>
      )}

      {selected && loadingConv && (
        <div className="flex-1 flex flex-col p-3 sm:p-4 space-y-3">
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
            {/* Left: Back button + Chat info */}
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

            {/* Center/Left: AI toggle + Assign button + AI status indicator */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {/* AI Toggle button */}
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

              {/* AI Off indicator badge — only show when AI is disabled */}
              {!activeConv.ai_enabled && (
                <div className="flex items-center gap-1 px-2 py-1.5 rounded-lg bg-amber-50 border border-amber-200 shrink-0">
                  <span className="text-amber-600 text-xs font-semibold">AI Disabled</span>
                </div>
              )}

              
              {/* Assignment button — supervisor/admin only */}
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
                      <span className="bg-green-100 text-green-700 px-1.5 py-0.5 rounded text-[10px] font-bold">
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
                      <div className="absolute left-0 top-full mt-1 w-56 bg-white rounded-lg shadow-lg border border-gray-200 z-40">
                        <div className="p-2 space-y-1 max-h-64 overflow-y-auto">
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
                              <div className="text-[11px] text-gray-400">{agent.email}</div>
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
              className="md:hidden btn-ghost p-1.5"
              aria-label="Show AI context"
            >
              <Info size={15} />
            </button>
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
    <div className="flex flex-col h-[calc(100vh-4rem)] -mx-4 md:-mx-8 -my-4 md:-my-8 bg-white">
      {/* Header - Fixed */}
      <div className="px-4 md:px-8 py-4 border-b border-gray-100 bg-white shrink-0">
        <h1 className="text-2xl font-bold text-gray-900">Messages</h1>
        <p className="text-sm text-gray-500 mt-0.5">Manage customer conversations across all channels</p>
      </div>

      {/* Main content area - flex-1 to fill remaining space, no overflow */}
      <div className="flex-1 flex gap-0 overflow-hidden">
        {ConvList}
        {ChatPanel}
        {ContextPanel}
      </div>

      {MobileContextDrawer}
    </div>
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
