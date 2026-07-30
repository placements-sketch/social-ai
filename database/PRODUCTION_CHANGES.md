# Production database changes

A running record of the SQL to run against **production** (Supabase), grouped
by the frontend page the work belonged to. Kept because the review is
happening page by page, so production is touched once per page rather than
after every commit.

There is no `migrations/` directory in this project, so schema changes ship as
SQL here.

## Rules for this file

1. **Step numbers are permanent.** Once a step has a number it keeps it
   forever, even if it's later found to be wrong or gets superseded.
2. **New work is APPENDED at the bottom** with the next unused number. This
   file is never reordered or renumbered — you may be part-way through it, and
   moving the goalposts destroys the only thing a checklist is for.
3. **Everything is safe to re-run.** `IF NOT EXISTS` on the DDL, and
   `WHERE ... IS NULL` / `IS DISTINCT FROM` guards on the backfills, so
   anything already applied matches zero rows the second time.

Paste into the Supabase SQL editor. Deploy the code first; every change is
additive, so the running code keeps working against the new columns.

---

## Just want to get it done?

Open **[`dashboard-all-steps.sql`](dashboard-all-steps.sql)**, paste the whole
thing into the Supabase SQL editor, run it. That's steps 2–6 in the right
order, in one block.

It doesn't matter what you've already run. Every statement is guarded, so
anything applied before matches zero rows the second time. Verified: running
the whole file against an already-migrated database changed **0 rows on every
statement**.

The step-by-step version below exists if you want to know what each part does.

---

## "Which steps have I already run?"

**Don't rely on memory — ask the database.** These two queries report the state
of every SQL step in this file. Run A first; run B only if A returns all 1s.

```sql
-- A. Do the columns exist? (safe to run at any time)
SELECT
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name='conversations' AND column_name='escalated_at')            AS step2_escalated_at,
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name='conversations' AND column_name='ai_disabled_at')          AS step2_ai_disabled_at,
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name='messages'      AND column_name='ai_eligible')             AS pre_existing_ai_eligible,
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name='conversion_attributions' AND column_name='order_tax')     AS step5_order_tax;
```

```sql
-- B. Has the backfill work been done? (only valid once A returns all 1s)
SELECT
  (SELECT count(*) FROM conversations WHERE escalated_at IS NOT NULL)           AS step3_rows_filled,
  (SELECT count(*) FROM messages m WHERE m.direction='inbound'
     AND m.ai_eligible IS DISTINCT FROM true
     AND EXISTS (SELECT 1 FROM messages r WHERE r.conversation_id=m.conversation_id
                 AND r.direction='outbound' AND r.sender='ai'
                 AND r.created_at >= m.created_at))                             AS step4_still_todo,
  (SELECT count(*) FROM messages
    WHERE direction='inbound' AND ai_eligible IS NULL)                          AS step4_nulls_left,
  (SELECT count(*) FROM logs
    WHERE source='services.inbound' AND conversation_id IS NULL)                AS step6_still_todo,
  (SELECT count(*) FROM conversion_attributions)                                AS step10_rows;
```

How to read B:

| Column | Meaning |
| --- | --- |
| `step3_rows_filled` | 0 with escalations present → step 3 hasn't run |
| `step4_still_todo` | **must be 0.** Anything above 0 → step 4 hasn't run (or didn't finish) |
| `step4_nulls_left` | **must be 0** after step 4 |
| `step6_still_todo` | 0 → step 6 done. Non-zero is harmless, just unclickable feed rows |
| `step10_rows` | 0 → the attribution job still isn't scheduled (step 10) |

Local dev returns `A = (1,1,1,1)` and `B = (7, 0, 0, 0, 0)` — everything
applied except step 10, which is a scheduling task rather than SQL.

If you're unsure where you left off: run A, then B, then just re-run every SQL
step from the top. Re-running is a no-op.

---

## Dashboard page

Steps 1–11. These numbers are now fixed and will not change; anything found
later gets appended below as step 12 onward.

- **SQL to run:** 2, 3, 4, 5, 6
- **Read-only checks:** 1, 7, 8
- **Not SQL** (scheduling / deploy): 9, 10, 11

