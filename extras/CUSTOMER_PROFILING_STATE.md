# Customer Profiling — where the page stands

Written 12 August 2026, after a long run of changes. This is the orientation
document: what is on the page, where each number comes from, what is finished,
what is half-done, and what is known to be wrong.

---

## The one-paragraph version

The page is in good shape **except for its sales figures**. Everything about
customers — counts, segments, spend, the table, the exports — reads from our own
mirror of Shopify's transactional data and is trustworthy. Everything about
**sales** (Total sales, its breakdown, the revenue chart) currently comes from
Shopify's *analytics* layer, which we have now measured to be missing orders in
every single month. That part is mid-replacement. Nothing is broken on screen;
one chart was quietly wrong and has been contained.

---

## What is on the page, top to bottom

| # | Section | Where its numbers come from | State |
|---|---|---|---|
| 1 | Header — sync status, stale banner, Sync Now / Cancel | `customers_cache` timestamps | Done |
| 2 | **Export** button — CSV or PDF | `customers_cache` | Done |
| 3 | KPI: **Revenue** | `customers_cache` — sum of Shopify's per-customer "Total spent" | Done |
| 4 | KPI: **Total sales** | **ShopifyQL** (`read_reports`) | Being replaced |
| 5 | KPI: Total customers / Came back for more / New in 30 days | `customers_cache` | Done |
| 6 | **How Total sales is calculated** (7-row breakdown) | **ShopifyQL** | Being replaced |
| 7 | Segments + AOV trend chart | `customers_cache` for segments; **ShopifyQL** for the revenue series and the header line | Mixed |
| 8 | Segment trends (`CustomerTrends`) | `customers_cache` | Done |
| 9 | Top Spenders / Most Frequent Buyers | `customers_cache` | Done |
| 10 | Customer table — search, sort, filter, pagination | `customers_cache` | Done |
| 11 | Customer AI chat | conversation data | Out of scope of this audit |

**The rule of thumb:** if it counts *customers*, it is solid. If it counts
*money at the store level*, it is mid-migration.

---

## The thing that changed everything

Finance (Maureen) kept reporting that orders were missing from the figures she
pulls out of Shopify's **Reports**, compared with what the tech team sees in the
API. We tested it rather than taking it on faith, comparing Shopify's own
monthly order counts against our transactional mirror across 52 complete months:

```
ShopifyQL LOWER than the transactional API : 52 months
ShopifyQL HIGHER                           :  0 months
exactly equal                              :  0 months
```

Between 5 and 35 orders short **every single month** — never once higher, about
665 orders in total. That is systematic, not noise.

`read_reports` is the permission that reads that analytics layer, so any figure
we take through it inherits the same shortfall. That is why Total sales, its
breakdown, and the revenue chart are being moved onto figures computed from the
transactional orders instead.

**A caveat we have not yet closed:** a one-directional shortfall is also what you
would see if Shopify *correctly* excludes orders we include — test orders and
cancelled ones. Finance's complaint is about real orders, which that theory does
not explain, but it has not been proven either way. The `is_test` and
`cancelled_at` columns added in Step 37 answer it directly once the order sync
finishes.

---

## A second, separate defect — already contained

The revenue chart at **Daily** granularity was plotting 1,000 of 1,617 days.
ShopifyQL caps a response at 1,000 rows and does not say when it truncates, and
because the rows come back unordered and we sort them, the missing 617 days were
scattered through the range rather than falling off one end. The chart looked
continuous while omitting 38% of its days and KES 91.9M of revenue.

This one was ours, not Shopify's. The daily window is now clamped to 900 days,
which keeps it under the cap. Weekly and monthly were never affected.

---

## Numbers you can rely on, and numbers you cannot

**Rely on:**
- Customer counts, segments, retention, new-in-30-days
- Per-customer spend and order history (straight from Shopify's own per-customer
  totals, not recalculated by us)
- The customer table, its filters, and both exports
- Returns totals — cross-checked two ways: our 216.3M of returned goods against
  633.5M gross is a ~30% return rate, and Shopify's own Returns line independently
  says ~29.7%

**Do not rely on yet:**
- Total sales and its 7-row breakdown — real Shopify figures, but from the layer
  that under-counts
- The revenue chart's totals line — same source
- `amount_refunded` / `total_refunded` — see Step 40 below; being corrected to
  read NULL ("unknown") instead of a false zero
- Any ex-VAT figure — still divides by a hardcoded 1.16, which is wrong for
  anything zero-rated or exempt. Fix is unblocked but not yet done.

---

## Where the migration has got to

Steps refer to `database/PRODUCTION_CHANGES.md`.

| Step | What | Status |
|---|---|---|
| 37 | Add sales-component columns to `orders_cache` | **SQL run on production** |
| 38 | Create `refunds_cache`, one row per refund with its own date | **SQL run on production** |
| 39 | Clear the orders watermark to force a full backfill | **SQL run on production** |
| — | Full order re-sync | **Running** |
| 40 | Correct refunded-amount zeros to NULL | Written; **deploy code, then run SQL** |
| — | Compute the sales breakdown ourselves | Not started |
| — | Reconcile computed vs ShopifyQL, then retire `read_reports` | Not started |
| — | Replace the 1.16 VAT divisor with real per-order tax | Not started (unblocked by Step 37) |

**Why refunds needed their own table:** Shopify attributes a return to the date
the *refund* was processed, not the date of the order. An order placed in March
and refunded in May reduces **May**. A single per-order total summed by order
date pushes that money into March — and because the annual total still comes out
right, nothing would flag it except finance, who read the months.

---

## Immediate next actions, in order

1. **Let the running order backfill finish.** Deploying now restarts the service
   and interrupts it. It would resume from a cursor, but there is no reason to.
2. **Deploy** the refund-amount fix.
3. **Run Step 40 SQL.**
4. **Answer the open question** — are the ~665 orders Shopify omits test/cancelled
   orders, or ordinary paid ones? One query, and it decides whether we replicate
   Shopify's exclusions or have proof that Reports drops revenue.
5. Then build the computed breakdown and reconcile it before anything is switched
   over on screen.

---

## Also worth knowing

- **The orders sync had not run since 2 July** — six weeks. The watermark was
  stuck, which is why our order count sat 1,723 below Shopify's. The backfill
  fixes the data; it does not explain the stall, and the stall will recur if
  whatever caused it is still there. Unexamined.
- **Three latent crashes found elsewhere** by static analysis, all pre-existing:
  `logs.py` (three sites), `ai_settings.py`, `automation.py`. The `logs.py` ones
  sit inside `except` blocks, so they replace a real error with a confusing one
  at exactly the wrong moment. Not fixed — outside this page.
- **Segment colours** were rebuilt to pass contrast and colour-blindness checks
  in both light and dark themes, and the definition now lives in one file
  (`utils/segments.js`) instead of being duplicated in three that had drifted.
