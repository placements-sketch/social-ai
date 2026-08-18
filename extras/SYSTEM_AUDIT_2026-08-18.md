# System audit — 18 August 2026

State of the platform after the Render migration, the AI-pause rework and the
switch to the live Instagram account. Everything below was checked against the
production database, not recalled.

---

## First: a conclusion I got wrong

Earlier I told you the data backed the claim that Shopify Reports drops orders —
52 of 52 months short, "systematic, not noise". **That does not survive the
better data we now have.**

At the time we could not tell a test or cancelled order from a real one, because
those columns did not exist yet. They do now (Step 37), and the picture inverts:

```
months compared                                   52
raw gap (our count - Shopify)                    665
gap excluding test and cancelled orders      -10,130
months where Shopify is STILL lower                0
```

Once test and cancelled orders are excluded, **Shopify is not lower in a single
month.** The 665-order gap was us counting 11,300 cancelled and 15 test orders
that Shopify correctly leaves out of sales. Shopify's figures are defensible.

What this changes:

- **Do not rebuild sales figures on the premise that Reports is broken.** The
  premise is not supported.
- Finance's complaint may still be real, but it is not "the sales dataset is
  systematically short on orders". Worth asking Maureen for one specific missing
  order number — a single example is now checkable in seconds against
  `orders_cache`.
- The other reasons to compute sales ourselves still stand on their own:
  ShopifyQL's 1,000-row cap, rate limiting, six-hour cache staleness, and the
  inability to join to our own customer data. Those are robustness arguments,
  not correctness ones.

The lesson worth keeping: a one-directional gap across every month looked like
proof, and I called it proof. It was an artefact of a filter we could not apply
yet.

---

## Confirmed working

Checked live, not assumed.

| | Evidence |
|---|---|
| Database on Render | app writing to it; Supabase last written 17 Aug |
| Step 37/38 data | 133,085 orders — **all** with `total_tax` and `gross_sales`; 51,988 refunds, all with `goods_subtotal` |
| Silent-conversation watchdog | `cron.check_silent` running, last 11:49; `handoff.silent` fired 13 alerts |
| Unanswered backlog | **0** conversations waiting — the 13 that sat 7-18 days are cleared |
| Shadow mode | `services.dispatch.dry_run` — a real reply has already been held |
| Live account | shopzetu active and webhook-subscribed; mileszetu disconnected |
| Customer search | 4.2s → ~300ms; "mbugua pat" now finds Pat Mbugua |
| Delivery fees | Nairobi 250, environs 350, Vivo pickup 250, other 500 |

Current runtime state: **AI master switch ON, shadow mode ON.** The assistant is
reading real customer messages and writing real replies that nobody receives.

---

## What is left, in the order I would do it

### 1. Decide when shadow mode ends — and who covers customers until then

Right now real Shop Zetu customers are messaging and **nothing is being sent to
them**. The assistant's answers are readable in the inbox, which is the point,
but every one of those conversations still needs a human reply until you switch
sending on.

The auto-routing built this week fires on the **master switch**, not shadow mode,
so these conversations are not being pushed to the Unclaimed queue. The watchdog
will catch them after 24 hours, but that is a backstop, not a workflow.

**Decide:** either agents actively work the inbox during the test, or shadow mode
should also route to agents. The second is a small change if you want it.

### 2. Two deadlines you cannot miss

- **The Render Postgres free instance is deleted after ~30 days.** Connected 17
  August, so around **16 September**. The previous one was already lost this way.
  Either move to the paid tier (~$7/mo, which also removes the 1 GB ceiling) or
  diarise a migration.
- **Supabase**, kept as rollback since 17 August. After about a week the two have
  diverged far enough that rolling back would lose real data. Decide by **24
  August** whether to delete it or keep paying attention to it.

### 3. Data the assistant still gets wrong

- **`ex_vat()` divides by a hardcoded 1.16** in 10 places. This is now trivially
  fixable and was not before: every order has a real `total_tax`. The divisor is
  wrong for anything zero-rated or exempt.
- **The returns policy contradicts the delivery zones.** The policy says returns
  are accepted from "Kenya, Uganda, Rwanda and rest of world"; there is no
  international delivery zone any more. Asked about Kampala the assistant will
  say it cannot deliver there and can accept a return from there.
- **Seven towns have no zone** — Kiserian, Kiambu, Thika, Kikuyu, Limuru,
  Kitengela, Athi River. They now fall to "Other towns" at KES 500, which nobody
  has confirmed is right.

### 4. Permissions worth requesting

- **`human_agent`** via Meta App Review. Without it your reply window is 24 hours;
  with it, 7 days. The tag is already implemented and only used once the 24-hour
  window has closed, so approving it can only help and cannot break current sends.
- **shopzetu granted 3 scopes** where mileszetu had 5 — missing
  `content_publish` and `manage_insights`. Neither is needed for messaging, but
  anything insights-related will come back empty.

### 5. Reconsider, given the correction above

- **Retiring `read_reports`** was justified to me on correctness grounds that no
  longer hold. The robustness reasons remain, but this is now a "nice to have",
  not a fix. I would not spend the effort yet.
- **The daily chart is still clamped to 900 days** to dodge ShopifyQL's 1,000-row
  cap. That containment is still correct and still needed.

### 6. Never audited

The **Customer Detail page** (`CustomerDetail.jsx`, ~685 lines) and
`CustomerProfileExtras.jsx` are the largest surfaces never reviewed against the
"every section must have a purpose and correct data" standard. The page-by-page
audit stopped at Customer Profiling.

---

## Housekeeping

- `schema.sql`, `fk_restore.sql`, `fk_drop.sql` are migration leftovers in the
  project root — safe to delete.
- Render inherited Supabase's `auth`, `storage`, `realtime`, `vault` and
  `graphql` schemas from the schema dump. Harmless (the app only uses `public`)
  but it is clutter that could be dropped.
- `silent_alert_hours` is not stored in settings, so the watchdog uses the 24-hour
  code default. Fine, but it means the Settings field shows a value that is not
  actually persisted until someone saves the form.
- `VACUUM (ANALYZE)` on the big tables has not been run since the migration.
