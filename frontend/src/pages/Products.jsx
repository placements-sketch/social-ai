import { useState, useEffect } from 'react'
import { RefreshCw, Package, Loader2, AlertCircle, ChevronLeft, ChevronRight, Search, X, Tag } from 'lucide-react'
import clsx from 'clsx'
import { SkeletonHeader, SkeletonList } from '../components/Skeleton'
import { ModalPortal } from '../context/ModalPortal'
import { useCountAnimation } from '../hooks/useCountAnimation'
import { formatTimeAgo } from '../utils/time'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'


/**
 * One product, in full.
 *
 * The list can only show a name, a price and a total — enough to scan, not
 * enough to answer a customer. This is the detail an agent is actually asked
 * for mid-conversation: which size is gone, what the description says, what it
 * is tagged as, and how stale our copy of it is.
 *
 * Everything here comes from the row already loaded for the list, so opening a
 * product costs no request.
 */
/**
 * Shopify descriptions are HTML — 7045 of 7713 in this catalogue contain tags.
 * Rendered as text you get `<span style="font-size: 10pt;">2 PACK BOXERS</span>`
 * on screen; rendered as HTML you inherit whatever markup and inline styling
 * the store's editor produced, inside our layout. Stripped to plain text
 * instead, with entities decoded, so it reads as a sentence either way.
 */
function plainText(html) {
  if (!html) return ''
  return html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|h[1-6])>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}


