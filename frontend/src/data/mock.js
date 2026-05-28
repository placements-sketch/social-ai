// ─────────────────────────────────────────────────────────────────────────────
// Mock data — replace with real API calls when backend is wired up
// ─────────────────────────────────────────────────────────────────────────────

export const stats = {
  messagesToday: 142,
  autoRepliesSent: 138,
  humanOverrides: 4,
  failedResponses: 2,
  outOfStockQueries: 17,
}

export const activityFeed = [
  { id: 1, time: '2 min ago',  icon: 'message',  text: 'User @amina_ke asked about Black Dress size M',        channel: 'instagram_dm' },
  { id: 2, time: '3 min ago',  icon: 'bot',      text: 'AI responded via Instagram DM — response time 1.1s',  channel: 'instagram_dm' },
  { id: 3, time: '5 min ago',  icon: 'database', text: 'Shopify stock checked: Floral Wrap Dress — 14 units',    channel: 'shopify' },
  { id: 4, time: '8 min ago',  icon: 'message',  text: 'User +254712345678 asked about lipstick shades',           channel: 'whatsapp'    },
  { id: 5, time: '9 min ago',  icon: 'bot',      text: 'AI responded via WhatsApp — response time 0.9s',           channel: 'whatsapp'    },
  { id: 6, time: '11 min ago', icon: 'message',  text: 'Facebook user asked: "Do you ship to Kisumu?"',            channel: 'facebook_dm' },
  { id: 7, time: '12 min ago', icon: 'alert',    text: 'Vitamin C Serum out of stock — 3 queries unanswered',      channel: 'alert'       },
  { id: 8, time: '15 min ago', icon: 'comment',  text: 'Facebook comment: "price?" on product post — DM triggered',channel: 'facebook_comment' },
  { id: 9, time: '17 min ago', icon: 'comment',  text: 'Instagram comment: "available?" — DM flow triggered',      channel: 'instagram_comment' },
  { id: 10,time: '18 min ago', icon: 'database', text: 'Shopify sync completed — 48 products updated',             channel: 'shopify'     },
  { id: 11,time: '20 min ago', icon: 'message',  text: 'TikTok user @tiktok_fashionista asked about dress colors', channel: 'tiktok_dm'   },
  { id: 12,time: '21 min ago', icon: 'bot',      text: 'AI responded via TikTok DM — response time 1.0s',          channel: 'tiktok_dm'   },
  { id: 13,time: '23 min ago', icon: 'comment',  text: 'TikTok comment: "How much?" on product video — DM triggered', channel: 'tiktok_comment' },
]
export const alerts = [
  { id: 1, level: 'warning', message: 'Shopify product mismatch: 3 items have conflicting stock' },
  { id: 2, level: 'info',    message: 'WhatsApp webhook response time elevated (avg 3.2s)' },
  { id: 3, level: 'info',    message: 'TikTok webhook: 12 new messages received in last hour' },
]

