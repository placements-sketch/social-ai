// src/api/messages.js
// Fetch wrapper for the Messages/Inbox endpoints.
// Contract: see ARCHITECTURE.md §4.2 (canonical).
// Assumes the JWT from login is stored in localStorage under 'authToken'.

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const TOKEN_KEY = 'authToken'

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY)
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function handle(fetchPromise) {
  const res = await fetchPromise
  let body = null
  try {
    const text = await res.text()
    if (text) {
      body = JSON.parse(text)
    }
  } catch (err) {
    if (!res.ok) {
      const error = new Error(`Request failed (${res.status}): ${err.message}`)
      error.status = res.status
      throw error
    }
  }
  if (!res.ok) {
    const msg = (body && body.error) || `Request failed (${res.status})`
    const error = new Error(msg)
    error.status = res.status
    throw error
  }
  return body
}

/**
 * List conversations for the inbox.
 * @param {{page?:number, per_page?:number, channel?:string, status?:string, search?:string}} opts
 * @returns {Promise<{conversations:Array, total:number, page:number, per_page:number}>}
 */
export function listConversations({ page = 1, per_page = 20, channel = null, status = null, search = null } = {}) {
  const params = new URLSearchParams()
  params.set('page', page)
  params.set('per_page', per_page)
  if (channel && channel !== 'all') params.set('channel', channel)
  if (status && status !== 'all') params.set('status', status)
  if (search) params.set('search', search)

  return handle(
    fetch(`${API_BASE}/conversations?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/**
 * Get one conversation with its full message thread.
 * @returns {Promise<{conversation:Object}>}  (wrapped)
 */
export function getConversation(id) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/**
 * Send a manual reply. Canonical endpoint: POST /conversations/<id>/messages.
 * @param {number} id
 * @param {string} content
 * @param {'human'|'ai'|'system'} [sender='human']
 * @returns {Promise<{message:Object, conversation:Object}>}
 */
export function sendReply(id, content, sender = 'human') {
  return handle(
    fetch(`${API_BASE}/conversations/${id}/messages`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ content, sender }),
    })
  )
}

/**
 * Toggle AI auto-reply for a conversation. Dedicated endpoint: PATCH /conversations/<id>/ai.
 * @returns {Promise<{conversation:Object}>}
 */
export function toggleAI(id, aiEnabled) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}/ai`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ ai_enabled: aiEnabled }),
    })
  )
}

/**
 * Update conversation status. PATCH /conversations/<id>.
 * @param {number} id
 * @param {'active'|'resolved'|'human_override'|'pending'} status
 * @returns {Promise<{conversation:Object}>}
 */
export function updateConversationStatus(id, status) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ status }),
    })
  )
}

/**
 * Mark a conversation as read. Dedicated endpoint: PATCH /conversations/<id>/read.
 * @returns {Promise<{conversation:Object}>}
 */
export function markRead(id) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}/read`, {
      method: 'PATCH',
      headers: authHeaders(),
    })
  )
}

/**
 * Assign a conversation to an agent.
 * @param {number} id - Conversation ID
 * @param {number} agentId - Agent ID to assign to (or self-claim)
 * @returns {Promise<{conversation:Object}>}
 */
export function assignConversation(id, agentId) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}/assign`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ agent_id: agentId }),
    })
  )
}

/**
 * Unassign a conversation (remove current assignment). Supervisor+admin only.
 * @param {number} id - Conversation ID
 * @returns {Promise<{conversation:Object}>}
 */
export function unassignConversation(id) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}/unassign`, {
      method: 'POST',
      headers: authHeaders(),
    })
  )
}

/**
 * List active agents for assignment dropdown. Supervisor+admin only.
 * @returns {Promise<{agents:Array}>}
 */
export function listAgents() {
  return handle(
    fetch(`${API_BASE}/auth/agents`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}