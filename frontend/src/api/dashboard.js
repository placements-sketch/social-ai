// src/api/dashboard.js
// Fetch wrapper for Dashboard endpoints

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
      throw new Error(`Request failed (${res.status}): ${err.message}`)
    }
  }
  if (!res.ok) {
    const msg = (body && body.error) || `Request failed (${res.status})`
    throw new Error(msg)
  }
  return body
}

/**
 * Get analytics summary (KPIs, weekly chart, intent breakdown, channel split, top products)
 * @returns {Promise<{window_days, scope, kpis, weekly, intent_breakdown, channel_split, top_products}>}
 */
export function getAnalyticsSummary() {
  return handle(
    fetch(`${API_BASE}/analytics/summary`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/**
 * Get system logs (alerts)
 * @param {{page?:number, per_page?:number, level?:string, search?:string}} opts
 * @returns {Promise<{logs:Array, total:number, page:number, per_page:number}>}
 */
export function getSystemLogs({ page = 1, per_page = 5, level = null, search = null } = {}) {
  const params = new URLSearchParams()
  params.set('page', page)
  params.set('per_page', per_page)
  if (level) params.set('level', level)
  if (search) params.set('search', search)

  return handle(
    fetch(`${API_BASE}/logs/system?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/**
 * Get my conversation logs (for live activity feed)
 * @param {{page?:number, per_page?:number}} opts
 * @returns {Promise<{logs:Array, total:number, page:number, per_page:number}>}
 */
export function getMyLogs({ page = 1, per_page = 10 } = {}) {
  const params = new URLSearchParams()
  params.set('page', page)
  params.set('per_page', per_page)

  return handle(
    fetch(`${API_BASE}/logs/me?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}