export const conversations = [
  {
    id: 'c1',
    handle: '@amina_ke',
    platform: 'instagram_dm',
    lastMessage: 'Do you have the black dress in medium?',
    time: '2m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'Hi! Do you have the black dress in medium?', time: '14:32' },
      { id: 2, from: 'ai',   text: 'Hi there! 👋 Yes, the Black Wrap Dress is available in Medium. We have 8 units in stock. Would you like to place an order?', time: '14:32', meta: { intent: 'stock_inquiry', product: 'Black Wrap Dress', stock: '8 units', responseTime: '1.1s' } },
      { id: 3, from: 'user', text: 'What colors does it come in?', time: '14:33' },
      { id: 4, from: 'ai',   text: 'The Black Wrap Dress comes in Black, Burgundy, and Olive Green. All sizes XS–XL are available in Black. Burgundy and Olive are limited to S–L. Which color catches your eye? 😊', time: '14:33', meta: { intent: 'product_inquiry', product: 'Black Wrap Dress', stock: '8 units', responseTime: '0.9s' } },
    ],
  },
  {
    id: 'c2',
    handle: '+254712345678',
    platform: 'whatsapp',
    lastMessage: 'How much is the vitamin C serum?',
    time: '9m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'Hello, how much is the vitamin C serum?', time: '14:25' },
      { id: 2, from: 'ai',   text: 'Hi! The Vitamin C Brightening Serum is KES 2,200 for 30ml and KES 3,100 for 50ml. It\'s a bestseller for glowing skin! ✨ Would you like to order?', time: '14:25', meta: { intent: 'price_inquiry', product: 'Vitamin C Serum', stock: '0 units', responseTime: '0.9s' } },
      { id: 3, from: 'user', text: 'Is it in stock?', time: '14:26' },
      { id: 4, from: 'ai',   text: 'Unfortunately the Vitamin C Serum is currently out of stock 😔 Would you like me to notify you as soon as it\'s back?', time: '14:26', meta: { intent: 'stock_inquiry', product: 'Vitamin C Serum', stock: '0 units', responseTime: '1.0s' } },
    ],
  },
  {
    id: 'c3',
    handle: '@beauty_nairobi',
    platform: 'instagram_comment',
    lastMessage: 'price? 👀',
    time: '15m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'price? 👀', time: '14:19' },
      { id: 2, from: 'ai',   text: 'Hey! 👋 We\'ve sent you a DM with all the details. Check your inbox! 💌', time: '14:19', meta: { intent: 'price_inquiry', product: 'Unknown', stock: 'N/A', responseTime: '0.7s' } },
    ],
  },
  {
    id: 'c4',
    handle: '@fatuma.style',
    platform: 'instagram_dm',
    lastMessage: 'My order hasn\'t arrived yet',
    time: '22m ago',
    status: 'human_override',
    unread: true,
    messages: [
      { id: 1, from: 'user', text: 'Hi, my order #KE2041 hasn\'t arrived yet. It\'s been 5 days.', time: '14:12' },
      { id: 2, from: 'ai',   text: 'I\'m sorry to hear that! Please share your order number and I\'ll look it up for you.', time: '14:12', meta: { intent: 'order_status', product: 'N/A', stock: 'N/A', responseTime: '1.2s' } },
      { id: 3, from: 'user', text: 'I already gave it — #KE2041', time: '14:13' },
      { id: 4, from: 'human', text: '(Agent took over) Hi Fatuma, I\'m checking on order #KE2041 right now. Give me 2 minutes!', time: '14:15' },
    ],
  },
  {
    id: 'c5',
    handle: '+254798001122',
    platform: 'whatsapp',
    lastMessage: 'Do you deliver to Mombasa?',
    time: '31m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'Do you deliver to Mombasa?', time: '14:03' },
      { id: 2, from: 'ai',   text: 'Yes! We deliver nationwide including Mombasa 🚚 Delivery takes 2–3 business days and costs KES 350. Would you like to place an order?', time: '14:03', meta: { intent: 'unknown', product: 'N/A', stock: 'N/A', responseTime: '1.3s' } },
    ],
  },
  {
    id: 'c6',
    handle: 'David Ochieng',
    platform: 'facebook_dm',
    lastMessage: 'Do you ship to Kisumu?',
    time: '11m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'Hi! Do you ship to Kisumu?', time: '14:23' },
      { id: 2, from: 'ai',   text: 'Yes, we ship nationwide including Kisumu! 🚚 Delivery takes 2–3 business days and costs KES 350. Is there a specific product you\'d like to order?', time: '14:23', meta: { intent: 'unknown', product: 'N/A', stock: 'N/A', responseTime: '1.0s' } },
    ],
  },
  {
    id: 'c7',
    handle: 'Wanjiru Kamau',
    platform: 'facebook_comment',
    lastMessage: 'price? 🔥',
    time: '15m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'price? 🔥', time: '14:19' },
      { id: 2, from: 'ai',   text: 'Hey Wanjiru! 👋 We\'ve sent you a DM with all the pricing details. Check your inbox! 💌', time: '14:19', meta: { intent: 'price_inquiry', product: 'Unknown', stock: 'N/A', responseTime: '0.8s' } },
    ],
  },
  {
    id: 'c8',
    handle: '@tiktok_fashionista',
    platform: 'tiktok_dm',
    lastMessage: 'Is the black dress available?',
    time: '7m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'Hi! Is the black dress available in size M?', time: '14:27' },
      { id: 2, from: 'ai',   text: 'Hey! 👋 Yes, the Black Wrap Dress is available in size M — we have 8 units in stock! 🎉 Would you like to place an order?', time: '14:27', meta: { intent: 'stock_inquiry|product_inquiry', product: 'Black Wrap Dress', stock: '8 units', responseTime: '1.0s' } },
    ],
  },
  {
    id: 'c9',
    handle: 'TikTok User',
    platform: 'tiktok_comment',
    lastMessage: 'How much?',
    time: '5m ago',
    status: 'ai_replied',
    unread: false,
    messages: [
      { id: 1, from: 'user', text: 'How much? 💕', time: '14:29' },
      { id: 2, from: 'ai',   text: 'Hey! 💕 We\'ve sent you a DM with all the details. Check your inbox! 📱', time: '14:29', meta: { intent: 'price_inquiry', product: 'Unknown', stock: 'N/A', responseTime: '0.7s' } },
    ],
  },
]

