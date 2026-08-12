import { listCustomers } from '../api/customers'
import { SEGMENT_META } from './segments'

/*
 * Exporting the customer list — CSV and PDF.
 *
 * These are two different tools, not one feature with a file-format switch, and
 * the difference is the reason the caps below are not the same number:
 *
 *   CSV is the data. Someone opens it in Excel and pivots it. It should carry
 *   every matching row it reasonably can, and nothing but rows.
 *
 *   PDF is a document. Someone emails it or brings it to a meeting. 20,000 rows
 *   is ~600 pages and roughly 40MB — technically an export, practically
 *   unopenable. It carries a bounded top-N under the sort already applied, and
 *   says on its face that that is what it is.
 *
 * Both caps are stated in the output rather than applied quietly. A file that
 * silently stops at N reads as "this is all of them" to whoever receives it,
 * which is how a partial list becomes "our customer base" in someone else's
 * inbox.
 */

// Server-side MAX_PER_PAGE.
const PER = 100

// CSV: browser-memory stop. 20,000 rows is a ~3MB file that Excel opens fine.
export const CSV_ROW_CAP = 20_000

// PDF: what stays readable as a document — roughly 15 pages.
export const PDF_ROW_CAP = 500

const BRAND = [199, 234, 70]   // Shop Zetu lime
const DARK  = [26, 26, 46]
const MUTE  = [130, 130, 130]

const num = (v) => (v ?? 0).toLocaleString()

export const SORT_LABELS = {
  spent_desc:  'Highest spend',
  orders_desc: 'Most orders',
  recent:      'Most recent order',
  name:        'Name (A–Z)',
}

/**
 * Every customer matching the current filters, up to `cap`.
 *
 * Takes the same search/segment/sort the table is using, so what you export is
 * what you were looking at. Reports progress because at 20,000 rows this is 200
 * round trips and a button that just sits there looks hung.
 *
 * Returns `truncated` so the caller can say so out loud — it is the difference
 * between a complete list and a sample, and only this function knows which one
 * it just produced.
 */
export async function fetchMatchingCustomers({
  search, segment, sortBy, cap = CSV_ROW_CAP, onProgress,
} = {}) {
  const rows = []
  let total = 0

  for (let p = 1; p <= Math.ceil(cap / PER); p++) {
    const data = await listCustomers({
      page: p,
      per_page: PER,
      search: search || null,
      segment,
      sort_by: sortBy,
    })
    total = data.total || 0
    const batch = data.customers || []
    rows.push(...batch)
    onProgress?.(Math.min(rows.length, cap), Math.min(total, cap))
    if (batch.length === 0 || rows.length >= total) break
  }

  const capped = rows.slice(0, cap)
  return { rows: capped, total, truncated: total > capped.length }
}

/**
 * The human description of what was exported.
 *
 * Built once and used by both formats so the CSV preamble and the PDF header
 * can't drift into describing different things.
 */
export function describeScope({ search, segment, sortBy, total, exported, truncated }) {
  const filters = []
  if (segment && segment !== 'all') filters.push(`Segment: ${SEGMENT_META[segment]?.label || segment}`)
  if (search) filters.push(`Search: "${search}"`)

  return {
    filters: filters.length ? filters.join('  ·  ') : 'All customers (no filters)',
    sort: SORT_LABELS[sortBy] || sortBy,
    matched: total,
    exported,
    // Phrased as a sentence rather than a flag: this string is the only thing
    // standing between a 500-row sample and someone treating it as the list.
    coverage: truncated
      ? `Showing the top ${num(exported)} of ${num(total)} matching customers, by ${(SORT_LABELS[sortBy] || sortBy).toLowerCase()}. This is a sample, not the full list.`
      : `All ${num(exported)} matching customers.`,
    generatedAt: new Date().toLocaleString('en-KE', {
      day: 'numeric', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }),
  }
}

function filename(ext, segment) {
  const scope = segment && segment !== 'all' ? `-${segment}` : ''
  return `customers${scope}-${new Date().toISOString().split('T')[0]}.${ext}`
}

function download(blob, name) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

const COLUMNS = [
  'Name', 'Email', 'Phone', 'Location', 'Segment',
  'Total Spent (KES, incl. tax)', 'Total Orders', 'Last Order',
]

const toRow = (c) => [
  c.name,
  c.email || '',
  c.phone || '',
  c.location || '',
  SEGMENT_META[c.segment]?.label || c.segment,
  c.total_spent,
  c.total_orders,
  c.last_order_date ? c.last_order_date.split('T')[0] : 'Never',
]

