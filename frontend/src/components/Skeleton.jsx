import clsx from 'clsx'

export function SkeletonCard({ className = '' }) {
  return (
    <div className={clsx('card p-4 sm:p-5', className)}>
      <div className="space-y-3">
        {/* Header skeleton */}
        <div className="flex items-start justify-between gap-2 mb-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="w-9 sm:w-11 h-9 sm:h-11 rounded-xl bg-gray-200 animate-pulse shrink-0" />
            <div className="flex-1 min-w-0 space-y-2">
              <div className="h-4 bg-gray-200 rounded animate-pulse w-3/4" />
              <div className="h-3 bg-gray-100 rounded animate-pulse w-1/2" />
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="h-6 w-16 bg-gray-200 rounded animate-pulse" />
            <div className="h-6 w-11 bg-gray-200 rounded-full animate-pulse" />
          </div>
        </div>
        
        {/* Content skeleton - 2 column grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
          <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
          <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
          <div className="h-10 bg-gray-100 rounded-lg animate-pulse" />
        </div>
      </div>
    </div>
  )
}

export function SkeletonText({ lines = 3, className = '' }) {
  return (
    <div className={clsx('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 bg-gray-200 rounded animate-pulse"
          style={{ width: `${100 - i * 15}%` }}
        />
      ))}
    </div>
  )
}

export function SkeletonList({ count = 4, className = '' }) {
  return (
    <div className={clsx('space-y-2 sm:space-y-3', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

export function SkeletonGrid({ count = 6, columns = 2, className = '' }) {
  return (
    <div className={clsx(`grid grid-cols-1 sm:grid-cols-${columns} gap-2 sm:gap-3`, className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

export function SkeletonHeader({ className = '' }) {
  return (
    <div className={clsx('space-y-3', className)}>
      <div className="h-8 bg-gray-200 rounded animate-pulse w-2/3" />
      <div className="h-4 bg-gray-100 rounded animate-pulse w-1/2" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, columns = 4, className = '' }) {
  return (
    <div className={clsx('space-y-2', className)}>
      {/* Header */}
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
        {Array.from({ length: columns }).map((_, i) => (
          <div key={`header-${i}`} className="h-4 bg-gray-200 rounded animate-pulse" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={`row-${rowIdx}`} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
          {Array.from({ length: columns }).map((_, colIdx) => (
            <div key={`cell-${rowIdx}-${colIdx}`} className="h-4 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      ))}
    </div>
  )
}
