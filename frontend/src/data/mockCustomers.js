// Mock data for the Customer Profiling pages.
// Replace with real Shopify fetches once backend is wired up.

const FIRST_NAMES = ['Amina','Fatuma','Grace','Lulu','Wanjiru','Faith','Mary','Akinyi','Wairimu','Sarah','Lisa','Njeri','Brenda','Esther','Joy','Halima','Mercy','Caroline','Beatrice','Rebecca','Christine','Sharon','Liz','Tabitha','Susan']
const LAST_NAMES  = ['Otieno','Wanjiku','Mwangi','Kamau','Achieng','Njoroge','Kiprotich','Hassan','Okello','Muthoni','Wairimu','Owino','Kimani','Maina','Kinyua','Wambui','Auma','Atieno','Cherono','Nyambura']
const LOCATIONS   = ['Nairobi','Mombasa','Kisumu','Nakuru','Eldoret','Thika','Kiambu','Machakos','Nyeri','Meru','Naivasha','Malindi']
const CHANNELS    = ['instagram_dm','whatsapp','facebook_dm','tiktok_dm','instagram_comment']
const PRODUCT_NAMES = ['Black Wrap Dress','Floral Wrap Dress','Vitamin C Serum','Leather Tote Bag','Silk Scarf','Linen Blazer','Statement Earrings','Denim Jacket','Maxi Skirt','Cashmere Sweater','Velvet Heels','Pearl Necklace']
const TAGS = ['New','VIP','Loyal','At Risk','Churned','High Value','Frequent','New Customer']

function rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min }
function pick(arr) { return arr[Math.floor(Math.random() * arr.length)] }
function pickMany(arr, n) {
  const shuffled = [...arr].sort(() => 0.5 - Math.random())
  return shuffled.slice(0, n)
}

// ── Segment logic (RFM-lite) ────────────────────────────────────────
// Recency = days since last order; Frequency = total orders; Monetary = total spent
function computeSegment({ daysSinceLastOrder, totalOrders, totalSpent }) {
  if (totalOrders === 0) return 'new'
  if (totalSpent >= 50000 && daysSinceLastOrder <= 60) return 'vip'
  if (totalOrders >= 5 && daysSinceLastOrder <= 60)    return 'loyal'
  if (daysSinceLastOrder > 180 && totalOrders >= 2)    return 'churned'
  if (daysSinceLastOrder > 90 && totalOrders >= 2)     return 'at_risk'
  if (totalOrders <= 1 && daysSinceLastOrder <= 30)    return 'new'
  return 'regular'
}

export const SEGMENT_META = {
  vip:      { label: 'VIP',       color: 'brand',   description: 'High spend, recent activity' },
  loyal:    { label: 'Loyal',     color: 'success', description: 'Frequent repeat buyers' },
  regular:  { label: 'Regular',   color: 'neutral', description: 'Active, moderate spend' },
  new:      { label: 'New',       color: 'info',    description: 'Recently joined' },
  at_risk:  { label: 'At Risk',   color: 'warning', description: 'No activity in 90+ days' },
  churned:  { label: 'Churned',   color: 'danger',  description: 'Lost — 180+ days inactive' },
}

// ── Generate 48 mock customers ──────────────────────────────────────
function buildCustomer(id) {
  const first = pick(FIRST_NAMES)
  const last  = pick(LAST_NAMES)
  const totalOrders = rand(0, 18)
  const totalSpent  = totalOrders === 0 ? 0 : totalOrders * rand(1500, 8500)
  const daysSinceLastOrder = totalOrders === 0 ? 0 : rand(1, 365)
  const lastOrderDate = totalOrders === 0
    ? null
    : new Date(Date.now() - daysSinceLastOrder * 86400000).toISOString()
  const segment = computeSegment({ daysSinceLastOrder, totalOrders, totalSpent })

  return {
    id,
    shopify_id: `shopify_${1000000 + id}`,
    first_name: first,
    last_name: last,
    name: `${first} ${last}`,
    email: `${first.toLowerCase()}.${last.toLowerCase()}@example.com`,
    phone: `+25471${rand(1000000, 9999999)}`,
    location: pick(LOCATIONS),
    primary_channel: pick(CHANNELS),
    accepts_marketing: Math.random() > 0.3,
    total_orders: totalOrders,
    total_spent: totalSpent,
    aov: totalOrders > 0 ? Math.round(totalSpent / totalOrders) : 0,
    last_order_date: lastOrderDate,
    days_since_last_order: daysSinceLastOrder,
    created_at: new Date(Date.now() - rand(30, 720) * 86400000).toISOString(),
    segment,
    tags: pickMany(TAGS, rand(0, 3)),
    top_products: pickMany(PRODUCT_NAMES, rand(1, 4)),
    avatar_color: pick(['#ff5900','#10b981','#3b82f6','#f59e0b','#a855f7','#ec4899']),
  }
}

