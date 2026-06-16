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

/**
 * Get analytics summary.
 * @param {number} days  time window in days (1 = today, 7 = week, 30 = month)
 */
export function getAnalyticsSummary({ days = 7 } = {}) {
  const params = new URLSearchParams({ days })
  return handle(
    fetch(`${API_BASE}/analytics/summary?${params}`, {
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
 * Get pipeline activity feed (logs table — not audit_logs).
 * Returns natural pipeline events for the Dashboard live feed.
 */
export function getMyLogs({ page = 1, per_page = 12, exclude_pollers = true } = {}) {
  const params = new URLSearchParams()
  params.set('page', page)
  params.set('per_page', per_page)
  if (exclude_pollers) params.set('exclude_pollers', 'true')

  return handle(
    fetch(`${API_BASE}/logs/feed?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}
