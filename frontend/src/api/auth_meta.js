// src/api/auth_meta.js
// Wrappers for the Facebook OAuth flow + connection management.

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
 * Ask the backend for the Facebook OAuth URL.
 * Pass an optional `return_to` URL — where we want to land after the flow finishes.
 */
export function getMetaOAuthUrl(returnTo) {
  const params = new URLSearchParams()
  if (returnTo) params.set('return_to', returnTo)
  return handle(
    fetch(`${API_BASE}/auth/facebook/start?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/** List existing OAuth-connected Pages/IG accounts. */
export function listMetaConnections() {
  return handle(
    fetch(`${API_BASE}/auth/facebook/connections`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}