export const MOCK_CUSTOMERS = Array.from({ length: 48 }, (_, i) => buildCustomer(i + 1))

// ── Overview aggregates ─────────────────────────────────────────────
export function buildOverview(customers) {
  const total = customers.length
  const totalRevenue = customers.reduce((sum, c) => sum + c.total_spent, 0)
  const totalOrders = customers.reduce((sum, c) => sum + c.total_orders, 0)
  const newThisMonth = customers.filter(c => {
    const created = new Date(c.created_at)
    return (Date.now() - created.getTime()) / 86400000 <= 30
  }).length
  const repeatCustomers = customers.filter(c => c.total_orders >= 2).length
  const retentionRate = total > 0 ? (repeatCustomers / total) : 0
  const avgAOV = totalOrders > 0 ? Math.round(totalRevenue / totalOrders) : 0

  // Segment counts
  const segmentCounts = customers.reduce((acc, c) => {
    acc[c.segment] = (acc[c.segment] || 0) + 1
    return acc
  }, {})

  // Channel breakdown
  const channelCounts = customers.reduce((acc, c) => {
    acc[c.primary_channel] = (acc[c.primary_channel] || 0) + 1
    return acc
  }, {})
  const channelBreakdown = Object.entries(channelCounts).map(([name, count]) => ({
    name: name.replace('_', ' '),
    count,
    percent: Math.round((count / total) * 100),
  }))

  // AOV by month — last 6 months, simulated
  const months = ['Jan','Feb','Mar','Apr','May','Jun']
  const aovByMonth = months.map(m => ({
    month: m,
    aov: rand(3500, 6500),
    orders: rand(40, 120),
  }))

  // Top products (aggregate)
  const productMentions = {}
  customers.forEach(c => {
    c.top_products.forEach(p => {
      productMentions[p] = (productMentions[p] || 0) + 1
    })
  })
  const topProducts = Object.entries(productMentions)
    .map(([name, count]) => ({ name, purchases: count }))
    .sort((a, b) => b.purchases - a.purchases)
    .slice(0, 6)

  // Top spenders
  const topSpenders = [...customers]
    .sort((a, b) => b.total_spent - a.total_spent)
    .slice(0, 5)

  // Most frequent buyers
  const topFrequent = [...customers]
    .sort((a, b) => b.total_orders - a.total_orders)
    .slice(0, 5)

  return {
    kpis: {
      total_customers: total,
      new_this_month: newThisMonth,
      repeat_customers: repeatCustomers,
      retention_rate: retentionRate,
      total_revenue: totalRevenue,
      avg_aov: avgAOV,
    },
    segmentCounts,
    channelBreakdown,
    aovByMonth,
    topProducts,
    topSpenders,
    topFrequent,
  }
}

// ── Single-customer order history ───────────────────────────────────
export function buildOrderHistory(customer) {
  if (customer.total_orders === 0) return []
  return Array.from({ length: customer.total_orders }, (_, i) => {
    const daysAgo = Math.round((customer.days_since_last_order / customer.total_orders) * (i + 1))
    return {
      id: `ORD-${10000 + customer.id * 100 + i}`,
      date: new Date(Date.now() - daysAgo * 86400000).toISOString(),
      items: rand(1, 4),
      total: rand(1500, 8500),
      status: pick(['fulfilled', 'fulfilled', 'fulfilled', 'pending', 'refunded']),
      products: pickMany(PRODUCT_NAMES, rand(1, 3)),
    }
  }).reverse()
}

// Spending trend over time (last 12 months)
export function buildSpendingTrend(customer) {
  const months = ['Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May','Jun']
  return months.map(m => ({
    month: m,
    spent: customer.total_orders === 0 ? 0 : rand(0, Math.round(customer.aov * 1.5)),
  }))
}