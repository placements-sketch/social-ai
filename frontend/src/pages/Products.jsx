import { useState } from 'react'
import { products } from '../data/mock'
import { CheckCircle, RefreshCw, Package } from 'lucide-react'
import clsx from 'clsx'

const tabs = ['All Products', 'Out of Stock']

export default function Products() {
  const [tab, setTab] = useState('All Products')

  const filtered = products.filter(p => {
    if (tab === 'Out of Stock') return p.shopifyStock === 0
    return true
  })

  const outOfStock = products.filter(p => p.shopifyStock === 0).length

  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Products & Inventory</h1>
          <p className="text-sm text-gray-500 mt-0.5">Shopify is the source of truth for all inventory</p>
        </div>
        <button className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} /> Sync Now
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="stat-card">
          <p className="text-xs text-gray-500 font-medium">Total Products</p>
          <p className="text-3xl font-bold text-gray-900">{products.length}</p>
          <p className="text-xs text-gray-400">Last sync: 2 min ago</p>
        </div>
        <div className={clsx('stat-card', outOfStock > 0 && 'border border-red-200')}>
          <div className="flex items-center gap-1.5">
            <Package size={13} className="text-red-500" />
            <p className="text-xs text-red-600 font-semibold">Out of Stock</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{outOfStock}</p>
          <p className="text-xs text-gray-400">Shopify qty = 0</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1 w-fit shadow-sm">
        {tabs.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'px-4 py-1.5 rounded-md text-sm font-semibold transition-colors',
              tab === t ? 'bg-brand-500 text-white shadow-sm' : 'text-gray-500 hover:text-gray-800'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Table — horizontal scroll on mobile */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[600px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-bold uppercase tracking-wide">Product</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-bold uppercase tracking-wide">Price</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-bold uppercase tracking-wide">Variants</th>
                <th className="text-center px-4 py-3 text-xs text-gray-500 font-bold uppercase tracking-wide">Stock</th>
                <th className="text-center px-4 py-3 text-xs text-gray-500 font-bold uppercase tracking-wide">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const oos = p.shopifyStock === 0
                return (
                  <tr key={p.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-gray-100 flex items-center justify-center shrink-0">
                          <Package size={14} className="text-gray-400" />
                        </div>
                        <div>
                          <p className="font-semibold text-gray-900">{p.name}</p>
                          <p className="text-xs text-gray-400">ID: {p.shopifyId}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-700 font-medium">KES {p.price.toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {p.variants.slice(0, 3).map(v => (
                          <span key={v} className="badge bg-gray-100 text-gray-600">{v}</span>
                        ))}
                        {p.variants.length > 3 && (
                          <span className="badge bg-gray-100 text-gray-400">+{p.variants.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={clsx('font-bold', oos ? 'text-red-500' : 'text-green-600')}>
                        {p.shopifyStock}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {oos ? (
                        <span className="badge bg-red-50 text-red-600 border border-red-200">Out of Stock</span>
                      ) : (
                        <span className="badge bg-green-50 text-green-600 border border-green-200">
                          <CheckCircle size={10} /> In Stock
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