export const products = [
  { id: 'p1', shopifyId: '001', name: 'Floral Wrap Dress',      price: 3500, variants: ['XS','S','M','L','XL'], tags: ['dress','floral','summer'], shopifyStock: 14, image: null },
  { id: 'p2', shopifyId: '002', name: 'Matte Lipstick',         price: 850,  variants: ['Red','Nude','Berry','Coral'], tags: ['beauty','lips','makeup'], shopifyStock: 52, image: null },
  { id: 'p3', shopifyId: '003', name: 'Vitamin C Serum',        price: 2200, variants: ['30ml','50ml'], tags: ['skincare','serum','glow'], shopifyStock: 5, image: null },
  { id: 'p4', shopifyId: '004', name: 'Black Wrap Dress',       price: 4200, variants: ['XS','S','M','L','XL'], tags: ['dress','black','evening'], shopifyStock: 8, image: null },
  { id: 'p5', shopifyId: '005', name: 'Hydrating Moisturizer',  price: 1800, variants: ['50ml','100ml'], tags: ['skincare','moisturizer'], shopifyStock: 23, image: null },
  { id: 'p6', shopifyId: '006', name: 'Gold Hoop Earrings',     price: 1200, variants: ['Small','Large'], tags: ['jewelry','gold','accessories'], shopifyStock: 0, image: null },
]

export const analyticsData = {
  intentBreakdown: [
    { name: 'Price Inquiry',   value: 38 },
    { name: 'Stock Inquiry',   value: 27 },
    { name: 'Product Info',    value: 18 },
    { name: 'Order Status',    value: 10 },
    { name: 'Complaint',       value: 4  },
    { name: 'Other',           value: 3  },
  ],
  topProducts: [
    { name: 'Black Wrap Dress',      queries: 41 },
    { name: 'Vitamin C Serum',       queries: 34 },
    { name: 'Floral Wrap Dress',     queries: 28 },
    { name: 'Matte Lipstick',        queries: 22 },
    { name: 'Hydrating Moisturizer', queries: 17 },
  ],
  weeklyMessages: [
    { day: 'Mon', messages: 98,  replies: 95  },
    { day: 'Tue', messages: 112, replies: 109 },
    { day: 'Wed', messages: 87,  replies: 85  },
    { day: 'Thu', messages: 134, replies: 131 },
    { day: 'Fri', messages: 142, replies: 138 },
    { day: 'Sat', messages: 76,  replies: 74  },
    { day: 'Sun', messages: 61,  replies: 60  },
  ],
  channelSplit: [
    { name: 'Instagram DM',       value: 40 },
    { name: 'WhatsApp',           value: 25 },
    { name: 'Instagram Comments', value: 12 },
    { name: 'Facebook Messenger', value: 12 },
    { name: 'TikTok DM',          value: 7  },
    { name: 'TikTok Comments',    value: 4  },
  ],
  aiPerformance: {
    avgResponseTime: '1.1s',
    successRate: '97.2%',
    overrideRate: '2.8%',
  },
}