function ProductDetailModal({ product, onClose }) {
  if (!product) return null

  const stock = product.stock_quantity
  const untracked = stock == null
  const variants = product.variants_detail || []
  const images = product.images || []
  const [activeImg, setActiveImg] = useState(0)

  const stockTone = untracked
    ? 'bg-gray-100 text-gray-500'
    : stock === 0
      ? 'bg-red-50 text-red-600'
      : stock <= 5
        ? 'bg-amber-50 text-amber-700'
        : 'bg-green-50 text-green-600'

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="fixed inset-0 bg-black/40 fade-in" onClick={onClose} />
        <div className="relative glass glass-modal pop-in rounded-2xl shadow-2xl w-full max-w-2xl max-h-[88vh] overflow-y-auto custom-scrollbar">
          <div className="flex items-start justify-between gap-3 p-5 pb-0">
            <div className="min-w-0">
              <h2 className="text-base font-bold text-gray-900 leading-snug">{product.name}</h2>
              <p className="text-xs text-gray-400 mt-1">
                {product.handle ? `/${product.handle}` : `Shopify id ${product.shopify_product_id}`}
              </p>
            </div>
            <button onClick={onClose}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors shrink-0"
                    aria-label="Close">
              <X size={16} />
            </button>
          </div>

          <div className="p-5 grid grid-cols-1 sm:grid-cols-[minmax(0,220px)_1fr] gap-5">
            <div>
              <div className="aspect-square rounded-xl bg-gradient-to-br from-brand-100 to-brand-50 overflow-hidden flex items-center justify-center">
                {images[activeImg]
                  ? <img src={images[activeImg]} alt="" className="w-full h-full object-cover" />
                  : <Package size={34} className="text-brand-600" />}
              </div>
              {images.length > 1 && (
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {images.slice(0, 6).map((src, i) => (
                    <button key={i} onClick={() => setActiveImg(i)}
                            className={clsx('w-11 h-11 rounded-lg overflow-hidden border-2 transition-colors',
                              i === activeImg ? 'border-brand-500' : 'border-transparent opacity-60 hover:opacity-100')}>
                      <img src={src} alt="" className="w-full h-full object-cover" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="min-w-0 space-y-4">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-lg font-bold text-gray-900">{product.price || '—'}</span>
                <span className={clsx('text-[11px] font-semibold px-2 py-0.5 rounded-md', stockTone)}>
                  {untracked ? 'Not tracked' : stock === 0 ? 'Out of stock' : `${stock} in stock`}
                </span>
              </div>

              {/* Per-variant stock. The total says whether you can sell it; this
                  says which size to stop promising. */}
              {variants.length > 0 && (
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400 mb-1.5">
                    Stock by variant
                  </p>
                  <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 overflow-hidden">
                    {variants.map((v, i) => {
                      const q = v.stock_quantity ?? v.inventory_quantity
                      // Respected per variant: a variant Shopify isn't tracking
                      // has no meaningful number, and showing 0 would read as
                      // "sold out" when it means "we don't count this one".
                      const tracked = v.inventory_tracked !== false
                      const out = tracked && q === 0
                      return (
                        <div key={i} className="flex items-center justify-between gap-3 px-3 py-2">
                          <div className="min-w-0">
                            <p className="text-xs text-gray-700 truncate">{v.title || v.name || `Variant ${i + 1}`}</p>
                            {v.sku && (
                              <p className="text-[10px] text-gray-400 font-mono truncate">{v.sku}</p>
                            )}
                          </div>
                          <span className={clsx('text-xs font-semibold tabular-nums shrink-0',
                            out ? 'text-red-600'
                              : !tracked || q == null ? 'text-gray-400'
                                : q <= 5 ? 'text-amber-600' : 'text-gray-600')}>
                            {!tracked || q == null ? 'untracked' : out ? 'sold out' : q}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {plainText(product.description) && (
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400 mb-1">Description</p>
                  <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-line">
                    {plainText(product.description).length > 700
                      ? `${plainText(product.description).slice(0, 700)}…`
                      : plainText(product.description)}
                  </p>
                </div>
              )}

              {(product.tags || []).length > 0 && (
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-gray-400 mb-1.5">Tags</p>
                  <div className="flex flex-wrap gap-1.5">
                    {product.tags.map((t, i) => (
                      <span key={i} className="inline-flex items-center gap-1 text-[11px] text-gray-600 bg-gray-100 rounded-md px-2 py-0.5">
                        <Tag size={10} className="text-gray-400" />{t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Stated, not hidden: this is a cached copy, and how old it is
                  decides whether you trust the stock number above. */}
              {product.cached_at && (
                <p className="text-[11px] text-gray-400 pt-1">
                  Synced from Shopify {formatTimeAgo(product.cached_at)}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </ModalPortal>
  )
}

// ProductKPIs Component - animated KPI cards
function ProductKPIs({ status, products, lastSynced, formatTimeAgo }) {
  const animatedTotal = useCountAnimation(status?.product_count || 0, 2000)
  const animatedInStock = useCountAnimation(status?.in_stock_count || 0, 2000)
  const animatedOutOfStock = useCountAnimation(status?.out_of_stock_count || 0, 2000)
  const animatedUntracked = useCountAnimation(status?.untracked_count || 0, 2000)

  const total = status?.product_count || 0
  const outOfStock = status?.out_of_stock_count || 0
  const untracked = status?.untracked_count || 0
  const pctOut = total ? (outOfStock / total) * 100 : 0

  return (
    /* Three cards, not four.
       The old strip was Total / In Stock / Out of Stock / Untracked. On this
       catalogue that reads 7,713 / 7,701 / 12 / 0 — "In Stock" is 99.8% of the
       total and therefore restates it, and "Untracked" has been zero since the
       page was built. Two of the four cards could not tell you anything.

       What is left is what changes and what you can act on: how big the
       catalogue is, what the assistant cannot sell right now, and whether the
       data behind it is fresh enough to trust. */
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      <div className="card p-4">
        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">In the catalogue</p>
        <p className="text-2xl font-bold text-gray-900 mt-2 tabular-nums">{animatedTotal}</p>
        <p className="text-xs text-gray-400 mt-1">
          products the assistant can recommend
        </p>
      </div>

      <div className="card p-4">
        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">Cannot be sold</p>
        <p className={clsx('text-2xl font-bold mt-2 tabular-nums',
          outOfStock > 0 ? 'text-amber-600' : 'text-gray-900')}>
          {animatedOutOfStock}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {outOfStock === 0
            ? 'everything in stock'
            : `out of stock · ${pctOut < 0.1 ? '<0.1' : pctOut.toFixed(1)}% of the catalogue`}
          {untracked > 0 && ` · ${untracked} untracked`}
        </p>
      </div>

      <div className="card p-4 col-span-2 lg:col-span-1">
        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">Catalogue freshness</p>
        <p className={clsx('text-2xl font-bold mt-2',
          status?.stale ? 'text-amber-600' : 'text-gray-900')}>
          {lastSynced ? formatTimeAgo(lastSynced) : 'Never'}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {!lastSynced
            ? 'the assistant is answering from nothing'
            : status?.stale
              ? `stale — prices and stock may be wrong in replies`
              : 'prices and stock are current'}
        </p>
      </div>
    </div>
  )
}

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
  // The product whose detail is open. Held as the row itself, not an id — the
  // list already has every field the modal shows, so opening one costs nothing.
  const [detail, setDetail] = useState(null)

  // Settle the typing before asking the server. This fired on every keystroke,
  // and it fired fetchStatus() with it — four catalogue-wide COUNT queries
  // over 7,713 rows — even though none of those counts depend on the search
  // box at all.
  const [searchInput, setSearchInput] = useState('')
  useEffect(() => {
    const t = setTimeout(() => { setSearch(searchInput.trim()); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [searchInput])

  useEffect(() => { fetchProducts() }, [page, search])
  useEffect(() => { fetchStatus() }, [])

  const fetchProducts = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('page', page)
      params.set('per_page', perPage)
      if (search) params.set('search', search)

      const res = await fetch(`${API_BASE}/products?${params}`, {
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
      const res = await fetch(`${API_BASE}/products/sync/status`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) throw new Error('Failed to load sync status')
      const data = await res.json()
      setStatus(data)
    } catch (err) {
      console.error('Failed to fetch sync status:', err)
    }
  }

  // Poll the sync/status endpoint until the current job finishes.
  // Returns the final job object so callers can read its result.
  const pollJobUntilDone = async (expectedKind, intervalMs = 2000, timeoutMs = 600000) => {
    const startedAt = Date.now()
    while (true) {
      if (Date.now() - startedAt > timeoutMs) {
        throw new Error(`Job timed out after ${Math.round(timeoutMs / 1000)}s`)
      }
      await new Promise(resolve => setTimeout(resolve, intervalMs))

      const res = await fetch(`${API_BASE}/products/sync/status`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (!res.ok) continue
      const data = await res.json()
      setStatus(data)
      const job = data.current_job
      if (!job) continue
      if (job.kind !== expectedKind) continue  // some other job finished, keep waiting
      if (job.status === 'success') return job
      if (job.status === 'failed') {
        throw new Error(job.error || 'Job failed')
      }
      // still pending/running — loop
    }
  }

  const handleCheckSync = async () => {
    setChecking(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/products/sync/check`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      // 202 = job started, 409 = job already running (either way we poll)
      if (res.status !== 202 && res.status !== 409) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.message || `Failed to start check (HTTP ${res.status})`)
      }

      const job = await pollJobUntilDone('products_check')
      setSyncDiff(job.result)
      setShowSyncDiff(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(false)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/products/sync`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('authToken')}` },
      })
      if (res.status !== 202 && res.status !== 409) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.message || `Failed to start sync (HTTP ${res.status})`)
      }

      await pollJobUntilDone('products_apply')
      setShowSyncDiff(false)
      setSyncDiff(null)
      await fetchProducts()
      await fetchStatus()
    } catch (err) {
      setError(err.message)
    } finally {
      setSyncing(false)
    }
  }

  // Keep as raw ISO string — formatTimeAgo handles UTC interpretation
  const lastSynced = status?.last_synced_at || null
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
            {checking && status?.current_job?.progress
              ? status.current_job.progress
              : 'Check for Changes'}
          </button>
          <button
            onClick={handleSync}
            disabled={syncing || checking}
            className="btn-primary flex items-center gap-2 text-xs"
          >
            {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {syncing && status?.current_job?.progress
              ? status.current_job.progress
              : 'Sync Now'}
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
              <p className="text-xs text-amber-700 mt-0.5">Last synced {lastSynced ? formatTimeAgo(lastSynced) : 'never'}. Click "Sync Now" to refresh.</p>
            </div>
          </div>
        </div>
      )}

      {/* Sync diff modal */}
      {showSyncDiff && syncDiff && (
        <div className="card p-6 border border-blue-200 bg-blue-50 space-y-4">
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
                {syncing && status?.current_job?.progress
                  ? status.current_job.progress
                  : 'Apply Sync'}
              </button>
            </div>
          )}
          {syncDiff.in_sync && (
            <p className="text-sm text-green-700 font-medium">✓ Catalog is already in sync with Shopify</p>
          )}
        </div>
      )}

      {/* Status cards */}
      <ProductKPIs status={status} products={products} lastSynced={lastSynced} formatTimeAgo={formatTimeAgo} />

      {/* Search.
          Now covers name, tags, variants and description — the same fields the
          assistant searches. It was name-only, so the two disagreed sharply
          ("cotton": 184 here against 438 for the assistant) and you could not
          use this page to reproduce a recommendation you were questioning. */}
      <div>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-3 text-gray-400" />
          <input
            type="text"
            placeholder="Search name, tags, variants or description…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            className="input w-full pl-10"
          />
        </div>
        {search && (
          <p className="text-[11px] text-gray-400 mt-1.5">
            {total.toLocaleString()} match{total === 1 ? '' : 'es'} for “{search}” —
            the same fields the assistant searches when picking what to recommend.
          </p>
        )}
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="p-4 sm:p-6">
            <SkeletonList count={6} />
          </div>
        ) : products.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <Package size={32} className="text-gray-300 mb-3" />
            <p className="text-gray-500 font-medium">No products found</p>
            <p className="text-sm text-gray-400 mt-1">Try syncing from Shopify to populate the catalog</p>
          </div>
        ) : (
          <>
          <div className="overflow-x-auto hidden md:block">
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
                  <tr key={p.id}
                      onClick={() => setDetail(p)}
                      // Keyboard-reachable: a row that only responds to a mouse
                      // is a control half the people using it cannot press.
                      tabIndex={0}
                      role="button"
                      aria-label={`Open ${p.name}`}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setDetail(p) }
                      }}
                      className="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer focus:outline-none focus:bg-gray-50">
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-brand-100 to-brand-50 flex items-center justify-center shrink-0 overflow-hidden">
                          {(p.images && p.images[0])
                            ? <img src={p.images[0]} alt="" className="w-full h-full object-cover" />
                            : <Package size={20} className="text-brand-600" />}
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
                    {/* The label was wrapping to two lines inside a pill sized
                        for one — "In / Stock" stacked, with the rounded-full
                        border drawn around the taller box, which is what made
                        it read as a broken circle. whitespace-nowrap stops the
                        wrap; the column no longer has to be wide enough to
                        avoid it by luck. */}
                    <td className="px-4 py-4">
                      <div className="flex justify-center">
                        <span className={clsx(
                          'inline-flex items-center gap-1.5 text-[11px] font-semibold',
                          'px-2.5 py-1 rounded-full whitespace-nowrap border',
                          p.stock_quantity === 0
                            ? 'bg-red-50 text-red-700 border-red-200'
                            : 'bg-green-50 text-green-700 border-green-200'
                        )}>
                          <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0',
                            p.stock_quantity === 0 ? 'bg-red-500' : 'bg-green-500')} />
                          {p.stock_quantity === 0 ? 'Out of stock' : 'In stock'}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: stacked cards — same product data as the table */}
          <div className="md:hidden p-3 space-y-2.5">
            {products.map((p) => {
              const stock = p.stock_quantity
              const stockBadge =
                stock === 0
                  ? { label: 'Out of stock', cls: 'bg-red-50 text-red-600' }
                  : stock == null
                    ? { label: 'Untracked', cls: 'bg-gray-100 text-gray-500' }
                    : { label: `${stock} in stock`, cls: 'bg-green-50 text-green-600' }
              const img = (p.images && p.images[0]) || null
              return (
                <div key={p.id}
                     onClick={() => setDetail(p)}
                     tabIndex={0}
                     role="button"
                     aria-label={`Open ${p.name}`}
                     onKeyDown={(e) => {
                       if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setDetail(p) }
                     }}
                     className="bg-white border border-gray-200 rounded-2xl p-3 flex items-start gap-3 cursor-pointer hover:border-gray-300 transition-colors focus:outline-none focus:border-brand-500">
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-brand-100 to-brand-50 flex items-center justify-center shrink-0 overflow-hidden">
                    {img
                      ? <img src={img} alt="" className="w-full h-full object-cover" />
                      : <Package size={18} className="text-brand-600" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-gray-900 truncate">{p.name}</p>
                        <p className="text-xs font-semibold text-gray-700 truncate">{p.price || '—'}</p>
                      </div>
                      <span className={clsx('text-[10px] font-bold px-2 py-1 rounded-md shrink-0 whitespace-nowrap', stockBadge.cls)}>
                        {stockBadge.label}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {(p.variants || []).slice(0, 3).map((v, i) => (
                        <span key={i} className="text-[11px] bg-gray-100 text-gray-700 px-2 py-0.5 rounded">{v}</span>
                      ))}
                      {(p.variants || []).length > 3 && (
                        <span className="text-[11px] bg-gray-100 text-gray-600 px-2 py-0.5 rounded">+{(p.variants || []).length - 3}</span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
          </>
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
                        ? 'bg-black text-white'
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

      <ProductDetailModal product={detail} onClose={() => setDetail(null)} />
    </div>
  )
}