import { Database, Clock, Calculator, ListChecks, Crown, Heart, Users, Sparkles, UserPlus, AlertTriangle, UserMinus } from 'lucide-react'

// Segment → action playbook (mirrors backend SEGMENT_ACTIONS).
const PLAYBOOK = [
  { key: 'vip',          label: 'VIP',          Icon: Crown,         color: 'text-amber-600',  dot: 'bg-amber-500',  action: 'Send VIP invite + exclusive early access to new drops.' },
  { key: 'loyal',        label: 'Loyal',        Icon: Heart,         color: 'text-pink-600',   dot: 'bg-pink-500',   action: 'Reward loyalty — offer a thank-you perk or referral bonus.' },
  { key: 'regular',      label: 'Regular',      Icon: Users,         color: 'text-blue-600',   dot: 'bg-blue-500',   action: 'Encourage a repeat purchase with a curated recommendation.' },
  { key: 'new',          label: 'New Convert',  Icon: Sparkles,      color: 'text-green-600',  dot: 'bg-green-500',  action: 'Welcome series — introduce bestsellers and the brand story.' },
  { key: 'at_risk',      label: 'At Risk',      Icon: AlertTriangle, color: 'text-orange-600', dot: 'bg-orange-500', action: 'Win-back nudge — a time-limited "we miss you" offer.' },
  { key: 'churned',      label: 'Churned',      Icon: UserMinus,     color: 'text-gray-600',   dot: 'bg-gray-500',   action: 'Reactivation campaign — strong incentive to return.' },
  { key: 'never_bought', label: 'Never Bought', Icon: UserPlus,      color: 'text-slate-600',  dot: 'bg-slate-400',  action: 'First-purchase incentive — a welcome discount to convert.' },
]

function Card({ icon: Icon, title, children }) {
  return (
    <div className="card p-5">
      <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-3">
        <Icon size={14} className="text-brand-500" /> {title}
      </h2>
      {children}
    </div>
  )
}

export default function CustomerConfig() {
  return (
    <div className="space-y-6 w-full max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Configuration</h1>
        <p className="text-sm text-gray-500 mt-0.5">Data sources, sync schedule and scoring method.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Left column */}
        <div className="space-y-5">
          <Card icon={Database} title="Data sources">
            <div className="space-y-2 text-sm text-gray-700">
              <p>Customers feed: <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">/api/customers</code></p>
              <p>Orders feed: <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">/api/orders</code></p>
              <p className="text-xs text-gray-500 leading-relaxed pt-1">
                Customer and order data is mirrored from Shopify into a local cache. Segments and
                RFM scores are computed from these feeds on each sync.
              </p>
            </div>
          </Card>

          <Card icon={Clock} title="Sync">
            <div className="space-y-2 text-sm text-gray-700">
              <p>Delta sync: <span className="font-semibold">every 3 hours</span> (products, customers, orders)</p>
              <p>Full reconcile: <span className="font-semibold">daily · 01:00 UTC</span></p>
              <p>Live updates: <span className="font-semibold">Shopify webhooks</span> (near-instant for new orders)</p>
              <p className="text-xs text-gray-500 leading-relaxed pt-1">
                RFM scores are recomputed at the end of each customer and order sync.
              </p>
            </div>
          </Card>

          <Card icon={Calculator} title="Scoring method">
            <p className="text-sm text-gray-700 leading-relaxed">
              Every buyer is graded 1–5 on Recency, Frequency and Monetary using quintiles across
              the whole base. Recency is inverted, so fewer days since the last order scores higher.
              The three scores combine into a named segment. Customers with no orders are kept aside
              as <span className="font-semibold">Never bought</span>.
            </p>
          </Card>
        </div>

        {/* Right column — playbook */}
        <Card icon={ListChecks} title="Segments & suggested actions">
          <div className="space-y-3">
            {PLAYBOOK.map(({ key, label, Icon, color, dot, action }) => (
              <div key={key} className="flex items-start gap-3">
                <span className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dot}`} />
                <div>
                  <p className={`text-sm font-semibold ${color} flex items-center gap-1.5`}>
                    <Icon size={12} /> {label}
                  </p>
                  <p className="text-xs text-gray-600 leading-relaxed mt-0.5">{action}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}