// Escaping, not just quoting. A customer named O"Brien, or an address with a
// comma and a quote in it, shifts every later column on that row — and a subtly
// misaligned CSV is worse than one that fails to open, because someone will use
// it. Doubling the quote is the RFC 4180 escape.
const csvCell = (v) => '"' + String(v ?? '').replace(/"/g, '""') + '"'

export function exportCustomersCSV({ rows, scope, segment }) {
  const line = (cells) => cells.map(csvCell).join(',')

  const out = [
    line(['Shop Zetu — Customer List']),
    line(['Filters', scope.filters]),
    line(['Sorted by', scope.sort]),
    line(['Coverage', scope.coverage]),
    line(['Generated', scope.generatedAt]),
    '',
    line(COLUMNS),
    ...rows.map((c) => line(toRow(c))),
  ]

  // BOM so Excel reads it as UTF-8. Without it Excel assumes the system
  // codepage and mangles every accented name on open.
  const csv = '﻿' + out.join('\r\n')
  download(new Blob([csv], { type: 'text/csv;charset=utf-8' }), filename('csv', segment))
}

export async function exportCustomersPDF({ rows, scope, segment }) {
  const { jsPDF } = await import('jspdf')
  const mod = await import('jspdf-autotable')

  // jspdf-autotable 3.x ships CJS with no "import" condition, so WHICH of these
  // holds the callable depends on who is doing the interop: Vite hands the
  // function back as `default`, Node's CJS bridge nests it one level deeper.
  // Pick the one that is actually a function rather than assuming a shape —
  // guessing wrong throws "autoTable is not a function" at click time, which is
  // the one moment nobody is watching a console.
  const autoTable = [mod.default?.default, mod.default, mod.autoTable, mod]
    .find((f) => typeof f === 'function')
  if (!autoTable) throw new Error('jspdf-autotable failed to load')

  const doc = new jsPDF({ unit: 'pt', format: 'a4', orientation: 'landscape' })
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const mx = 32

  doc.setFont('helvetica', 'bold'); doc.setFontSize(18); doc.setTextColor(...DARK)
  doc.text('Shop Zetu', mx, 44)
  doc.setFont('helvetica', 'normal'); doc.setFontSize(11); doc.setTextColor(...BRAND)
  doc.text('Customer List', mx, 61)

  doc.setFontSize(8.5); doc.setTextColor(...MUTE)
  doc.text(`${scope.filters}    ·    Sorted by: ${scope.sort}    ·    Generated: ${scope.generatedAt}`, mx, 77)

  // The coverage line gets its own weight. When this is a 500-row sample of
  // 162,000, that fact has to survive being skim-read by someone who only
  // looks at the table.
  doc.setFont('helvetica', 'bold'); doc.setFontSize(9); doc.setTextColor(...DARK)
  doc.text(scope.coverage, mx, 93)

  doc.setDrawColor(...BRAND); doc.setLineWidth(1.5); doc.line(mx, 101, pageW - mx, 101)

  // Segment mix, counted over the rows actually in this document rather than
  // the whole result set — a mix quoted from 162,000 customers above a table of
  // the top 500 by spend would describe a population the reader cannot see.
  const mix = rows.reduce((acc, c) => {
    const k = SEGMENT_META[c.segment]?.label || c.segment || 'Unknown'
    acc[k] = (acc[k] || 0) + 1
    return acc
  }, {})
  const mixRows = Object.entries(mix).sort((a, b) => b[1] - a[1])

  let y = 121
  doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(...DARK)
  doc.text(`Segment mix of these ${num(rows.length)}`, mx, y)
  autoTable(doc, {
    startY: y + 8,
    head: [['Segment', 'Customers', 'Share']],
    body: mixRows.map(([k, v]) => [k, num(v), `${((v / (rows.length || 1)) * 100).toFixed(1)}%`]),
    margin: { left: mx, right: mx },
    // 'wrap', not a fixed width: pinned to 320pt this table needed ~393 for
    // "Never Bought" and squeezed its columns, which autoTable reports only as
    // a console warning nobody sees.
    tableWidth: 'wrap',
    styles: { fontSize: 8.5, cellPadding: 4, textColor: DARK, lineColor: [235, 235, 235], lineWidth: 0.5 },
    headStyles: { fillColor: BRAND, textColor: [255, 255, 255], fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [249, 249, 251] },
    theme: 'striped',
  })

  y = doc.lastAutoTable.finalY + 24
  doc.setFont('helvetica', 'bold'); doc.setFontSize(10); doc.setTextColor(...DARK)
  doc.text('Customers', mx, y)
  autoTable(doc, {
    startY: y + 8,
    head: [COLUMNS],
    body: rows.map((c) => {
      const r = toRow(c)
      r[5] = num(Math.round(c.total_spent || 0))   // thousands separators in print
      return r
    }),
    margin: { left: mx, right: mx },
    styles: { fontSize: 7.5, cellPadding: 3.5, textColor: DARK, lineColor: [235, 235, 235], lineWidth: 0.5, overflow: 'ellipsize' },
    headStyles: { fillColor: BRAND, textColor: [255, 255, 255], fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [249, 249, 251] },
    theme: 'striped',
    // Name and Email are deliberately left auto. They are the two
    // variable-length fields, so they should absorb whatever width the fixed
    // columns don't use. Pinning all eight also means no column can take up the
    // slack, and autoTable squeezes and warns rather than filling the page.
    columnStyles: {
      2: { cellWidth: 80 },                     // Phone
      3: { cellWidth: 90 },                     // Location
      4: { cellWidth: 70 },                     // Segment
      5: { cellWidth: 90, halign: 'right' },    // Spent
      6: { cellWidth: 50, halign: 'right' },    // Orders
      7: { cellWidth: 65 },                     // Last order
    },
  })

  const pages = doc.internal.getNumberOfPages()
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i)
    doc.setFontSize(7.5); doc.setTextColor(...MUTE)
    doc.text('Shop Zetu · Confidential · Contains customer personal data', mx, pageH - 16)
    doc.text(`Page ${i} of ${pages}`, pageW - mx, pageH - 16, { align: 'right' })
  }

  doc.save(filename('pdf', segment))
}