Run the SQL steps in numeric order — later ones read columns earlier ones
create.

### Step 1 — Where is production right now?


Safe to run at any time. Tells you which of the steps below have already been
applied, so you can skip or repeat with confidence.

```sql
SELECT
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name = 'conversations' AND column_name = 'escalated_at')   AS has_escalated_at,
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name = 'conversations' AND column_name = 'ai_disabled_at') AS has_ai_disabled_at,
  (SELECT count(*) FROM information_schema.columns
    WHERE table_name = 'messages'      AND column_name = 'ai_eligible')    AS has_ai_eligible;
```

How to read it:

| Result | Meaning |
| --- | --- |
| `has_escalated_at` / `has_ai_disabled_at` = 1 | Step 2 already done — running it again is harmless |
| either = 0 | Step 2 has not run yet |
| `has_ai_eligible` = 0 | **Stop.** That column predates this work and needs separate handling — tell me |

### Step 2 — Add the escalation timestamp columns


```sql
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS escalated_at   TIMESTAMP;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_disabled_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_conversations_escalated_at
  ON conversations (escalated_at);
CREATE INDEX IF NOT EXISTS ix_conversations_ai_disabled_at
  ON conversations (ai_disabled_at);
```

| column | meaning |
| --- | --- |
| `escalated_at` | when the AI last handed off to a human |
| `ai_disabled_at` | when a human last switched the AI off |

Plain `TIMESTAMP` (no timezone) on purpose — the app writes naive UTC
everywhere, and the analytics layer converts to local time itself.

**Why:** "Escalated" on the Dashboard used to count conversations whose
*last message* fell in the window and which carried a `handoff_reason`. That
counted state rather than events, so one June escalation recounted in every
later window the thread stayed alive in. Worse, `handoff_reason` is cleared
when an agent switches the AI back on, so re-enabling a conversation erased
its escalation entirely.

### Step 3 — Fill in the escalation timestamps


**Escalated reads these, so it shows 0 for all history until this runs.**

```sql
-- Conversations the AI escalated. Prefer the real handoff log timestamp;
-- fall back to updated_at where no log row exists.
UPDATE conversations c
SET escalated_at = COALESCE(
      (SELECT max(l.created_at)
         FROM logs l
        WHERE l.conversation_id = c.id
          AND l.source = 'handoff.triggered'),
      c.updated_at, c.last_message_at, c.created_at)
WHERE c.handoff_reason IS NOT NULL
  AND c.escalated_at IS NULL;

-- An escalation always switches the AI off, so it is the same moment.
UPDATE conversations c
SET ai_disabled_at = c.escalated_at
WHERE c.escalated_at IS NOT NULL
  AND c.ai_disabled_at IS NULL;

-- AI switched off by hand, with no escalation. No log exists for this,
-- so updated_at is the only signal available.
UPDATE conversations c
SET ai_disabled_at = COALESCE(c.updated_at, c.last_message_at, c.created_at)
WHERE c.ai_enabled = false
  AND c.handoff_reason IS NULL
  AND c.ai_disabled_at IS NULL;
```

**Known limitation.** Timestamps only come from `handoff.triggered` logs where
those rows exist; otherwise they fall back to `updated_at`. On local dev all 7
legacy escalations fell back, so their dates may be off by a day or two.
Escalations recorded from here on are exact.

### Step 4 — Repair `messages.ai_eligible`


**Must run after step 3** — the second statement reads `ai_disabled_at`.

`ai_eligible` is meant to record whether the AI was allowed to answer a
message **at the moment it arrived**. The original backfill instead derived it
from whatever `conversations.ai_enabled` and `channels.enabled` happened to
say at backfill time, so any conversation or channel switched off later had
its whole history retroactively marked ineligible — including messages the AI
verifiably answered.

That matters because Success Rate, Response Rate and every per-channel
answered rate filter on this column. On local dev, **25 inbound messages were
marked ineligible despite the AI having replied in that conversation
afterwards.**

Strongest evidence first; each statement is guarded so it cannot overwrite a
better answer:

```sql
-- 1. HARD EVIDENCE: the AI replied in this conversation at or after this
--    message, so it was demonstrably switched on at the time.
UPDATE messages m
SET ai_eligible = true
WHERE m.direction = 'inbound'
  AND m.ai_eligible IS DISTINCT FROM true
  AND EXISTS (
        SELECT 1 FROM messages r
         WHERE r.conversation_id = m.conversation_id
           AND r.direction  = 'outbound'
           AND r.sender     = 'ai'
           AND r.created_at >= m.created_at);

-- 2. HARD EVIDENCE the other way: the message arrived after the AI was
--    switched off for that conversation. Fills gaps only, never overwrites.
UPDATE messages m
SET ai_eligible = false
FROM conversations c
WHERE c.id = m.conversation_id
  AND m.direction     = 'inbound'
  AND m.ai_eligible  IS NULL
  AND c.ai_disabled_at IS NOT NULL
  AND m.created_at >= c.ai_disabled_at;

-- 3. NO EVIDENCE: fall back to the current gates. The same guess the original
--    backfill made, but now only for rows nothing better could be said about.
UPDATE messages m
SET ai_eligible = COALESCE(ch.enabled, true) AND c.ai_enabled
FROM conversations c
LEFT JOIN channels ch ON ch.channel = c.channel
WHERE c.id = m.conversation_id
  AND m.direction    = 'inbound'
  AND m.ai_eligible IS NULL;

-- 4. PUBLIC COMMENTS THE AI DELIBERATELY IGNORED. Comments are public, so the
--    AI only answers questions — it stays out of "Love this 😍". That gate
--    was never captured in the snapshot, so those comments counted as
--    conversations the AI failed to answer. Scoped hard: only comments in
--    conversations that both logged the suppression AND never got an AI
--    reply, so a genuine question is never demoted by mistake.
UPDATE messages m
SET ai_eligible = false
FROM conversations c
WHERE c.id = m.conversation_id
  AND m.direction    = 'inbound'
  AND m.channel   LIKE '%_comment'
  AND m.ai_eligible IS DISTINCT FROM false
  AND NOT EXISTS (SELECT 1 FROM messages r
                   WHERE r.conversation_id = c.id
                     AND r.direction = 'outbound' AND r.sender = 'ai')
  AND EXISTS (SELECT 1 FROM logs l
               WHERE l.conversation_id = c.id
                 AND l.source = 'services.ai_suppressed'
                 AND l.payload->>'reason' = 'not_a_question');
```

Local dev: 25 / 0 / 0 / 1 rows, moving the distribution from
`false: 44, true: 83` to `false: 20, true: 107`. Success Rate went
18.8% → 22.6%, WhatsApp and Facebook went from "AI off here" to 100%
answered, and Instagram's "never answered" dropped from 2 to 1.

**What this does not fix.** There is no history for `channels.enabled` or the
global AI master switch, so messages with no AI reply and no recorded disable
keep whatever they had — genuinely ambiguous. Locally that is 17 rows.
Snapshots taken from the deploy onwards are captured live and are exact.

### Step 5 — Add `order_tax` to attributions


Attributed revenue used to be reported by dividing every order total by a flat
1.16 VAT divisor — a guess that assumed every order was taxed at the Kenyan
rate. Shopify reports `total_tax` per order, so we now store it and compute
net revenue exactly. Rows written before this column keep the old divisor, so
historical figures don't silently change meaning.

```sql
ALTER TABLE conversion_attributions
  ADD COLUMN IF NOT EXISTS order_tax NUMERIC(12,2);
```

Nothing to backfill — the table is empty (see 6c).

### Step 6 — Link historical inbound logs to their conversations


`services.inbound` was logged before the conversation row existed, so the most
important line in Live Activity — *"a customer sent a message"* — was the one
you couldn't click through to. New rows link themselves; this fixes the old
ones by matching each log to the first inbound message saved after it.