export const logs = [
  { id: 1, time: '14:32:01', level: 'success', source: 'instagram_dm',      message: 'Inbound DM from @amina_ke — intent: stock_inquiry — replied in 1.1s' },
  { id: 2, time: '14:32:00', level: 'info',    source: 'integrations.shopify', message: 'Stock check: Black Wrap Dress → 8 units' },
  { id: 3, time: '14:31:59', level: 'info',    source: 'integrations.shopify', message: 'Product fetch: Black Wrap Dress → KES 4,200 — variants: XS S M L XL' },
  { id: 4, time: '14:31:58', level: 'info',    source: 'ai.generator',      message: 'Claude API prompt sent — model: claude-3-5-sonnet — tokens: 312' },
  { id: 5, time: '14:25:11', level: 'success', source: 'whatsapp',          message: 'Inbound WA from +254712345678 — intent: price_inquiry — replied in 0.9s' },
  { id: 6, time: '14:25:10', level: 'info',    source: 'integrations.shopify', message: 'Stock check: Vitamin C Serum → 0 units (OUT OF STOCK)' },
  { id: 7, time: '14:19:03', level: 'success', source: 'instagram_comment', message: 'Comment from @beauty_nairobi — DM flow triggered' },
  { id: 8, time: '14:12:44', level: 'warning', source: 'services',          message: 'Human override triggered for conversation c4 (@fatuma.style)' },
  { id: 9, time: '13:58:22', level: 'error',   source: 'integrations.shopify', message: 'Shopify API timeout after 5000ms — falling back to cached stock data' },
  { id: 10,time: '13:45:00', level: 'info',    source: 'integrations.shopify', message: 'Shopify sync completed — 48 products updated' },
  { id: 11,time: '13:30:15', level: 'success', source: 'facebook_dm',          message: 'Inbound FB Messenger from David Ochieng — intent: unknown — replied in 1.0s' },
  { id: 12,time: '13:29:55', level: 'success', source: 'facebook_comment',     message: 'FB comment from Wanjiru Kamau — DM flow triggered — replied in 0.8s' },
  { id: 13,time: '13:15:22', level: 'success', source: 'tiktok_dm',            message: 'Inbound TikTok DM from @tiktok_fashionista — intent: stock_inquiry — replied in 1.0s' },
  { id: 14,time: '13:14:18', level: 'info',    source: 'integrations.tiktok', message: 'TikTok webhook verified — signature valid' },
  { id: 15,time: '13:10:45', level: 'success', source: 'tiktok_comment',       message: 'TikTok comment detected — DM flow triggered for user' },
]

export const automationRules = [
  { id: 'r1', name: 'Price Reply',        enabled: true,  trigger: 'Message contains: "price", "how much", "bei", "ksh"', action: 'Always include price from Shopify in reply' },
  { id: 'r2', name: 'Out of Stock',       enabled: true,  trigger: 'Shopify stock = 0',                                     action: 'Reply: "Currently out of stock" + suggest similar product' },
  { id: 'r3', name: 'Comment → DM',       enabled: true,  trigger: 'Instagram comment contains: "price?", "how much?"',    action: 'Reply publicly: "Check your DMs!" + trigger DM flow' },
  { id: 'r4', name: 'After Hours',        enabled: true,  trigger: 'Any message (always on)',                              action: 'Auto-reply normally — no after-hours delay' },
  { id: 'r5', name: 'Complaint Escalate', enabled: false, trigger: 'Intent = complaint',                                   action: 'Flag for human review + send empathy reply' },
  { id: 'r6', name: 'Order Status',       enabled: true,  trigger: 'Intent = order_status',                                action: 'Ask for order number + flag for human follow-up' },
]
