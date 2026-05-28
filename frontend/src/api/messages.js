// src/api/messages.js
// Fetch wrapper for the Messages/Inbox endpoints.
// Assumes the JWT from login is stored in localStorage under 'authToken'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5000/api'
const TOKEN_KEY = 'authToken'

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY)
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function handle(res) {
  let body = null
  try {
    body = await res.json()
  } catch {
    /* no body */
  }

  if (!res.ok) {
    const msg = (body && body.error) || `Request failed (${res.status})`
    throw new Error(msg)
  }

  return body
}

export function listConversations({ page = 1, per_page = 20, channel = null, status = null } = {}) {
  const params = new URLSearchParams()
  params.set('page', page)
  params.set('per_page', per_page)
  if (channel) params.set('channel', channel)
  if (status) params.set('status', status)

  return handle(
    fetch(`${API_BASE}/conversations?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

export function getConversation(id) {
  return handle(
    fetch(`${API_BASE}/conversations/${id}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

export function sendReply(id, content, sender = 'human') {
  return handle(
    fetch(`${API_BASE}/conversations/${id}/messages`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ content, sender }),
    })
  )
}

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
 * Toggle AI for a conversation (alias for updateConversationStatus)
 * @param {number} id - Conversation ID
 * @param {boolean} aiEnabled - Whether AI is enabled
 * @returns {Promise<Object>} Updated conversation object
 */
export function toggleAI(id, aiEnabled) {
  // For now, this just updates the status
  // In the future, we might have a dedicated endpoint
  const status = aiEnabled ? 'active' : 'human_override'
  return updateConversationStatus(id, status)
}

/**
 * Mark conversation as read (alias for updateConversationStatus)
 * @param {number} id - Conversation ID
 * @returns {Promise<Object>} Updated conversation object
 */
export function markRead(id) {
  // Mark as read by setting unread_count to 0
  // This is handled automatically by getConversation, but we can add it here for completeness
  return handle(
    fetch(`${API_BASE}/conversations/${id}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}