```sql
WITH matched AS (
  SELECT DISTINCT ON (l.id) l.id AS log_id, m.conversation_id
  FROM logs l
  JOIN users u    ON u.external_id = l.payload->>'user_external_id'
  JOIN messages m ON m.user_id   = u.id
                 AND m.channel   = l.payload->>'channel'
                 AND m.direction = 'inbound'
                 AND m.created_at >= l.created_at - interval '5 seconds'
  WHERE l.source = 'services.inbound'
    AND l.conversation_id IS NULL
  ORDER BY l.id, m.created_at ASC
)
UPDATE logs l
SET conversation_id = matched.conversation_id
FROM matched
WHERE matched.log_id = l.id;
```

The message join matters: 8 users in local dev have more than one
conversation on the same channel, so matching on user + channel alone picks an
arbitrary one. `DISTINCT ON` plus the timestamp ordering pins each log to the
message it was actually about. Local dev: 74 rows linked, 0 left unlinked.

### Step 7 — Verify


```sql
SELECT
  (SELECT count(*) FROM conversations WHERE escalated_at   IS NOT NULL) AS escalated_filled,
  (SELECT count(*) FROM conversations WHERE ai_disabled_at IS NOT NULL) AS ai_off_filled,
  (SELECT count(*) FROM messages WHERE direction = 'inbound'
      AND ai_eligible = true)                                           AS eligible_true,
  (SELECT count(*) FROM messages WHERE direction = 'inbound'
      AND ai_eligible = false)                                          AS eligible_false,
  (SELECT count(*) FROM messages WHERE direction = 'inbound'
      AND ai_eligible IS NULL)                                          AS eligible_null,
  -- Should be 0 once step 4 has run. Anything above 0 means step 4 did not
  -- complete — messages the AI answered are still marked ineligible.
  (SELECT count(*) FROM messages m WHERE m.direction = 'inbound'
      AND m.ai_eligible IS DISTINCT FROM true
      AND EXISTS (SELECT 1 FROM messages r
                   WHERE r.conversation_id = m.conversation_id
                     AND r.direction = 'outbound' AND r.sender = 'ai'
                     AND r.created_at >= m.created_at))                 AS still_to_fix;
```

Local dev after all steps: `7, 11, 108, 19, 0, 0`. **`still_to_fix` and
`eligible_null` must both be 0.**

### Step 8 — Optional: see why anything went unanswered


No changes to run — this is the query behind the sheet's new "why" lines, for
when you want the detail per conversation.

```sql
SELECT l.conversation_id,
       c.channel,
       l.payload->>'reason' AS reason,
       l.payload->>'detail' AS detail,
       l.created_at
FROM logs l
JOIN conversations c ON c.id = l.conversation_id
WHERE l.source = 'services.no_reply_sent'
  AND l.created_at >= now() - interval '7 days'
ORDER BY l.created_at DESC;
```

`level = 'error'` rows are faults (`dispatch_failed`, `pipeline_exception`,
`settings_unreadable`); `info` rows are the system working as designed.
Conversations with no row at all show as **No reason recorded** in the sheet —
that means the message predates this logging, so expect all historical seed
data to look that way.

### Step 9 — Schedule the unclaimed-queue check

Nothing to run by hand — this ships as a workflow file.

`.github/workflows/unclaimed-queue.yml` is **new**, added with this work. Once
it's merged it runs itself every 15 minutes, and appears in the Actions tab as
**Unclaimed Queue Check** if you want to trigger it manually.

It alerts when a conversation sits in the human queue with nobody assigned.
Threshold is `handoff.unclaimed_alert_minutes` (Settings → Handoff &
assignment, default 15). It alerts **once per waiting spell**, not once per
tick, so the 15-minute cadence won't spam anyone.

To see the queue without waiting for an alert (supervisor/admin only):

```
GET /api/conversations/unclaimed?threshold_minutes=0
```

### Step 10 — Conversion attribution — CORRECTION

**This step originally told you to set up a scheduled call for
`/api/cron/attribute`. That was wrong — it already exists.**

`.github/workflows/daily-sync.yml` has had it all along: a `0 1 * * *`
schedule (04:00 EAT daily), a "Trigger attribution" step, and `attribute` in
the manual dropdown. Nothing to create.

