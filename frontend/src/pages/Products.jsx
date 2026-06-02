import { useState, useEffect } from 'react'
import { RefreshCw, Package, Loader2, AlertCircle, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import clsx from 'clsx'

export default function Products() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null)
  const [syncDiff, setSyncDiff] = useState(null)

  // Pagination
  const [page, setPage] = useState(1)
  const [perPage] = useState(20)
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')

  // Sync UI
  const [showSyncDiff, setShowSyncDiff] = useState(false)

  useEffect(() => {
    fetchProducts()
    fetchStatus()
  }, [page, search])

  const fetchProducts = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('page', page)
      params.set('per_page', perPage)
      if (search) params.set('search', search)

      const res = await fetch(`/api/products?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load products')
      const data = await res.json()
      setProducts(data.products || [])
      setTotal(data.total || 0)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/products/sync/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load sync status')
      const data = await res.json()
      setStatus(data)
    } catch (err) {
      console.error('Failed to fetch sync status:', err)
    }
  }

  const handleCheckSync = async () => {
    setChecking(true)
    try {
      const res = await fetch('/api/products/sync/check', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.message || 'Failed to check sync')
      }
      const data = await res.json()
      setSyncDiff(data)
      setShowSyncDiff(true)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(false)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await fetch('/api/products/sync', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.message || 'Failed to sync products')
      }
      const data = await res.json()
      setShowSyncDiff(false)
      setSyncDiff(null)
      await fetchProducts()
      await fetchStatus()
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setSyncing(false)
    }
  }

  const lastSynced = status?.last_synced_at ? new Date(status.last_synced_at) : null
  const isStale = status?.stale || false
  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="space-y-6 w-full max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Products & Inventory</h1>
          <p className="text-xs text-gray-500 mt-0.5">Shopify is the single source of truth for all product data</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleCheckSync}
            disabled={checking || syncing}
            className="btn-ghost flex items-center gap-2 text-sm"
          >
            {checking && <Loader2 size={14} className="animate-spin" />}
            Check for Changes
          </button>
          <button
            onClick={handleSync}
            disabled={syncing || checking}
            className="btn-primary flex items-center gap-2 text-xs"
          >
            {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Sync Now
          </button>
        </div>
      </div>

      {/* Alert messages */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex gap-3">
          <AlertCircle size={18} className="text-red-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-900">{error}</p>
          </div>
        </div>
      )}

      {/* Stale warning */}
      {isStale && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between">
          <div className="flex gap-3">
            <AlertCircle size={18} className="text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-amber-900">Catalog is stale</p>
              <p className="text-xs text-amber-700 mt-0.5">Last synced {lastSynced ? formatTime(lastSynced) : 'never'}. Click "Sync Now" to refresh.</p>
            </div>
          </div>
        </div>
      )}

      {/* Sync diff modal */}
      {showSyncDiff && syncDiff && (
        <div className="card p-6 border-2 border-blue-200 bg-blue-50 space-y-4">
          <div>
            <h3 className="text-base font-bold text-gray-900">Sync Preview</h3>
            <p className="text-sm text-gray-600 mt-1">Review the changes that will be applied</p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Will be added', count: syncDiff.added?.length || 0, color: 'green' },
              { label: 'Will be updated', count: syncDiff.updated?.length || 0, color: 'blue' },
              { label: 'Will be removed', count: syncDiff.removed?.length || 0, color: 'red' },
            ].map(({ label, count, color }) => (
              <div key={label} className={`p-3 rounded-lg ${color === 'green' ? 'bg-green-100' : color === 'blue' ? 'bg-blue-100' : 'bg-red-100'}`}>
                <p className={`text-xs font-medium ${color === 'green' ? 'text-green-700' : color === 'blue' ? 'text-blue-700' : 'text-red-700'}`}>{label}</p>
                <p className="text-2xl font-bold mt-1" style={{ color: color === 'green' ? '#059669' : color === 'blue' ? '#2563eb' : '#dc2626' }}>{count}</p>
              </div>
            ))}
          </div>
          {!syncDiff.in_sync && (
            <div className="flex gap-3">
              <button onClick={() => setShowSyncDiff(false)} className="btn-ghost flex-1">Cancel</button>
              <button onClick={handleSync} disabled={syncing} className="btn-primary flex-1 flex items-center justify-center gap-2">
                {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                Apply Sync
              </button>
            </div>
          )}
          {syncDiff.in_sync && (
            <p className="text-sm text-green-700 font-medium">✓ Catalog is already in sync with Shopify</p>
          )}
        </div>
      )}

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Total Products</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{status?.product_count || 0}</p>
          <p className="text-xs text-gray-500 mt-2">
            {lastSynced ? `Last synced ${formatTime(lastSynced)}` : 'Never synced'}
          </p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">In Stock</p>
          <p className="text-3xl font-bold text-green-600 mt-1">{products.filter(p => p.stock_quantity > 0).length}</p>
        </div>
        <div className="card p-4">
          <p className="text-xs text-gray-600 font-medium uppercase tracking-wide">Out of Stock</p>
          <p className="text-3xl font-bold text-red-600 mt-1">{products.filter(p => p.stock_quantity === 0).length}</p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-3 text-gray-400" />
        <input
          type="text"
          placeholder="Search products..."
          value={search}
          onChange={e => {
            setSearch(e.target.value)
            setPage(1)
          }}
          className="input w-full pl-10"
        />
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-brand-500" />
          </div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Package size={32} className="text-gray-300 mb-3" />
            <p className="text-gray-500 font-medium">No products found</p>
            <p className="text-sm text-gray-400 mt-1">Try syncing from Shopify to populate the catalog</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-4 py-3 text-xs font-bold text-gray-700 uppercase tracking-wider">Product</th>
                  <th className="text-left px-4 py-3 text-xs font-bold text-gray-700 uppercase tracking-wider">Price</th>
                  <th className="text-left px-4 py-3 text-xs font-bold text-gray-700 uppercase tracking-wider">Variants</th>
                  <th className="text-center px-4 py-3 text-xs font-bold text-gray-700 uppercase tracking-wider">Stock</th>
                  <th className="text-center px-4 py-3 text-xs font-bold text-gray-700 uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-brand-100 to-brand-50 flex items-center justify-center shrink-0">
                          <Package size={16} className="text-brand-600" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900 truncate">{p.name}</p>
                          <p className="text-xs text-gray-500 truncate">{p.shopify_product_id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-sm font-semibold text-gray-900">{p.price || '—'}</td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-1">
                        {(p.variants || []).slice(0, 2).map((v, i) => (
                          <span key={i} className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded">{v}</span>
                        ))}
                        {(p.variants || []).length > 2 && (
                          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">+{(p.variants || []).length - 2}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-4 text-center">
                      <span className={clsx('text-xs font-bold', p.stock_quantity === 0 ? 'text-red-600' : 'text-green-600')}>
                        {p.stock_quantity}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-center">
                      {p.stock_quantity === 0 ? (
                        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-200">Out of Stock</span>
                      ) : (
                        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-green-50 text-green-700 border border-green-200">In Stock</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-600">
            Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of {total} products
          </p>
          <div className="flex gap-1 items-center">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-50"
            >
              <ChevronLeft size={14} />
            </button>

            {/* Smart pagination with ellipses */}
            {(() => {
              const pages = []
              const delta = 1 // pages to show around current
              const left = Math.max(2, page - delta)
              const right = Math.min(totalPages - 1, page + delta)

              // Always show first page
              pages.push(1)

              // Add left ellipsis if needed
              if (left > 2) pages.push('...')

              // Add pages around current
              for (let i = left; i <= right; i++) {
                pages.push(i)
              }

              // Add right ellipsis if needed
              if (right < totalPages - 1) pages.push('...')

              // Always show last page if more than 1
              if (totalPages > 1) pages.push(totalPages)

              return pages.map((p, i) =>
                p === '...' ? (
                  <span key={`ellipsis-${i}`} className="px-2 text-xs text-gray-400">…</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p)}
                    className={clsx(
                      'w-8 h-8 rounded-lg text-xs font-medium transition-colors',
                      page === p
                        ? 'bg-gray-900 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    )}
                  >
                    {p}
                  </button>
                )
              )
            })()}

            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-50"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function formatTime(date) {
  const now = new Date()
  const diff = now - date
  const mins = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}
