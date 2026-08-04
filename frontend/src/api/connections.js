// src/api/connections.js
// Instagram Login connections — list, connect, refresh, disconnect.

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

export function listConnections() {
  return handle(fetch(`${API_BASE}/auth/instagram/connections`, { headers: authHeaders() }))
}

// Returns the Instagram authorize URL — the caller navigates to it.
export function startInstagramConnect(returnTo = '/channels') {
  const q = new URLSearchParams({ return_to: returnTo })
  return handle(fetch(`${API_BASE}/auth/instagram/start?${q}`, { headers: authHeaders() }))
}

export function refreshConnection(id) {
  return handle(fetch(`${API_BASE}/auth/instagram/${id}/refresh`, {
    method: 'POST', headers: authHeaders(),
  }))
}

// Asks Instagram whether the token actually works. The only call on this page
// that checks anything rather than reporting what our own row already said.
export function verifyConnection(id) {
  return handle(fetch(`${API_BASE}/auth/instagram/${id}/verify`, {
    method: 'POST', headers: authHeaders(),
  }))
}

export function disconnectConnection(id) {
  return handle(fetch(`${API_BASE}/auth/instagram/${id}/disconnect`, {
    method: 'POST', headers: authHeaders(),
  }))
}