What I got wrong, and why: I checked `sync_jobs` and the `cron.*` logs on the
**local dev database**, found no `attribute` rows, and concluded the job had
never run. Local dev isn't production. Run this against production to find out
what actually happened there:

```sql
-- Has the attribution job ever run in production?
SELECT kind, status, count(*), max(started_at) AS last_run
FROM sync_jobs
WHERE kind = 'attribute'
GROUP BY 1, 2;

-- And did it write anything?
SELECT count(*) AS rows, min(order_date) AS oldest, max(order_date) AS newest
FROM conversion_attributions;
```

**One real gap, now fixed.** Selecting **all** in the manual dropdown ran
products, customers and orders but *not* attribution — so a manual "run
everything" quietly skipped the only job that writes conversion data. The
workflow now includes it in `all`, after a pause so the orders sync lands
first.

**Still true regardless:** don't leave attribution paused for more than a
week. It looks back `window_days = 7` (`app/cron_routes.py`), so an order not
picked up within a week of its last update is never attributed — lost, not
delayed.

**Also note** the workflows post to `social-ai-backend-tult.onrender.com`, so
the backend is on Render. Earlier notes in this file guessed Railway; ignore
that.

### Step 11 — Not database changes


**`tzdata` dependency.** The deploy crashes without it — analytics resolves
calendar windows in the business timezone, and `zoneinfo` has no tz database
of its own on some hosts.

```
pip install -r requirements.txt      # tzdata==2026.3 was added
```

Confirm after deploy: `from zoneinfo import ZoneInfo; ZoneInfo("Africa/Nairobi")`
must not raise.

**New settings, nothing to run.** `business.timezone` (default
`Africa/Nairobi`) and `business.week_starts_on` (default `monday`) live in the
existing `app_settings` JSON row and fall back to their defaults. Worth
confirming in **Settings → Business info → Reporting** after deploy, since
they decide when "Today", "This week" and "This month" begin.

---

## Later pages

Appended as each page is finished.

---

## Appended after go-live

### Step 12 — Fix `EMAXCONNSESSION` (Shopify webhooks failing)

**Not SQL — an environment variable change plus a redeploy.** Do this one
first; it's dropping live webhook data.

Production is logging, ~70 times in half an hour:

```
shopify_webhook.handler_failed
Handler for 'products/update' failed: (psycopg2.OperationalError)
connection to server at "aws-1-us-west-2.pooler.supabase.com", port 5432
failed: FATAL: (EMAXCONNSESSION) max clients reached in session mode
```

Every one of those is a Shopify product/inventory update **thrown away**, so
the product cache silently drifts out of date.

**Cause.** `DATABASE_URL` points at the Supabase pooler on **port 5432**,
which is *session mode*: each client holds a dedicated server connection for
its entire life, so the slots run out quickly. *Transaction mode* on **port
6543** hands the connection back after every transaction and supports far
more clients.

**Fix — change the port in `DATABASE_URL` on Render:**

```
postgresql://…@aws-1-us-west-2.pooler.supabase.com:5432/postgres    ← now
postgresql://…@aws-1-us-west-2.pooler.supabase.com:6543/postgres    ← change to
```

Nothing else in the string changes. Redeploy after saving.

**Also shipped in the code** (`app/config.py`): our own pool was far too big
for session mode. The pool is per *worker process*, and the Procfile runs
2 workers × 4 threads, so the previous `pool_size=5, max_overflow=10` meant up
to **30 connections from the web dyno alone**, before cron jobs and webhook
handlers. Now `pool_size=4` (matching the thread count) and
`max_overflow=1` → **10 maximum**. Tunable via `DB_POOL_SIZE` /
`DB_MAX_OVERFLOW` if needed.

**Transaction mode caveat:** it doesn't support session-level features —
`LISTEN`/`NOTIFY`, advisory locks held across transactions, or server-side
prepared statements spanning transactions. This app uses none of them, and
psycopg2 doesn't use server-side prepared statements by default.

Verify after redeploy — this should return no rows:

```sql
SELECT created_at, left(message, 90)
FROM logs
WHERE source = 'shopify_webhook.handler_failed'
  AND created_at > now() - interval '30 minutes'
ORDER BY created_at DESC;
```
