// src/api/customers.js
// Fetch wrappers for the Customer Profiling endpoints.

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

/** Paginated, filterable, sortable customer list. */
export function listCustomers({
  page = 1,
  per_page = 25,
  search = null,
  segment = null,
  sort_by = 'spent_desc',
} = {}) {
  const params = new URLSearchParams()
  params.set('page', page)
  params.set('per_page', per_page)
  if (search) params.set('search', search)
  if (segment && segment !== 'all') params.set('segment', segment)
  if (sort_by) params.set('sort_by', sort_by)
  return handle(
    fetch(`${API_BASE}/customers?${params.toString()}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/** KPIs + segment counts + top spenders/frequent + AOV by month + top products. */
export function getCustomersOverview() {
  return handle(
    fetch(`${API_BASE}/customers/overview`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/** Single-customer detail. */
export function getCustomer(id) {
  return handle(
    fetch(`${API_BASE}/customers/${id}`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/** Order history for one customer (from local OrderCache). */
export function getCustomerOrders(id) {
  return handle(
    fetch(`${API_BASE}/customers/${id}/orders`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/** Last-sync metadata + current sync job (for status banner). */
export function getCustomersSyncStatus() {
  return handle(
    fetch(`${API_BASE}/customers/sync/status`, {
      method: 'GET',
      headers: authHeaders(),
    })
  )
}

/** Kick off a customer sync — returns 202 + job id. */
export function startCustomersSync() {
  return handle(
    fetch(`${API_BASE}/customers/sync`, {
      method: 'POST',
      headers: authHeaders(),
    })
  )
}