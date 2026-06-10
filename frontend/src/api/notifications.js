// src/api/notifications.js
// Fetch wrapper for notification endpoints.

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
    if (text) body = JSON.parse(text)
  } catch (err) {
    if (!res.ok) throw new Error(`Request failed (${res.status}): ${err.message}`)
  }
  if (!res.ok) {
    const msg = (body && body.error) || `Request failed (${res.status})`
    throw new Error(msg)
  }
  return body
}

/**
 * List notifications for the current user.
 */
export function fetchNotifications({ unreadOnly = false, limit = 20, days = 7 } = {}) {
  const params = new URLSearchParams()
  if (unreadOnly) params.set('unread_only', 'true')
  params.set('limit', limit)
  params.set('days', days)
  return handle(
    fetch(`${API_BASE}/notifications?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

export function markNotificationRead(id) {
  return handle(
    fetch(`${API_BASE}/notifications/${id}/read`, {
      method: 'PATCH',
      headers: authHeaders(),
    })
  )
}

export function markAllNotificationsRead() {
  return handle(
    fetch(`${API_BASE}/notifications/read-all`, {
      method: 'PATCH',
      headers: authHeaders(),
    })
  )
}