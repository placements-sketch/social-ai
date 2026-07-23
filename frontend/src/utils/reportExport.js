// src/utils/reportExport.js
// Professional CSV + PDF analytics reports, shared by Dashboard and Analytics.

const BRAND = [255, 89, 0]     // Shop Zetu orange
const DARK  = [26, 26, 46]
const MUTE  = [130, 130, 130]

const pct = (v) => `${((v || 0) * 100).toFixed(1)}%`
const num = (v) => (v ?? 0).toLocaleString()
const ms  = (v) => (v == null ? '—' : v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`)
const clean = (s) => String(s || '').replace(/_/g, ' ')

// Pull every section out of the loaded analytics data into table-ready rows.
function buildSections(data) {
  const kpis = data?.kpis || {}
  const conv = data?.conversion || {}
  const channels = data?.channel_split || []
  const intents = data?.intent_breakdown || []
  const products = data?.top_products || []
  const agents = data?.agents || []

  const sections = [
    {
      title: 'Overview',
      head: ['Metric', 'Value'],
      rows: [
        ['Total messages', num(kpis.messages_total)],
        ['Inbound', num(kpis.inbound_total)],
        ['AI replies', num(kpis.ai_replies_total)],
        ['Human replies', num(kpis.human_replies_total)],
        ['AI engagement rate', pct(kpis.ai_success_rate)],
        ['Avg response time', ms(kpis.avg_response_time_ms)],
        ['Human overrides', num(kpis.human_override_total)],
        ['Escalated', num(kpis.escalated_total)],
        ['Total conversations', num(kpis.conversations_total)],
      ],
    },
    {
      title: 'Conversion',
      head: ['Metric', 'Value'],
      rows: [
        ['Conversations with a recommendation', num(conv.recommended_conversations)],
        ['Converted conversations', num(conv.converted_conversations)],
        ['Conversion rate', pct(conv.conversion_rate)],
        ['Attributed orders', num(conv.attributed_orders)],
        ['Attributed revenue', `KES ${num(Math.round(conv.attributed_revenue || 0))}`],
      ],
    },
  ]

  if (channels.length)
    sections.push({
      title: 'Channel breakdown',
      head: ['Channel', 'Messages', 'Share'],
      rows: channels.map((c) => [clean(c.name), num(c.count), `${c.percent}%`]),
    })

  if (intents.length)
    sections.push({
      title: 'Intent breakdown',
      head: ['Intent', 'Count', 'Share'],
      rows: intents.map((it) => [clean(it.name), num(it.count), `${it.percent}%`]),
    })

  if (products.length)
    sections.push({
      title: 'Top products customers ask about',
      head: ['#', 'Product', 'Asks'],
      rows: products.map((p, i) => [i + 1, p.name, num(p.mentions)]),
    })

  if (agents.length)
    sections.push({
      title: 'Agent performance',
      head: ['Agent', 'Active', 'Assigned', 'Resolved', 'Human replies', 'AI on their convos'],
      rows: agents.map((a) => [
        a.agent?.full_name || a.agent?.name || a.agent?.email || '—',
        num(a.active_total),
        num(a.assigned_total),
        num(a.resolved_in_window),
        num(a.human_replies_in_window),
        num(a.ai_replies_on_their_conversations),
      ]),
    })

  return sections
}

export function exportAnalyticsCSV(data, meta) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const line = (...cells) => cells.map(esc).join(',')
  const out = []

  out.push(line('Shop Zetu — Social AI Assistant — Analytics Report'))
  out.push(line('Period', meta.periodLabel))
  out.push(line('Generated', meta.generatedAt))
  out.push('')

  for (const s of buildSections(data)) {
    out.push(line(s.title.toUpperCase()))
    out.push(line(...s.head))
    for (const r of s.rows) out.push(line(...r))
    out.push('')
  }

  const blob = new Blob([out.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `shopzetu-analytics-${meta.periodSlug}-${meta.dateSlug}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function exportAnalyticsPDF(data, meta) {
  const { jsPDF } = await import('jspdf')
  const mod = await import('jspdf-autotable')
  const autoTable = mod.default || mod.autoTable   // works across versions

  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const mx = 40

  // Header
  doc.setFont('helvetica', 'bold'); doc.setFontSize(20); doc.setTextColor(...DARK)
  doc.text('Shop Zetu', mx, 50)
  doc.setFont('helvetica', 'normal'); doc.setFontSize(12); doc.setTextColor(...BRAND)
  doc.text('Social AI Assistant — Analytics Report', mx, 68)
  doc.setFontSize(9); doc.setTextColor(...MUTE)
  doc.text(`Period: ${meta.periodLabel}    ·    Generated: ${meta.generatedAt}`, mx, 84)
  doc.setDrawColor(...BRAND); doc.setLineWidth(1.5); doc.line(mx, 92, pageW - mx, 92)

  let y = 112
  for (const s of buildSections(data)) {
    if (y > pageH - 120) { doc.addPage(); y = 50 }
    doc.setFont('helvetica', 'bold'); doc.setFontSize(11); doc.setTextColor(...DARK)
    doc.text(s.title, mx, y)
    autoTable(doc, {
      startY: y + 8,
      head: [s.head],
      body: s.rows,
      margin: { left: mx, right: mx },
      styles: { fontSize: 9, cellPadding: 5, textColor: DARK, lineColor: [235, 235, 235], lineWidth: 0.5 },
      headStyles: { fillColor: BRAND, textColor: [255, 255, 255], fontStyle: 'bold' },
      alternateRowStyles: { fillColor: [249, 249, 251] },
      theme: 'striped',
    })
    y = doc.lastAutoTable.finalY + 26
  }

  // Footer on every page
  const pages = doc.internal.getNumberOfPages()
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i)
    doc.setFontSize(8); doc.setTextColor(...MUTE)
    doc.text('Shop Zetu · Confidential', mx, pageH - 20)
    doc.text(`Page ${i} of ${pages}`, pageW - mx, pageH - 20, { align: 'right' })
  }

  doc.save(`shopzetu-analytics-${meta.periodSlug}-${meta.dateSlug}.pdf`)
}