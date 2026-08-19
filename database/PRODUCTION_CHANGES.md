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

---

### Step 13 — Make inbox search cover message bodies

**Why.** Inbox search only looked at `conversations.last_message`, the customer
name and the handle. Anything said in the middle of a thread was unfindable —
searching "refund" returned a conversation only if "refund" happened to be the
most recent line in it. On the local database the difference is stark:

| Search term | Matched before | Matches now |
|---|---|---|
| refund   | 1 | 8  |
| dress    | 4 | 14 |
| delivery | 3 | 6  |
| size     | 2 | 4  |

The application change (a correlated `EXISTS` over `messages.content`) ships
with the deploy and needs no SQL. This step is purely about speed.

**What this does.** `ILIKE '%term%'` cannot use an ordinary B-tree index, so
without this the database reads every message row on every search. `pg_trgm`
provides a trigram GIN index, which Postgres *can* use for a leading-wildcard
match. Verified locally: the planner switches from a sequential scan to a
`Bitmap Index Scan on idx_messages_content_trgm`.

Safe to re-run — both statements are `IF NOT EXISTS`.

```sql
-- Trigram matching, so ILIKE '%term%' can use an index.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Index for searching message bodies from the inbox search box.
CREATE INDEX IF NOT EXISTS idx_messages_content_trgm
    ON messages USING gin (content gin_trgm_ops);
```

**Run the block above. That is the whole step.**

Building the index takes a brief table lock. On a table this size that is
under a second, so there is nothing to work around.

> **Do not use `CREATE INDEX CONCURRENTLY` here.** It exists to avoid locking a
> large, busy table for minutes, which is not the situation. More practically,
> the Supabase SQL editor runs what you paste inside a transaction, and
> `CONCURRENTLY` is one of the few statements Postgres refuses to run inside
> one — it would fail with *"CREATE INDEX CONCURRENTLY cannot run inside a
> transaction block"*. Noted here only so the option doesn't look like an
> oversight.

**Verify.** The index exists and is being used:

```sql
SELECT indexname FROM pg_indexes WHERE indexname = 'idx_messages_content_trgm';

EXPLAIN
SELECT 1 FROM messages WHERE content ILIKE '%refund%';
```

On a small table Postgres may still prefer a sequential scan — that is correct
behaviour, not a failure. The index earns its keep as the table grows.

---

### Step 14 — Remove conversations we accidentally had with ourselves

**Why.** Agents reply to Instagram comments straight from the Instagram app.
Those replies come back down our webhook in exactly the same shape as a
customer's comment — same fields, our own account as the sender — so they were
ingested as inbound customer messages. The inbox ended up holding a
conversation whose "customer" is our own handle.

The clutter is the small part. The AI treats those messages as questions to
answer, so an agent's reply ending in a question mark ("...want me to check
your size?") would have been answered by the AI, publicly, under our own post.
And because the AI's own comment replies arrive back through the same webhook,
each answer produces another event to answer — a loop, in public, under our
brand.

The code fix ships with the deploy: `_authored_by_us()` in `app/services.py`
now drops these before anything is saved, checked once at the pipeline entry
rather than at each of the four webhook routes. This step only cleans up the
rows already created.

**First, look at what you have.** Do not skip this — it tells you whether the
env vars on Render even match the account you are connected to.

```sql
-- What does the system think "we" are?
SELECT page_id, ig_business_account_id, ig_username, page_name, is_active
FROM meta_connections;

-- Conversations whose "customer" is actually us.
SELECT c.id, c.channel, u.name, u.external_id, c.last_message_at,
       (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS msgs
FROM conversations c
JOIN users u ON u.id = c.user_id
WHERE u.external_id IN (
        SELECT ig_business_account_id FROM meta_connections WHERE ig_business_account_id IS NOT NULL
        UNION SELECT page_id FROM meta_connections
      )
   OR lower(u.name) IN (
        SELECT lower(ig_username) FROM meta_connections WHERE ig_username IS NOT NULL
      )
ORDER BY c.last_message_at DESC;
```

If that returns nothing but you can see the problem in the inbox, the account
id in `meta_connections` does not match the account actually posting — check
the `IG_BUSINESS_ACCOUNT_ID` environment variable on Render against the
`ig_business_account_id` column above. Add the offending handle by name to the
`lower(u.name) IN (...)` list below rather than guessing.

**Then delete.** Two separate runs. Do not paste them together.

The Supabase SQL editor executes everything you give it, so a `COMMIT` at the
bottom of a script commits before you have read anything above it — "inspect the
count, then commit" only works in an interactive psql session. So the counting
happens in run 1, on its own, and run 2 does the deleting.

There is no temp table here either. The earlier version used one, which made
Supabase warn about row-level security — a false positive (a `TEMP` table is
session-scoped and no PostgREST client can reach it), but the warning is
avoidable and the subquery is clear enough repeated.

**Run 1 — how many, and which.** Read the output before going further.

```sql
SELECT c.id, c.channel, u.name AS customer, u.external_id, c.last_message_at,
       (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS msgs
FROM conversations c
JOIN users u ON u.id = c.user_id
WHERE u.external_id IN (
        SELECT ig_business_account_id FROM meta_connections WHERE ig_business_account_id IS NOT NULL
        UNION SELECT page_id FROM meta_connections
      )
   OR lower(u.name) IN (
        SELECT lower(ig_username) FROM meta_connections WHERE ig_username IS NOT NULL
      )
ORDER BY c.last_message_at DESC;
```

Every row here is a conversation whose "customer" is our own account. If a row
looks like a real customer, **stop** — the identity in `meta_connections` is
wrong and deleting would remove genuine conversations.

**If run 1 returns no rows but you can see the problem in the inbox**, do not
run the delete — it would match nothing. The identity is not where this query is
looking. `meta_connections` is populated by the Instagram OAuth flow; a
deployment still running on the `IG_BUSINESS_ACCOUNT_ID` environment variable
will have that table empty.

Note this does NOT mean the code fix is broken. `_authored_by_us()` reads the
OAuth table *and* the environment variables, so it works either way. Only this
cleanup query is narrower, because the SQL editor cannot read env vars.

Find the rows by the handle you can see in the inbox instead:

```sql
-- Is the OAuth table populated at all?
SELECT count(*) AS rows,
       count(ig_business_account_id) AS with_ig_id,
       count(ig_username) AS with_username
FROM meta_connections;

-- Find it by handle. Replace shopzetu if your account name differs.
SELECT c.id, c.channel, u.name AS customer, u.external_id, c.last_message_at,
       (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS msgs
FROM conversations c
JOIN users u ON u.id = c.user_id
WHERE lower(u.name) LIKE '%shopzetu%'
ORDER BY c.last_message_at DESC;
```

Compare the `external_id` that comes back with `IG_BUSINESS_ACCOUNT_ID` on
Render. If they match, the env var is correct and the guard will work; the
cleanup below just needs the ids passed in directly:

```sql
-- Delete by explicit id. Substitute the ids from the query above, and only
-- those you have confirmed are our own account.
BEGIN;
DELETE FROM conversation_reads WHERE conversation_id IN (00, 00);
DELETE FROM messages          WHERE conversation_id IN (00, 00);
DELETE FROM conversations     WHERE id             IN (00, 00);
COMMIT;
```

If they do NOT match, the env var points at the wrong account — fix that on
Render before relying on the guard, because it is one of the two sources
`_authored_by_us()` trusts.

**Run 2 — delete them.** Only after run 1 looked right.

Messages before conversations: `messages.conversation_id` is `NOT NULL`, so the
other order fails on the foreign key. The whole thing is one transaction, so a
failure part-way leaves nothing half-deleted.

```sql
BEGIN;

DELETE FROM conversation_reads
WHERE conversation_id IN (
    SELECT c.id FROM conversations c JOIN users u ON u.id = c.user_id
    WHERE u.external_id IN (
            SELECT ig_business_account_id FROM meta_connections WHERE ig_business_account_id IS NOT NULL
            UNION SELECT page_id FROM meta_connections)
       OR lower(u.name) IN (
            SELECT lower(ig_username) FROM meta_connections WHERE ig_username IS NOT NULL));

DELETE FROM messages
WHERE conversation_id IN (
    SELECT c.id FROM conversations c JOIN users u ON u.id = c.user_id
    WHERE u.external_id IN (
            SELECT ig_business_account_id FROM meta_connections WHERE ig_business_account_id IS NOT NULL
            UNION SELECT page_id FROM meta_connections)
       OR lower(u.name) IN (
            SELECT lower(ig_username) FROM meta_connections WHERE ig_username IS NOT NULL));

DELETE FROM conversations
WHERE id IN (
    SELECT c.id FROM conversations c JOIN users u ON u.id = c.user_id
    WHERE u.external_id IN (
            SELECT ig_business_account_id FROM meta_connections WHERE ig_business_account_id IS NOT NULL
            UNION SELECT page_id FROM meta_connections)
       OR lower(u.name) IN (
            SELECT lower(ig_username) FROM meta_connections WHERE ig_username IS NOT NULL));

COMMIT;
```

Repeating the subquery is safe: it reads `conversations` and `users`, and
nothing before the final statement modifies either.

The `users` rows for our own account are left in place deliberately. They are
harmless once their conversations are gone, and deleting them would break the
foreign key from any message elsewhere that happens to reference them.

**Verify.** Re-run the second query from the "look first" block — it should
return no rows. And after the deploy, these should start appearing whenever an
agent replies from the Instagram app:

```sql
SELECT created_at, message, payload
FROM logs
WHERE source = 'services.no_reply_sent'
  AND payload->>'reason' = 'authored_by_us'
ORDER BY created_at DESC
LIMIT 20;
```

---

### Step 14b — Set the account identity (required for the self-reply guard)

**Context that changes what "us" means.** Production is deliberately connected
to a **dummy Instagram account that stands in for Shop Zetu**, so the whole
pipeline can be exercised without replying to real customers. Comments written
by the *real* shopzetu team therefore arrive as if they were from a third party.

Two accounts must both count as "us":

| Account | Role | Identified by |
|---|---|---|
| The connected dummy | The business this platform posts as | `IG_BUSINESS_ACCOUNT_ID` |
| The real `shopzetu` | Where agents actually reply from | `OUR_ACCOUNT_IDS` / `OUR_ACCOUNT_HANDLES` |

**Do NOT change `IG_BUSINESS_ACCOUNT_ID`.** It is not just a label for the
guard — `app/integrations/meta_poller.py` uses it to decide which participant in
a DM thread is the business and which is the customer, and `app/meta_test.py`
validates it against the account actually linked to the Page. Repointing it at
the real shopzetu id would misidentify the sender of every polled DM.

Found on production by running Step 14's diagnostic:

- `meta_connections` is **empty** (no OAuth completed — deliberate).
- The self-conversation's `external_id` is **`17841412308701394`**, username
  `shopzetu` — the real account.
- `IG_BUSINESS_ACCOUNT_ID` holds a different id — the dummy. Correct, leave it.

So the guard knew about the dummy and nothing about the real account, which is
why our own comments came through.

**Fix — ADD these on Render, changing nothing that already exists:**

```
OUR_ACCOUNT_IDS=17841412308701394
OUR_ACCOUNT_HANDLES=shopzetu
```

Both accept comma-separated lists. The handle is the durable one: Instagram
sends `from.username` on every comment event, and a business can always state
its own @handle even when nobody can produce the 17-digit id. The id is the
precise one. Either alone is enough; together they survive the other being
wrong.

Handle matching is exact after stripping a leading `@`, so `shopzetu` does not
match `shopzetu_test` — the dummy keeps its own identity.

**Verify after redeploy** — reply to a comment from the Instagram app, then:

```sql
SELECT created_at, message, payload
FROM logs
WHERE source = 'services.no_reply_sent'
  AND payload->>'reason' = 'authored_by_us'
ORDER BY created_at DESC LIMIT 5;
```

A row means the guard recognised us. No row means the identity is still wrong.

---

### Step 14c — Delete the one conversation already created

Run 1 of Step 14 found exactly one, because `meta_connections` is empty and the
generic query could not match. By explicit id:

```sql
-- Confirm it is the right row before deleting.
SELECT c.id, u.name AS customer, u.external_id, c.channel,
       (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS msgs
FROM conversations c JOIN users u ON u.id = c.user_id
WHERE c.id = 58;
```

Expect: `shopzetu`, `17841412308701394`, `instagram_comment`, 2 messages. If it
shows anything else, stop — the id has moved.

```sql
BEGIN;
DELETE FROM conversation_reads WHERE conversation_id = 58;
DELETE FROM messages          WHERE conversation_id = 58;
DELETE FROM conversations     WHERE id             = 58;
COMMIT;
```

Do this **after** Step 14b and the redeploy — otherwise the next comment an
agent writes from the Instagram app simply recreates it.

---

### Step 15 — Make the global AI kill switch reversible

> ## ⚠ RUN THIS BEFORE DEPLOYING THE CODE
>
> This is the only step so far that the application **requires**. Steps 13 and
> 14 are optional improvements; this one adds a column the `Conversation` model
> declares, and SQLAlchemy selects every declared column on every query.
>
> Deploy the code without this and **every endpoint touching conversations
> returns 500** — the inbox, the counts, analytics, alerts and channels all at
> once — with `psycopg2.errors.UndefinedColumn: column
> conversations.ai_auto_paused_at does not exist` in the Render logs and
> `Unexpected token '<'` in the browser console (that is Render's HTML error
> page arriving where JSON was expected).
>
> If that has already happened, run the SQL below. No restart is needed; the
> next request picks it up.
>
> **General rule this belongs to:** additive schema changes run *before* the
> code that uses them, never after.


**Why.** The master switch in Settings is a flag checked when a reply is about
to be sent. It never touches `conversations.ai_enabled`. So while it is off:

- every conversation the AI held still has `ai_enabled = true`, so the inbox
  goes on reporting them under **AI handling** — when nothing is handling them;
- the **Unclaimed** bucket requires `ai_enabled = false`, so those same
  conversations are not offered to agents either.

They are invisible. They do resume correctly when the switch goes back on —
the gap is only that nobody can see they are stranded meanwhile.

Two things ship with the deploy and need no SQL: the inbox now relabels that
chip **"Stalled · AI off"** with a banner, and Settings asks what to do when you
flip the switch.

This step adds the one column that makes the answer reversible.

**What the column is for.** When an admin chooses "queue them for agents", each
affected conversation is stamped with `ai_auto_paused_at`. Switching the AI back
on can then hand back **exactly that set**. Without the stamp there is no way to
distinguish a conversation an agent deliberately took over from one the master
switch happened to catch, and a restore would take threads away from the people
who claimed them.

Safe to re-run.

```sql
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS ai_auto_paused_at TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_ai_auto_paused
    ON conversations (ai_auto_paused_at);
```

**Verify.** The column exists and nothing is stamped yet:

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'conversations' AND column_name = 'ai_auto_paused_at';

SELECT count(*) AS currently_queued_by_the_switch
FROM conversations
WHERE ai_auto_paused_at IS NOT NULL;
```

The second query should return 0 until someone uses the new prompt.

**Seeing what the switch is holding right now** — this is the number the prompt
shows you, and the one that is currently stranded if the switch is off:

```sql
SELECT count(*) AS conversations_still_marked_for_the_ai
FROM conversations
WHERE status <> 'resolved' AND ai_enabled IS TRUE;
```

---

### Step 16 — One Instagram account, and retiring shopzetu

**Why.** The platform is now limited to a **single connected Instagram account**.
The code change ships with the deploy: connecting a second account is refused
with a message naming the one already connected, rather than silently replacing
it. Swapping is two deliberate steps — disconnect, then connect — because a
silent swap disconnects a live account mid-conversation and there is no undo.

Re-connecting the SAME account is still allowed; that is how an expired token
gets refreshed.

---

#### There is no database work to do

Checked on production:

```
ig_username   is_active   ig_login_expires_at        time_left
mileszetu     true        2026-09-29 10:28:10        57 days
```

**One row. shopzetu is not in `meta_connections` at all.** It was never
connected through Instagram Login — it was the old Facebook-Login/environment
setup. So there is nothing to deactivate here, and the token refresh job will
renew mileszetu automatically once it comes within 14 days of expiry.

Re-run this whenever you want to confirm the state:

```sql
SELECT ig_username, is_active, ig_login_expires_at,
       (ig_login_expires_at - now()) AS time_left
FROM meta_connections
ORDER BY id;
```

---

#### Where shopzetu actually still lives: environment variables

`_get_meta_credentials()` falls back to `FB_PAGE_ID` + `FB_ACCESS_TOKEN` when
there is no OAuth token for an account, and `send_instagram_reply()` falls back
to *that* when there is no Instagram Login token.

So while those variables are set, there is a path where a reply goes out **as
shopzetu instead of the connected account** — and it triggers exactly when
something else has already gone wrong: mileszetu disconnected, its token
lapsed, or a webhook arriving for an account with no row.

The deploy makes that visible: reaching the fallback now logs
`integrations.meta.legacy_credentials_used` at **error** level, so it reaches
the alerts panel rather than happening quietly.

**To kill shopzetu properly, clear these on Render:**

```
FB_PAGE_ID
FB_ACCESS_TOKEN
```

With those gone, a missing OAuth token fails loudly instead of posting under the
wrong brand — which is the outcome you want.

**Also update, from the earlier self-reply work:**

```
OUR_ACCOUNT_HANDLES=mileszetu      # was shopzetu
OUR_ACCOUNT_IDS=                   # clear — meta_connections now supplies this
```

`_our_account_identifiers()` reads `meta_connections` first, so mileszetu is
already recognised. Leaving `shopzetu` in there is not harmful — it just means
the guard would also ignore shopzetu's own comments — but it is stale and
misleading.

`IG_BUSINESS_ACCOUNT_ID` can stay or go. It is read by `meta_poller.py` to tell
our account from the customer in DM threads, and that module is not invoked from
anywhere in the codebase.

**Verify after clearing:** send a test DM and confirm the reply arrives from
mileszetu, then check nothing logged:

```sql
SELECT created_at, message
FROM logs
WHERE source = 'integrations.meta.legacy_credentials_used'
ORDER BY created_at DESC
LIMIT 10;
```

No rows means every reply used the connected account's own credentials.

---

#### The swap procedure, from here on

1. **Disconnect** the current account in the UI.
2. **Connect** the new one.

The other order fails with *"@mileszetu is already connected. Disconnect it
first"* — intended behaviour, not a bug.

Disconnecting deletes nothing. Reconnecting later matches on
`ig_login_user_id` and refreshes the row in place, so conversation history
survives a round trip.

**One caution for parking an account.** Instagram Login tokens expire after 60
days and the refresh job only renews tokens that are **still valid**. An
account left disconnected past its expiry cannot be reactivated — it needs a
fresh OAuth connect. Fine over days or weeks; a problem over months.

---

### Step 17 — Point urgent-notification emails at the frontend

**No SQL. One environment variable on Render.**

Urgent notifications (escalations, a channel going down, an Instagram token
about to expire) are emailed to the recipient. That email has a single button —
*Open dashboard*.

`FRONTEND_URL` is not set, and the template used to fall back to `href="#"`, so
the button did nothing when clicked. It now falls back through
`FRONTEND_URL` → `PUBLIC_BASE_URL` → `APP_BASE_URL`, and drops the button
entirely rather than rendering a dead one.

That means it currently resolves to `PUBLIC_BASE_URL`, which is the **API**
host, not the frontend. The link works but lands in the wrong place.

**On Render, set:**

```
FRONTEND_URL = https://<your-frontend-domain>
```

No trailing slash — one is stripped either way. The email deep-links to
`<FRONTEND_URL>/activity`.

Nothing breaks if you skip this; the button just points at the API host.

---

### Step 18 — Turn off the channels we cannot reply on

**Run this SQL. Then re-check Step 17 — it is probably already satisfied.**

The MVP is Instagram DMs and Instagram comments. Facebook Messenger, Facebook
comments, WhatsApp and TikTok all have **stub senders**: inbound is accepted and
stored, but `_dispatch_reply` logs "not implemented" and returns nothing. A
customer messaging one of those gets no AI reply, and an agent's reply comes
back marked *not delivered*.

The code now refuses to enable them — `PATCH /api/channels/<id>` returns 409 and
the toggle renders as unavailable — but that does not switch off a channel that
is **already** enabled in the database. This does.

```sql
-- What is on right now.
SELECT id, channel, display_name, enabled
  FROM channels
 ORDER BY id;

-- Disable everything outside the MVP.
UPDATE channels
   SET enabled = false,
       updated_at = now()
 WHERE channel NOT IN ('instagram_dm', 'instagram_comment')
   AND enabled = true
RETURNING id, channel, display_name;

-- Confirm: only the two Instagram rows should read true.
SELECT channel, display_name, enabled
  FROM channels
 ORDER BY enabled DESC, id;
```

Safe to re-run — the `AND enabled = true` means a second run updates nothing.

Nothing is deleted. Inbound history on those channels stays exactly where it is,
and re-enabling is a one-line update once a real sender is built for them.

**On Step 17 (`FRONTEND_URL`):** the urgent-email button now falls back through
`FRONTEND_URL` → `FRONTEND_BASE_URL` → `APP_BASE_URL` → `PUBLIC_BASE_URL`.
`FRONTEND_BASE_URL` is already set, so the button resolves correctly without
adding anything. Setting `FRONTEND_URL` is now optional.

**On CORS:** `CORS_ORIGINS` now falls back to `FRONTEND_BASE_URL` when unset, so
an unset variable no longer blocks the frontend. The app logs which source it
used at boot — check that line says what you expect after deploying.

---

### Step 19 — Shopify webhooks exhausting the connection pool

**No SQL. Code only — deploy and watch the logs.**

Production is logging runs of:

```
shopify_webhook.handler_failed
Handler for 'products/update' failed: QueuePool limit of size 4 overflow 1
reached, connection timed out, timeout 30.00
```

Every one is a dropped Shopify update, so the product cache drifts out of date —
the same *consequence* as Step 12, but the opposite *cause*. Step 12 was the
Supabase server refusing new connections. This is our own client-side pool
running dry.

**Two causes, both fixed.**

**1. A connection was held across a network call.**
`_handle_inventory_update` read the product, then called
`refresh_stock_for_products()` — an HTTP round trip to Shopify — while still
holding a pooled connection. This worker has five (`pool_size` 4 +
`max_overflow` 1). Shopify delivers in bursts, so the pool drained while those
connections sat idle waiting on the network.

The handler now calls `db.session.commit()` before the HTTP call, which returns
the connection to the pool; the write afterwards checks one out again.

Reproduced against the real pool — 24 concurrent webhooks, 2s Shopify latency:

| | succeeded | wall time |
|---|---|---|
| before | **15 / 24** | 6.3s |
| after | **24 / 24** | 2.1s |

The nine failures carried the exact error above.

**2. Every webhook spawned its own thread.**
`threading.Thread(...).start()` with nothing bounding it, so a bulk product edit
could put far more handlers in flight than there are connections. Replaced with
a fixed `ThreadPoolExecutor` (`SHOPIFY_WEBHOOK_WORKERS`, default 4). Excess
deliveries queue instead of timing out. Shopify still gets its 200 immediately —
20 webhooks acknowledged in 37ms in testing.

**After deploying, confirm:**

```
-- Should stop growing. Anything recent means it is not fixed.
SELECT date_trunc('hour', created_at) AS hour, count(*)
  FROM logs
 WHERE source = 'shopify_webhook.handler_failed'
   AND created_at > now() - interval '24 hours'
 GROUP BY 1 ORDER BY 1 DESC;

-- Stock should track Shopify again.
SELECT count(*) FILTER (WHERE cached_at > now() - interval '1 hour') AS fresh,
       count(*) AS total
  FROM products_cache;
```

**If it recurs**, the levers in order: raise `SHOPIFY_WEBHOOK_WORKERS` only if
handlers are queueing (they are network-bound, not connection-bound);
raise `DB_POOL_SIZE` only if normal web traffic is also timing out — and
remember Step 12, the pooler has its own ceiling.

---

### Step 20 — Instagram webhook subscription was never happening

**No SQL. Deploy, then click **Verify** on each connected account.**

Production logs:

```
auth_ig.subscribe
37355381327440609: 400 {"error":{"message":"Unsupported request - method type: post",
                       "type":"IGApiException","code":100}}
```

**What it means.** After OAuth we subscribe the account to webhook events.
That call was addressed to `me`:

```
POST https://graph.instagram.com/v23.0/me/subscribed_apps      ← rejected
POST https://graph.instagram.com/v23.0/{ig-user-id}/subscribed_apps   ← correct
```

`me` resolves on GET but is not a routable target for a POST on this edge, so
Instagram refused it and **the subscription never happened**.

**Why this matters more than it looks.** The account still finished connecting
with a perfectly valid token. A valid token with no subscription receives
*nothing* — no DMs, no comments — and from the Channels page that is
indistinguishable from a healthy connection. The card even said **Connected**,
because that badge only meant "row active, no expiry recorded" (Step 20's
sibling fix, below).

**What changed.**

- Subscribe now uses the numeric account id, falling back to `me` only if that
  fails, so a change in the other direction cannot silently break it again.
- The subscribe/check calls moved into `app/integrations/meta.py`
  (`subscribe_ig_login_webhooks`, `get_ig_login_subscriptions`) so the OAuth
  callback and the health check share one definition.
- A new **Verify** button (shield icon) on each connection asks Instagram
  directly whether the token works, **and repairs a missing subscription in
  place** — no disconnect/reconnect needed. It also backfills `ig_username`,
  which is why a connection can display as a bare numeric id.
- Connection status gained an `unverified` state. A missing expiry used to fall
  through to a green "Connected"; it now reads amber **"Not verified"** until
  something has actually checked.

**After deploying:** open Settings → Channels and press **Verify** on each
account. Expect the toast *"…webhook subscription was missing, so it was
reconnected."* Then confirm inbound is flowing:

```sql
SELECT max(created_at) AS newest_inbound, count(*) AS last_hour
  FROM messages
 WHERE direction = 'inbound'
   AND created_at > now() - interval '1 hour';
```

If subscription still fails, the response body is logged verbatim under
`integrations.meta.ig_subscribe` — a rejected field name shows up there and
nowhere else.

---

### Step 21 — Correction to Step 20: the real cause was the tester role

**Step 20 diagnosed this wrong. Read this instead; Step 20 stays as written
because this file is append-only.**

Step 20 blamed the URL shape — `me` versus the numeric account id — for:

```
Unsupported request - method type: post   (webhook subscribe)
Unsupported request - method type: get    (token verify)
```

That was wrong. A probe added at **Meta Diagnostics → Instagram Login — URL
probe** fired the real token at ten URL shapes. Before the fix, all nine
Instagram ones failed identically; afterwards, all nine succeeded. When every
shape fails the same way, the shape is not the variable.

**The actual cause.** While a Meta app is in **Development mode**, only
Instagram accounts holding a role on it — admin, developer or **tester** — can
be used through the API. OAuth still completes and a valid token is still
issued; every subsequent API call is refused. Meta reports that as "Unsupported
request", which reads like a malformed URL and is really "not permitted".

`@mileszetu` worked throughout because it already held a role. `@shopzetu` did
not. Same code, same app id, same URLs.

**The fix is in the Meta dashboard, not the codebase:**
Roles → **Instagram Testers** → add the account, then accept the invite from
that account's Instagram settings (Settings → Website permissions → Tester
invites). Then press **Verify** on the connection.

Two changes from Step 20 are still in place and still worth having — an
unversioned retry and numeric-id addressing — but they are belt-and-braces, not
the fix. They cost one extra request only on that specific error.

**What the probe did find that mattered.** Asking for `fields=user_id` showed
two different ids on the same account:

| field | example | meaning |
|---|---|---|
| `id` | `37355381327440609` | app-scoped — the only one we stored |
| `user_id` | `17841412308701394` | **IG Business Account id** |

Webhooks are keyed on the business id and `_connection_for()` matches on
`ig_business_account_id`, which the Instagram Login flow never populated — so
every delivery fell through to "most recent active connection". Correct by
accident with one account, silently wrong with two. Both the OAuth callback and
Verify now store it.

Also corrected while in there: `conn.scopes` recorded what we *requested*
rather than what Meta *granted* (the exchange response carries `permissions`),
and `last_verified_at` was stamped at connect time, so a connection looked
verified simply because it existed.

**Confirm inbound is actually flowing:**

```sql
SELECT max(created_at) AS newest_inbound,
       count(*) FILTER (WHERE created_at > now() - interval '1 hour') AS last_hour
  FROM messages
 WHERE direction = 'inbound';

-- Should now be populated for the active connection.
SELECT id, ig_username, ig_login_user_id, ig_business_account_id,
       last_verified_at, is_active
  FROM meta_connections ORDER BY id;
```

Remember the app is still in Development mode: a DM will only arrive from an
account that also holds a role. Test with one that does.

---

### Step 22 — Remove seed and test conversations from the live inbox

**Why.** The inbox chips advertise `Facebook 12`, `WhatsApp 7`, `TikTok 4`. None
of those channels has ever been connected — Step 18 switched them off precisely
because we cannot reply on them. So those 23 conversations cannot be real. They
are demo rows, and their ids say so out loud:

```
seed:david_ochieng_fb   seed:254712345678   fb_seed_grace   tiktok_seed_comm_1
```

They are not harmless decoration. They inflate every count an operator reads,
they sit in the queue looking like unanswered customers, and they make the
"TikTok isn't connected yet" empty state unreachable — you click TikTok
expecting the setup hint and get four fabricated threads instead.

The same applies to Instagram rows left behind by testing: `1111111111`,
`notif_test_user_4`, `test_user_keyword_1`, `seed:amina_ke`.

**The rule, so this is defensible rather than a hand-picked list:**

1. Any conversation on a channel that has never been connected is not real.
2. A real Instagram customer is always identified by an IGSID — 15+ digits.
   Anything else in `users.external_id` on an Instagram thread was typed by us.

**Look before you delete.** Run this first and read it:

```sql
SELECT c.channel,
       u.external_id,
       u.name,
       count(*) AS threads,
       max(c.last_message_at) AS newest
  FROM conversations c
  JOIN users u ON u.id = c.user_id
 WHERE c.channel NOT LIKE 'instagram%'
    OR u.external_id !~ '^[0-9]{15,}$'
 GROUP BY 1, 2, 3
 ORDER BY 1, 2;
```

Every row should be obviously ours. **If any row looks like a real customer,
stop** and tell me before running the delete.

**Then delete, children first.** No `ON DELETE CASCADE` on these, so order
matters:

```sql
BEGIN;

CREATE TEMP TABLE junk_convos AS
SELECT c.id
  FROM conversations c
  JOIN users u ON u.id = c.user_id
 WHERE c.channel NOT LIKE 'instagram%'
    OR u.external_id !~ '^[0-9]{15,}$';

DELETE FROM conversation_reads     WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM conversion_attributions WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM logs                   WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM messages               WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM conversations          WHERE id IN (SELECT id FROM junk_convos);

-- Customer records orphaned by the above. Left behind they would resurface in
-- customer profiling as people who never existed.
DELETE FROM users
 WHERE NOT EXISTS (SELECT 1 FROM conversations c WHERE c.user_id = users.id)
   AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.user_id = users.id);

-- Expect: instagram_dm / instagram_comment only, and a total that matches
-- the number of genuine IGSID threads.
SELECT channel, count(*) FROM conversations GROUP BY 1 ORDER BY 2 DESC;

COMMIT;
```

Run the `SELECT` inside the transaction and check it before `COMMIT`. If it
looks wrong, `ROLLBACK;` instead — nothing is lost.

**After this, the empty state earns its keep:** clicking TikTok shows "TikTok
isn't connected yet" instead of four invented conversations, and the platform
chips describe only traffic that actually arrived.

---

### Step 23 — Sign in with a code emailed to you

Adds a second way in beside the password. Four columns on `auth_users`, no new
table — a code belongs to exactly one account and there is only ever one live at
a time, so a row per account is the whole story.

```sql
ALTER TABLE auth_users
  ADD COLUMN IF NOT EXISTS otp_hash     VARCHAR(255),
  ADD COLUMN IF NOT EXISTS otp_expires  TIMESTAMP,
  ADD COLUMN IF NOT EXISTS otp_attempts INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS otp_sent_at  TIMESTAMP;

-- Expect four rows.
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'auth_users' AND column_name LIKE 'otp%'
 ORDER BY column_name;
```

**`otp_hash` is bcrypt, not sha256 like `reset_token_hash` beside it.** That
difference is deliberate and worth being able to explain. A reset token is 32
random bytes — sha256 of it is unguessable. A login code is six digits: one
million possibilities, which a fast hash reverses in under a second for anyone
who can read this table. bcrypt makes each guess cost ~100ms.

**No new environment variables.** Delivery reuses the Brevo HTTP API that
already sends password-reset mail (`BREVO_API_KEY`, `SMTP_FROM`). If password
resets arrive today, codes will too. If they do not, both are broken for the
same reason.

**Nothing is removed and nothing changes for existing users.** Passwords keep
working exactly as before; this is an additional door, not a replacement.

---

### Step 24 — Make webhook de-duplication actually reliable

`messages.external_id` is indexed but **not unique**, so nothing at the database
level stops the same inbound message being stored twice.

The in-process guard (`_claim_inbound`) catches the common case, but it is a
Python dictionary inside one worker. Gunicorn runs 2 workers here, and Meta
retries deliveries — so two workers handling the same retry both check, both
find nothing, and both insert. That is the "double outbound in the app, single
message on Instagram" symptom.

A unique index makes the database the arbiter, which is the only place that
works across processes.

**Look first.** This must return zero rows:

```sql
SELECT external_id, count(*)
  FROM messages
 WHERE external_id IS NOT NULL
 GROUP BY external_id
HAVING count(*) > 1
 ORDER BY 2 DESC;
```

If it returns anything, **stop and tell me** — the duplicates have to be merged
before a unique index can be created, and which copy to keep depends on what
else references them.

**Then create it.** Partial, on purpose:

```sql
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_messages_external_id
  ON messages (external_id)
 WHERE external_id IS NOT NULL;
```

Two details that matter:

- **`WHERE external_id IS NOT NULL`** — 226 rows locally have no external id
  (manual replies, seeded rows). Postgres allows many NULLs in a unique index,
  but a partial index also keeps the index smaller and states the intent.
- **`CONCURRENTLY`** — builds without locking the table against writes. Webhooks
  are arriving while you run this. It cannot be run inside a transaction block,
  so paste it on its own, **not** wrapped in `BEGIN`/`COMMIT`.

**Verify:**

```sql
SELECT indexname, indexdef FROM pg_indexes
 WHERE tablename = 'messages' AND indexname = 'uq_messages_external_id';
```

**Note for the code side:** with this in place, a duplicate insert raises
`IntegrityError` instead of succeeding. The inbound path should treat that as
"already handled, nothing to do" rather than an error — see `_claim_inbound`.

---

### Step 25 — Correction to Step 22: DO NOT run that delete

**Step 22 was wrong and would have destroyed real customer conversations.**

Its rule was "any conversation on a channel that has never been connected is not
real". The preview disproved it: `facebook_dm` rows carry 17-digit Facebook
PSIDs with timestamps from this week. Those are real people who messaged us on
Messenger. Step 18 switched Facebook off for *replying* — it never stopped
messages arriving.

The mistake was inferring realness from the CHANNEL. Realness lives in the
**id**: platform-issued ids are long numerics we could never have invented,
while everything seeded carries an obvious human-typed marker.

**The corrected rule — classify every row and look at it:**

```sql
SELECT
  CASE
    WHEN u.external_id ~ '^[0-9]{15,}$'              THEN 'KEEP - platform id'
    WHEN u.external_id LIKE 'seed:%'                 THEN 'DELETE - seed prefix'
    WHEN u.external_id LIKE 'seed!_%'   ESCAPE '!'   THEN 'DELETE - seed prefix'
    WHEN u.external_id LIKE '%!_seed!_%' ESCAPE '!'  THEN 'DELETE - seed infix'
    WHEN u.external_id LIKE '%seed%'                 THEN 'DELETE - seed word'
    WHEN u.external_id ILIKE '%test%'                THEN 'DELETE - test row'
    WHEN u.external_id ~ '^[0-9]{1,14}$'             THEN 'DELETE - short numeric'
    WHEN u.external_id = u.name                      THEN 'DELETE - name as id'
    ELSE 'REVIEW - decide by hand'
  END AS verdict,
  c.channel, u.external_id, u.name,
  count(*) AS threads, max(c.last_message_at) AS newest
FROM conversations c
JOIN users u ON u.id = c.user_id
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3;
```

A real Instagram or Facebook id is 15–17 digits. Nothing under 15 digits and
nothing containing letters was issued by Meta.

**Read the REVIEW rows before going further.** Locally they are three WhatsApp
phone numbers (`+254722333444`, `+254700111222`, `+254733555666`). Those are
genuinely ambiguous: a phone number is what a real WhatsApp id looks like, and
WhatsApp has never been connected here — so they are almost certainly seeded,
but the id alone cannot prove it. **They are NOT deleted by the SQL below.**
Decide on them yourself; if you want them gone, delete those ids explicitly.

**Then delete — patterns only, never channel:**

```sql
BEGIN;

CREATE TEMP TABLE junk_convos AS
SELECT c.id
  FROM conversations c
  JOIN users u ON u.id = c.user_id
 WHERE u.external_id !~ '^[0-9]{15,}$'         -- never touch a platform id
   AND (   u.external_id LIKE 'seed:%'
        OR u.external_id LIKE 'seed!_%'   ESCAPE '!'
        OR u.external_id LIKE '%!_seed!_%' ESCAPE '!'
        OR u.external_id LIKE '%seed%'
        OR u.external_id ILIKE '%test%'
        OR u.external_id ~ '^[0-9]{1,14}$'
        OR u.external_id = u.name);

-- Sanity check BEFORE deleting: this must be 0.
SELECT count(*) AS platform_ids_caught
  FROM conversations c
  JOIN users u ON u.id = c.user_id
 WHERE c.id IN (SELECT id FROM junk_convos)
   AND u.external_id ~ '^[0-9]{15,}$';

DELETE FROM conversation_reads      WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM conversion_attributions WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM logs                    WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM messages                WHERE conversation_id IN (SELECT id FROM junk_convos);
DELETE FROM conversations           WHERE id IN (SELECT id FROM junk_convos);

DELETE FROM users
 WHERE NOT EXISTS (SELECT 1 FROM conversations c WHERE c.user_id = users.id)
   AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.user_id = users.id)
   AND external_id !~ '^[0-9]{15,}$';

-- Real Facebook and Instagram threads must still be here.
SELECT channel, count(*) FROM conversations GROUP BY 1 ORDER BY 2 DESC;

COMMIT;
```

Run the sanity check inside the transaction and confirm it returns **0** before
`COMMIT`. If anything looks wrong, `ROLLBACK;` — nothing is lost.

**Local result of the corrected rule:** 41 conversations deleted across 33
seeded/test users; the 2 real platform-id threads and the 3 WhatsApp REVIEW rows
untouched.

**The lesson worth keeping:** "this channel isn't connected" was a plausible
proxy for "this data is fake", and it was wrong within days of being written —
because a channel can receive without being able to reply. Identify data by what
it *is*, not by what you assume about where it came from.

---

### Step 26 — The three WhatsApp rows Step 25 left for review

Step 25 deliberately would not decide these. A phone number is exactly what a
real WhatsApp id looks like, so nothing about `+254700111222` proves it was
seeded — the id alone cannot tell you. **Confirmed by hand as seed data**, so
they go.

Keyed on the channel this time, which is safe ONLY because a person has looked
at all three and said so. That is the difference between this and Step 22: the
channel is not evidence, it is just the filter for a decision already made.

**Look first — expect exactly 3, all with phone-number ids:**

```sql
SELECT c.id, u.external_id, u.name, c.last_message_at
  FROM conversations c
  JOIN users u ON u.id = c.user_id
 WHERE c.channel = 'whatsapp'
 ORDER BY c.id;
```

**If it shows anything you do not recognise, stop.** WhatsApp is not connected,
so nothing new can arrive — but check before deleting, not after.

```sql
BEGIN;

CREATE TEMP TABLE wa_convos AS
SELECT id FROM conversations WHERE channel = 'whatsapp';

DELETE FROM conversation_reads      WHERE conversation_id IN (SELECT id FROM wa_convos);
DELETE FROM conversion_attributions WHERE conversation_id IN (SELECT id FROM wa_convos);
DELETE FROM logs                    WHERE conversation_id IN (SELECT id FROM wa_convos);
DELETE FROM messages                WHERE conversation_id IN (SELECT id FROM wa_convos);
DELETE FROM conversations           WHERE id IN (SELECT id FROM wa_convos);

DELETE FROM users
 WHERE channel = 'whatsapp'
   AND NOT EXISTS (SELECT 1 FROM conversations c WHERE c.user_id = users.id)
   AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.user_id = users.id);

-- Expect: instagram_dm, instagram_comment, facebook_dm only.
SELECT channel, count(*) FROM conversations GROUP BY 1 ORDER BY 2 DESC;

COMMIT;
```

**After Steps 25 and 26 the inbox finally describes reality:** every remaining
conversation was sent by a real person, the platform chips count real traffic,
and clicking TikTok or WhatsApp shows "not connected yet" instead of inventing
a conversation history for a channel that never existed.

---

### Step 27 — The Comment → DM rule could almost never match

The rule exists and is enabled. It has been enabled since 25 May. It has
essentially never fired, and the reason is one character.

`trigger_config.keywords` is `["price?", "how much?"]`, and the matcher in
`services.py::_match_automation_actions` is a plain substring test over the
lowercased comment:

```python
keywords = [k.lower() for k in (tc.get("keywords") or [])]
matched = any(k in text for k in keywords)
```

There is no tokenising and no punctuation stripping, so the `?` is part of the
string being searched for. The keyword only matches when the question mark
falls immediately after the phrase — that is, when the phrase *ends* the
sentence:

| Comment                             | Contains `how much?` | Fires |
|-------------------------------------|----------------------|-------|
| `How much?`                         | yes                  | ✅ |
| `How much is delivery to Mombasa?`  | no                   | ❌ |
| `how much for this babe`            | no                   | ❌ |
| `What's the price?`                 | yes (`price?`)       | ✅ |
| `Price?`                            | yes                  | ✅ |
| `whats the price of this`           | no                   | ❌ |

Real customers almost never stop at "how much?" — they name the thing they are
asking about, which pushes the `?` to the end of the sentence and away from the
keyword. So the AI answered these in the open, which looked correct and was
correct, but the DM flow the rule was written for never got a chance.

Dropping the `?` from the stored keywords fixes it. `price` also catches
`priced` and `prices`, which is wanted here.

**Look first — the local dev database is a stale mirror, so confirm what
production actually holds before changing it:**

```sql
SELECT id, name, enabled, sort_order, trigger_config, action_config
  FROM automation_rules
 ORDER BY sort_order, id;
```

**Then, if row `Comment → DM` still shows the question marks:**

```sql
BEGIN;

UPDATE automation_rules
   SET trigger_config = jsonb_set(
         trigger_config, '{keywords}',
         '["price", "how much", "cost", "how many", "available"]'::jsonb),
       action_config = action_config || jsonb_build_object(
         'dm_message',
         'Hi! 👋 You asked about this on our post — happy to give you the '
         'full details here. Which item were you looking at?'),
       enabled = true,
       updated_at = now()
 WHERE name = 'Comment → DM';

-- Expect exactly one row, keywords without '?', and a dm_message present.
SELECT id, name, enabled, trigger_config -> 'keywords' AS keywords,
       action_config -> 'dm_message' AS dm_message
  FROM automation_rules WHERE name = 'Comment → DM';

COMMIT;
```

`dm_message` is set because the rule did not have one. The code falls back to a
generic "What would you like to know?" while the public reply promises "we've
sent you a DM with all the details" — a DM that then asks the customer to
repeat themselves. The two halves now agree.

**Ordering note:** rules are first-match-wins by `sort_order`. `Comment → DM`
sits at 4, behind `Out of Stock` at 3. A price question about a sold-out item
will therefore get the out-of-stock template and no DM. That is arguably the
right precedence — telling someone it is unavailable matters more than moving
the conversation — so it is left alone, but it is a real reason the rule can
still stay quiet.

**This rule cannot work without Step 27b.** `send_instagram_private_reply` was
still on the retired Facebook page token, exactly like `send_instagram_comment_reply`
was, so the DM half would have failed on its first line and posted the
"drop us a DM" fallback instead. That is a code change, not SQL — see
`app/integrations/meta.py`. Note the two logins do **not** share an endpoint
here, unlike every other sender in that file:

```
Instagram Login:  POST {ig_user_id}/messages   {"recipient": {"comment_id": ...}}
Facebook Login:   POST {comment_id}/private_replies   {"message": "..."}
```

The Instagram Login route also answers with `message_id` rather than `id`, so
the response is normalised before returning — otherwise the DM would save with
a NULL `external_id` and read as undelivered.

---

### Step 28 — "how do i get this?" is the strongest buy signal and the rule ignores it

Step 27 fixed the punctuation but kept the keyword list narrow: `price`,
`how much`, `cost`, `how many`, `available`. A live test posted two comments on
the same product:

| Comment | Matched | What happened |
|---|---|---|
| `how much is this?` | `how much` | DM opened ✅ |
| `how do i get this?` | nothing | answered under the post |

The second is the better lead. "How much" is price research; "how do I get this"
is someone asking to buy. It got a public delivery blurb and no DM.

It was not misclassified — the intent classifier read it as a delivery question,
which it literally is, and answered it correctly. The gap is the keyword list,
which was written around price and never around purchase intent.

```sql
BEGIN;

UPDATE automation_rules
   SET trigger_config = jsonb_set(
         trigger_config, '{keywords}',
         '["price", "how much", "cost", "how many", "available",
           "how do i get", "how can i get", "how do i order",
           "where can i get", "want this", "want one", "i''ll take",
           "order this", "buy this", "still selling"]'::jsonb),
       updated_at = now()
 WHERE name = 'Comment → DM';

SELECT id, name, enabled, trigger_config -> 'keywords' AS keywords
  FROM automation_rules WHERE name = 'Comment → DM';

COMMIT;
```

**Why keywords and not the `order_request` intent, which would be cleaner:**
handoff runs at Step 3.5, one step *before* automation rules at Step 3.6, and
`HANDOFF_INTENTS` already contains `order_request`. A comment classified that
way is routed to a human and never reaches the rules at all. Retriggering on
that intent would mean two systems claiming the same message. Keywords stay in
the lane the rule already occupies.

**The cost of a wider list:** matching is substring, so `available` fires on
"is this available" and equally on "when will it be available again". Both go to
a DM. For a rule whose entire purpose is moving buying conversations off a
public post, a false positive costs one unnecessary DM — cheap next to a missed
customer. Watch it for a week; if the DM volume is noisy, the phrases to drop
first are the broad single words, not the multi-word ones.

---

### Step 29 — Delete the keyword list; let the AI decide

Steps 27 and 28 were both the same move: a comment did not match, so add more
words. That loop has no end. Every phrasing we have not imagined yet is a
customer answered in public when they should have been answered in a DM.

The list is now unnecessary, because the praise decision moved to the
classifier (`app/ai/classifier.py`, new `praise` intent, and Step 3.2 in
`services.py`). Public comments are filtered like this:

| The AI reads it as | What happens |
|---|---|
| praise **alone** — "love this 😍", "🔥🔥🔥", "@amina look" | the comment is liked, no reply |
| anything else, including praise **plus** a question | full pipeline → DM with the details |

So by the time automation rules run at Step 3.6, every comment still standing
is one somebody wants an answer to. The rule no longer needs to guess which
ones from the wording — it can simply say "comments".

```sql
BEGIN;

UPDATE automation_rules
   SET trigger = 'Any Instagram comment that isn''t praise',
       trigger_config = '{"type": "channel", "channels": ["instagram_comment"]}'::jsonb,
       updated_at = now()
 WHERE name = 'Comment → DM';

SELECT id, name, enabled, sort_order, trigger, trigger_config, action_config
  FROM automation_rules WHERE name = 'Comment → DM';

COMMIT;
```

`facebook_comment` is deliberately not listed. We cannot reply on that channel
at all yet (Step 18), so a rule promising a DM there would fail every time.

**What this costs.** Every public comment now goes to Haiku for
classification, including the ones we end up only liking — previously the
keyword heuristic rejected them for free. That is the price of judging meaning
instead of vocabulary, and at our comment volume it is negligible.

**What still gets there first.** Rules are first-match-wins, and `Out of Stock`
is evaluated in the second pass (Step 4.6, after the Shopify fetch) where it
answers with its own template and returns. A comment about a sold-out item will
therefore get the out-of-stock reply publicly and no DM. Left as is: telling
someone the item is gone is the more useful message, and it is honest to say it
where they asked.

**The fallback matters.** If the classifier is unavailable, `_praise_only()`
reverts to the old `is_question()` heuristic rather than treating "not praise"
as a decision. A degraded classifier must never silently become "reply to
everything" on a public post.

---

### Step 30 — The brand is Shopzetu, one word

Fixed in 45 places across the code, the frontend and the docs. Two things
cannot be fixed there, and only one of them is ours.

**Ours: the system prompt.** `ai_settings.system_prompt` is stored in the
database, so the default in `settings.py` never reaches it. It currently opens:

> You are Shop Zetu's customer support assistant. Shop Zetu is a Kenyan fashion
> brand…

That string is in front of the model on **every single reply**, which makes it
the one place where the wrong spelling actually reaches a customer.

```sql
BEGIN;

UPDATE ai_settings
   SET system_prompt = replace(system_prompt, 'Shop Zetu', 'Shopzetu'),
       updated_at = now()
 WHERE system_prompt LIKE '%Shop Zetu%';

-- Expect 0 rows.
SELECT id FROM ai_settings WHERE system_prompt LIKE '%Shop Zetu%';

COMMIT;
```

Also worth checking, since it is edited from the Settings page and may have
been saved before this:

```sql
SELECT key, value FROM settings WHERE value::text LIKE '%Shop Zetu%';
```

**Not ours: everything mirrored from Shopify.** Four tables still contain the
old spelling and must be left exactly as they are:

| Table | Rows | What it actually is |
|---|---|---|
| `orders_cache.products` | 8003 | Real product titles — "Shop Zetu Basic Leggings - Black" |
| `products_cache.name` | 1 | "Shop Zetu Credit Note" |
| `customers_cache.city` | 3 | Real addresses — "Shop Zetu Warehouse Location", "Shop zetu moi avenue" |
| `customers_cache.first_name` | 3 | Real customer records |

These are mirrors. Rewriting them would make our figures disagree with
Shopify's, which is the one thing we have committed not to do — and the next
sync would overwrite the edit anyway, so the disagreement would be temporary
*and* invisible. **If the product titles should read "Shopzetu", the change
belongs in Shopify**, and it will arrive here on the next sync.

The `customers_cache` rows are more than a naming question: one of them holds a
customer's entire enquiry pasted into the `first_name` field ("I would want to
discuss with you advertising on our magazine CIO Africa as Shop Zetu…"). That is
a data-quality problem in Shopify, not a spelling one, and it is worth a look
because that record appears in customer-facing lists.

**Left alone deliberately:** the generated exports in `extras/` (six PDFs and
one CSV). They are records of what was reported on a given day. New exports
carry the corrected name — `reportExport.js` was part of the rename.

---

### Step 31 — Correction to Step 30: DO NOT run it. The brand IS "Shop Zetu"

Step 30 renamed the brand to "Shopzetu" on my reading of a one-line
instruction. That was wrong — it is **two words, "Shop Zetu"**. Every code and
documentation change from Step 30 has been reverted; Step 30 stays in this file
because these steps are a record, not a draft.

**If you have not run Step 30's SQL: do nothing.** The database already holds
"Shop Zetu" and is correct.

**If you did run it**, the system prompt now says "Shopzetu" in front of the
model on every reply:

```sql
BEGIN;

UPDATE ai_settings
   SET system_prompt = replace(system_prompt, 'Shopzetu', 'Shop Zetu'),
       updated_at = now()
 WHERE system_prompt LIKE '%Shopzetu%';

-- Expect the opening line to read "You are Shop Zetu's customer support assistant."
SELECT id, left(system_prompt, 80) FROM ai_settings;

COMMIT;
```

Note the `replace()` here is safe in a way a blanket find-and-replace across the
codebase would NOT have been: several legitimate uses of the one-word form
exist and must survive — the `shopzetu.com` domain, the `shopzetu` Instagram
handle, the `shopzetu-analytics-*` export filenames, and the references to "the
real shopzetu team" in Step 14b. The revert was done by restoring the exact
files rather than by substituting the string back, precisely so those were not
caught in the reverse direction.

**Still correct from Step 30, and still worth reading:** the four tables holding
the old spelling in Shopify-mirrored data (`orders_cache.products`,
`products_cache.name`, `customers_cache.city`, `customers_cache.first_name`)
were never ours to edit, whichever way the brand is spelled. And the
`customers_cache` row containing a customer's entire enquiry in the
`first_name` field is still a real data-quality problem in Shopify.

---

### Step 32 — Vivo store addresses, so the assistant can answer "where can I try this on?"

Shop Zetu is online-only, and the prompt block enforcing that used to end with
**"never refer customers to Vivo or any other brand's stores."** That was
written when Vivo was treated as a separate business this app did not
represent. It is not — Shop Zetu manages products and stock for a number of
brands, Vivo among them — so a customer asking where they can see a piece in
person was being turned away for no reason. The ban is gone, replaced by a
narrower rule: answer from the list below, never from memory. An invented
branch sends a real person across Nairobi to a shop that is not there.

**Note the key: `brand_stores`, NOT `locations`.** `kind='locations'` already
belongs to `sync_locations_now()`, which overwrites it with Shopify's
fulfilment locations — warehouses and pickup points, not customer-facing shops.
Sharing the key would mean these addresses survive exactly until the next
Shopify sync and then vanish with nothing to show they were ever there.

Hours are identical across all 21 branches, so they are stored per-store but
rendered once ("All branches: ...") rather than repeated twenty-one times. The
whole block is ~700 tokens of static text in the cached part of the system
prompt.

```sql
BEGIN;

INSERT INTO store_info_cache (kind, data, updated_at)
VALUES ('brand_stores', '[
  {
    "name": "Vivo - Capital Centre",
    "address": "Ground Floor",
    "area": "Mombasa Road, Nairobi",
    "phone": "+254 742 036533",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Galleria Shopping Mall",
    "address": "First Floor",
    "area": "Langata Road, Nairobi",
    "phone": "+254 701 099647",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Garden City Mall",
    "address": "Ground Floor",
    "area": "Thika Road, Nairobi",
    "phone": "+254 724 201270",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Signature Mall",
    "address": "Ground Floor",
    "area": "Signature Mall, Mombasa Road",
    "phone": "+254 704 913890",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Greenspan Mall Donholm",
    "address": "Ground Floor",
    "area": "Lower Savannah Dakar Road, Nairobi",
    "phone": "+254 790 672271",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Imaara Mall",
    "address": "First Floor",
    "area": "Mombasa Road, Nairobi",
    "phone": "+254 746 499820",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Mama Ngina Street",
    "address": "Jubilee Exchange House, First Floor",
    "area": "Central Business District, Nairobi",
    "phone": "+254 700 516208",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Moi Avenue",
    "address": "31 Moi Avenue",
    "area": "Central Business District, Nairobi",
    "phone": "+254 741 781602",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Sarit Centre Mall",
    "address": "Ground Floor, New Wing",
    "area": "Karuna Road, Nairobi",
    "phone": "+254 700 369070",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - T-Mall",
    "address": "Ground Floor",
    "area": "Mai-Mahiu Road, Nairobi",
    "phone": "+254 743 332423",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - The Hub, Karen",
    "address": "First Floor",
    "area": "Dagoretti Road, Nairobi",
    "phone": "+254 798 049965",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - The Junction Mall",
    "address": "Ground Floor",
    "area": "Ngong Road, Nairobi",
    "phone": "+254 704 915479",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - The Village Market",
    "address": "Ground Floor, New Wing",
    "area": "Limuru Road, Nairobi",
    "phone": "+254 746 619337",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Thika Road Mall",
    "address": "First Floor",
    "area": "Thika Road, Nairobi",
    "phone": "+254 112 801225",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Two Rivers Mall",
    "address": "Ground Floor",
    "area": "Limuru Road, Nairobi",
    "phone": "+254 717 457724",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Yaya Centre",
    "address": "First Floor",
    "area": "Argwings Kodhek Road, Nairobi",
    "phone": "+254 703 420785",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Athi River, Signature Mall",
    "address": "Ground Floor",
    "area": "Mlolongo, Athi River",
    "phone": "+254 704 913890",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Kileleshwa",
    "address": "1st Floor, Kobil Station",
    "area": "Burugani/Mandera Road, Nairobi",
    "phone": "+254 712 807263",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Runda Mall",
    "address": "Ground Floor",
    "area": "Kiambu Road, Nairobi",
    "phone": "+254 745 531862",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Safari by Vivo - Sarit",
    "address": "1st Floor, New Wing",
    "area": "Sarit Centre, Karuna Road, Nairobi",
    "phone": "+254 745 162579",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Zoya by Vivo - Sarit",
    "address": "1st Floor, New Wing",
    "area": "Sarit Centre, Karuna Road, Nairobi",
    "phone": "+254 745 162113",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  }
]'::jsonb, now())
ON CONFLICT (kind) DO UPDATE
   SET data = EXCLUDED.data, updated_at = now();

-- Expect 21.
SELECT kind, jsonb_array_length(data) AS stores, updated_at
  FROM store_info_cache WHERE kind = 'brand_stores';

COMMIT;
```

If `store_info_cache` has no unique constraint on `kind`, the upsert will fail;
use this instead:

```sql
BEGIN;
DELETE FROM store_info_cache WHERE kind = 'brand_stores';
INSERT INTO store_info_cache (kind, data, updated_at)
VALUES ('brand_stores', '[
  {
    "name": "Vivo - Capital Centre",
    "address": "Ground Floor",
    "area": "Mombasa Road, Nairobi",
    "phone": "+254 742 036533",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Galleria Shopping Mall",
    "address": "First Floor",
    "area": "Langata Road, Nairobi",
    "phone": "+254 701 099647",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Garden City Mall",
    "address": "Ground Floor",
    "area": "Thika Road, Nairobi",
    "phone": "+254 724 201270",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Signature Mall",
    "address": "Ground Floor",
    "area": "Signature Mall, Mombasa Road",
    "phone": "+254 704 913890",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Greenspan Mall Donholm",
    "address": "Ground Floor",
    "area": "Lower Savannah Dakar Road, Nairobi",
    "phone": "+254 790 672271",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Imaara Mall",
    "address": "First Floor",
    "area": "Mombasa Road, Nairobi",
    "phone": "+254 746 499820",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Mama Ngina Street",
    "address": "Jubilee Exchange House, First Floor",
    "area": "Central Business District, Nairobi",
    "phone": "+254 700 516208",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Moi Avenue",
    "address": "31 Moi Avenue",
    "area": "Central Business District, Nairobi",
    "phone": "+254 741 781602",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Sarit Centre Mall",
    "address": "Ground Floor, New Wing",
    "area": "Karuna Road, Nairobi",
    "phone": "+254 700 369070",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - T-Mall",
    "address": "Ground Floor",
    "area": "Mai-Mahiu Road, Nairobi",
    "phone": "+254 743 332423",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - The Hub, Karen",
    "address": "First Floor",
    "area": "Dagoretti Road, Nairobi",
    "phone": "+254 798 049965",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - The Junction Mall",
    "address": "Ground Floor",
    "area": "Ngong Road, Nairobi",
    "phone": "+254 704 915479",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - The Village Market",
    "address": "Ground Floor, New Wing",
    "area": "Limuru Road, Nairobi",
    "phone": "+254 746 619337",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Thika Road Mall",
    "address": "First Floor",
    "area": "Thika Road, Nairobi",
    "phone": "+254 112 801225",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Two Rivers Mall",
    "address": "Ground Floor",
    "area": "Limuru Road, Nairobi",
    "phone": "+254 717 457724",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Yaya Centre",
    "address": "First Floor",
    "area": "Argwings Kodhek Road, Nairobi",
    "phone": "+254 703 420785",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Athi River, Signature Mall",
    "address": "Ground Floor",
    "area": "Mlolongo, Athi River",
    "phone": "+254 704 913890",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Kileleshwa",
    "address": "1st Floor, Kobil Station",
    "area": "Burugani/Mandera Road, Nairobi",
    "phone": "+254 712 807263",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Vivo - Runda Mall",
    "address": "Ground Floor",
    "area": "Kiambu Road, Nairobi",
    "phone": "+254 745 531862",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Safari by Vivo - Sarit",
    "address": "1st Floor, New Wing",
    "area": "Sarit Centre, Karuna Road, Nairobi",
    "phone": "+254 745 162579",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  },
  {
    "name": "Zoya by Vivo - Sarit",
    "address": "1st Floor, New Wing",
    "area": "Sarit Centre, Karuna Road, Nairobi",
    "phone": "+254 745 162113",
    "hours": "Mon-Sat 9:30AM-8:00PM; Sun & public holidays 10:00AM-7:00PM"
  }
]'::jsonb, now());
SELECT kind, jsonb_array_length(data) AS stores FROM store_info_cache WHERE kind = 'brand_stores';
COMMIT;
```

**Two corrections to the source data**, both silent typos on the website, worth
knowing in case someone diffs this against it later:

- "Argwings Khodek Road" -> **Argwings Kodhek** Road (Yaya Centre)
- "Ground Flour" / "1st Flour" -> Floor (Runda, Safari, Zoya)

**One thing to check:** Signature Mall appears twice — "Vivo - Signature Mall,
Mombasa Road" and "Vivo - Athi River, Signature Mall, Mlolongo" — and both
carry the same phone number, +254 704 913890. They may be one shop listed
twice, or two shops sharing a line. Both are in the list as given; if they are
the same branch, delete one.


---

### Step 33 — Link a chat to a Shopify customer

Customer profiling was parked on 1 August for one reason: 162,186 Shopify
customers and the handful who have ever messaged us live in the same database
with **no key joining them**. Instagram identifies a person by IGSID, WhatsApp
by phone number, Shopify by email. No two of those overlap, so nothing can
derive the link automatically.

This is the join, made by hand. An agent looking at a conversation searches
Shopify, picks the right person, and the link is recorded — after which that
customer's order history can sit beside the thread, and profiling finally
describes people we actually talk to.

Three columns on `users`, not on `conversations`: the same customer opens
several threads over time and the link belongs to the human, not to one
exchange.

```sql
BEGIN;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS shopify_customer_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS shopify_linked_at   TIMESTAMP,
  ADD COLUMN IF NOT EXISTS shopify_linked_by   INTEGER REFERENCES auth_users(id);

CREATE INDEX IF NOT EXISTS idx_users_shopify_customer_id
  ON users (shopify_customer_id);

-- Expect the three new columns, all NULL.
SELECT column_name, data_type, is_nullable
  FROM information_schema.columns
 WHERE table_name = 'users' AND column_name LIKE 'shopify%'
 ORDER BY column_name;

COMMIT;
```

**Why `shopify_customer_id` is a plain string and not a foreign key to
`customers_cache`:** that table is a *cache*. The sync deletes and rebuilds rows
in it, and `ON DELETE CASCADE` would take the links with them — an agent's
deliberate identification silently erased by a routine sync. A weak reference
means a link can briefly point at a customer the cache has not re-fetched yet,
which is recoverable; the alternative is not.

`shopify_linked_by` records who made the call, because this is a judgement about
identity. If a thread later turns out to be attached to the wrong person's
purchase history, the question "who linked this, and when" has to have an answer.

---

### Step 34 — Let a running sync be stopped

A full customer sync walks 162,186 records and, before the N+1 fix, could run
40 minutes. There was no way to stop one — pressing Sync Now with the wrong
code deployed meant waiting it out or restarting the service.

```sql
BEGIN;

ALTER TABLE sync_jobs
  ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;

-- Frees any job stuck 'running' because the process died mid-sync (a restart
-- kills the thread but never updates the row, so the UI shows a sync that will
-- never finish and refuses to start another).
UPDATE sync_jobs
   SET status = 'cancelled',
       finished_at = COALESCE(finished_at, now()),
       progress = COALESCE(progress, '') || ' — interrupted by a restart'
 WHERE status IN ('pending', 'running')
   AND started_at < now() - interval '1 hour';

SELECT id, kind, status, progress, started_at
  FROM sync_jobs ORDER BY id DESC LIMIT 5;

COMMIT;
```

**A flag, not a thread kill.** The sync writes in chunks inside a transaction;
terminating mid-chunk leaves the cache half updated with nothing recording where
it stopped. The loop checks the flag *between* chunks and unwinds cleanly, so
`cancelled` describes a known state.

**Rows already written stay written.** They hold Shopify's current values, so a
cancelled sync leaves the cache partly refreshed and wholly correct — never
reverted to older data. Re-running continues the job rather than undoing it.

The second statement matters as much as the first: killing the Render process to
stop a sync leaves its `sync_jobs` row saying `running` forever, and the UI will
not start a new one while it thinks one is in flight.

---

### Step 35 — Sale prices the assistant could not see

The app holds `read_discounts` and `read_price_rules` and has never used them —
Shopify's own app page flags both as "Unused access, no activity in the last 30
days". The obvious move was to wire them up. Checked first:

```
ACTIVE automatic discounts : 0
products sampled           : 100
with a compareAtPrice markdown : 22
```

**This store does not run sales through discount codes.** It marks products
down, which shows up as `compare_at_price` above `price` on the variant — and
that needs only `read_products`, which we already had. Wiring up the discount
APIs would have returned an empty list.

What we were doing instead: dropping `compare_at_price` on every sync, so the
assistant quoted "KES 1,825" for a dress reduced from 2,900 and never mentioned
the saving. A fifth of the catalogue, silently.

No schema change — `variants_detail` is JSON, so the new key lands with the next
product sync. Run one after deploying:

```sql
-- Before: expect 0.
SELECT count(*) FROM products_cache
 WHERE variants_detail::text LIKE '%compare_at_price%';

-- After a product sync, expect most rows. Spot-check a marked-down item:
SELECT name, variants_detail -> 0 ->> 'price'             AS price,
              variants_detail -> 0 ->> 'compare_at_price' AS was
  FROM products_cache
 WHERE variants_detail -> 0 ->> 'compare_at_price' IS NOT NULL
 LIMIT 5;
```

**A markdown is only a markdown when compare_at_price is HIGHER than price.**
Shopify allows the reverse, and treating that as a sale would advertise a
discount that does not exist — the check is explicit for that reason.

`read_discounts` and `read_price_rules` remain unused. Worth keeping: the moment
someone runs a code-based promotion they become the right source, and asking for
a scope back later is harder than holding one.

---

### Step 36 — Returns policy and the real delivery table

The assistant had no returns policy at all, and its delivery figures came from
whatever anyone had typed into Settings. Both now come from the published
policy.

**Delivery goes in `delivery.zones`** — structured, so `format_delivery_for_prompt()`
renders it and it is injected only on delivery questions.

**Returns goes in `delivery.returns_policy`** — one block of text, injected only
when the classifier returns the new `return_request` intent. It is ~2,000
characters and most conversations are about a dress; paying for it on every
reply would spend most of a prompt on a policy nobody asked about.

```sql
BEGIN;

UPDATE app_settings
   SET data = jsonb_set(
         jsonb_set(
           COALESCE(data, '{}'::jsonb),
           '{delivery,zones}',
           '[
             {"name": "Nairobi",                    "fee": "KES 220", "eta": "1-3 business days"},
             {"name": "Nairobi environs (Ngong, Rongai, Kiserian, Kiambu, Juja, Thika, Kikuyu, Limuru, Kitengela, Athi River)",
                                                    "fee": "KES 300", "eta": "1-3 business days"},
             {"name": "Other towns outside Nairobi","fee": "KES 500", "eta": "3-5 business days"},
             {"name": "East Africa (outside Kenya)","fee": "Varies by country, passed on to the customer", "eta": "7-10 business days"},
             {"name": "International",              "fee": "Varies by country, passed on to the customer", "eta": "10-14 business days"}
           ]'::jsonb),
         '{delivery,returns_policy}',
         to_jsonb($returns$
RETURNS AND EXCHANGES

Eligibility (Kenya, Uganda, Rwanda and rest of world)
- Return or exchange within 7 DAYS of delivery.
- Original condition, unworn, all tags attached, not washed.
- Must meet hygiene standards: no sweat, dirt or stains.
- Must be accompanied by the Shop Zetu invoice.

Refunds and exchanges
- Refund goes to the original payment method, or the customer may choose M-Pesa,
  card, or a Shop Zetu gift card.
- ITEMS ON SALE ARE ELIGIBLE FOR EXCHANGE ONLY. No refund is given on a sale item.

Starting a return
- The customer MUST call customer support first. NO RETURN IS ACCEPTED unless
  support has initiated it.
- Support: +254 748 419357, +254 703 420780, +254 705 408426, support@shopzetu.com
- Kenya: pack securely with all original packaging and the invoice, then drop at
  the nearest Vivo store or Shop Zetu store.
- Uganda, Rwanda, rest of world: pack securely and send to the return address
  support provides.

Return shipping costs
- Nairobi: call to initiate, then drop at the nearest Vivo store. Alternative
  arrangements are available for an additional fee.
- Outside Nairobi: the customer pays return shipping via the nearest Speedaf agent.
- Uganda, Rwanda, rest of world: the customer pays return shipping.

Refund timing
- Processed within 2-3 business days of us receiving and inspecting the item.

NOT eligible for return, anywhere
- Skincare, make-up, swimwear, fragrances, underwear.
$returns$::text)
       )
 WHERE id = 1;

SELECT jsonb_array_length(data -> 'delivery' -> 'zones') AS zones,
       length(data -> 'delivery' ->> 'returns_policy')   AS policy_chars
  FROM app_settings WHERE id = 1;

COMMIT;
```

Expect `5` zones and roughly `1700` characters.

**Two rules are stated in capitals on purpose**, because they are the ones an
assistant will otherwise get wrong and the business will have to honour:

- **Sale items are exchange only.** This is now enforceable rather than hoped
  for: since Step 35 the assistant knows which variants carry a markdown
  (`compare_at_price`), so it can tell a customer their item is reduced and
  therefore exchange-only instead of promising a refund.
- **Nothing is accepted unless support started it.** A customer told to "just
  drop it at a Vivo store" arrives and is turned away.

`app_settings` is a single JSON row (id=1), so this is an in-place edit of two
keys. Nothing else in the document is touched.

---

### Step 37 — Stop trusting Shopify Reports: capture the fields needed to compute sales ourselves

**Why.** Every sales figure on Customer Profiling — Total sales, its seven-row
breakdown, order count, AOV, and the revenue chart — came from ShopifyQL, which
requires the `read_reports` scope and reads Shopify's *analytics* layer: the
same derived data behind the admin's Reports section. Finance has been
reporting for a while that Reports is short a few orders against what the tech
team sees in the API.

That is now measured rather than reported. Comparing ShopifyQL's monthly order
counts against `orders_cache` over 52 complete months:

```
ShopifyQL LOWER than the transactional API : 52 months
ShopifyQL HIGHER                           :  0 months
exactly equal                              :  0 months
```

Every month, without exception, between 5 and 35 orders short — roughly 0.5% to
1.4% each month, ~665 orders across the window. A one-directional gap in all 52
of 52 months is not sampling noise.

A separate defect made it worse: `GROUP BY day` hits ShopifyQL's 1,000-row cap,
so the daily chart plotted an arbitrary 1,000 of 1,617 days spread across the
full date range — missing 617 days and 91.9M in revenue while looking
continuous. That one was ours, not Shopify's.

**What this step does.** Nothing user-visible. It adds the columns needed to
compute Shopify's own sales definitions from the transactional order payload,
which we already fetch and already throw most of away. Displaying computed
figures comes later, once they can be reconciled against ShopifyQL side by side.

Every column is nullable with **no default**, deliberately. A row synced before
this step must read as "not captured", not as a confident zero — otherwise a
half-populated table produces a total that is quietly too low, which is the
failure this whole step exists to remove.

```sql
BEGIN;

ALTER TABLE orders_cache
  ADD COLUMN IF NOT EXISTS gross_sales     NUMERIC(12,2),  -- total_line_items_price
  ADD COLUMN IF NOT EXISTS total_discounts NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS total_tax       NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS total_shipping  NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS total_refunded  NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS cancelled_at    TIMESTAMP,
  ADD COLUMN IF NOT EXISTS is_test         BOOLEAN;

COMMIT;
```

**After running it, re-sync orders** (`POST /api/orders/sync`). Until that
finishes the new columns are NULL everywhere, which is why nothing reads them
yet.

**What each column is for**

| Column | Feeds |
|---|---|
| `gross_sales` | Gross sales — the top line of the breakdown |
| `total_discounts` | Discounts |
| `total_refunded` | Returns. Shopify attributes a return to the **refund date**, not the order date — a detail that will move monthly figures if we get it wrong |
| `total_tax` | Taxes. Also retires `ex_vat()`'s hardcoded 1.16 divisor, which is wrong for anything zero-rated or exempt |
| `total_shipping` | Shipping |
| `cancelled_at`, `is_test` | Exclusions. Shopify's analytics leaves test and cancelled orders out; a computed total that includes them will not reconcile |

**One open question this data will answer.** A shortfall in all 52 months is
also what we would see if Shopify *correctly* excludes orders we include — test
or cancelled ones. Finance's complaint is about real orders, which that theory
does not explain, but `is_test` and `cancelled_at` settle it directly: if the
665 missing orders turn out to be flagged, Shopify was right and we replicate
its exclusions; if they are ordinary paid orders, Reports is dropping revenue.
Either way the columns are needed.

---

### Step 38 — Refunds get their own table, so monthly Returns lands in the right month

Step 37 added `orders_cache.total_refunded`: one lifetime figure per order. That
is enough for "what did this customer cost us" and **not** enough for a monthly
Returns line, which is what the sales breakdown needs.

Shopify attributes a return to the date the **refund** was processed, not the
date of the order. An order placed in March and refunded in May reduces **May**.
Summing a per-order column by `order_date` pushes that money into March —
understating May and overstating March — and because the annual total still
comes out right, nothing in any check would show it. Only the months are wrong,
which is exactly what finance reads.

So refunds need their own rows, each with its own date.

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS refunds_cache (
    id                 SERIAL PRIMARY KEY,
    shopify_refund_id  VARCHAR(64)  NOT NULL UNIQUE,
    shopify_order_id   VARCHAR(64)  NOT NULL,
    refund_date        TIMESTAMP,
    goods_subtotal     NUMERIC(12,2),
    goods_tax          NUMERIC(12,2),
    amount_refunded    NUMERIC(12,2),
    currency           VARCHAR(8),
    cached_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- The two ways this table gets read: "Returns for a month" and
-- "everything refunded against this order".
CREATE INDEX IF NOT EXISTS ix_refunds_cache_date  ON refunds_cache (refund_date);
CREATE INDEX IF NOT EXISTS ix_refunds_cache_order ON refunds_cache (shopify_order_id);

COMMIT;
```

Populated by the same order sync as Step 37 — Shopify returns the full `refunds`
array inside each order payload, so this costs no extra API calls.

**Two amounts per refund, and they are not interchangeable**

| Column | Is | Use for |
|---|---|---|
| `goods_subtotal` | Value of the items sent back, from `refund_line_items` | **The "Returns" line.** Excludes refunded tax and shipping because the breakdown already subtracts those via its own Taxes and Shipping lines |
| `amount_refunded` | What actually left the bank, from settled refund transactions | "How much did we pay back" — a real question, but the wrong number for Returns |

Using `amount_refunded` in the Returns line double-counts refunded tax and
shipping and will not reconcile against Shopify. `goods_tax` is kept so the tax
portion can be netted off the Taxes line when the computed breakdown is built.

Only transactions with `kind='refund'` and `status='success'` are counted. A
pending or failed refund is not money returned, and counting it understates
sales.

`refund_date` prefers the refund's `processed_at` over `created_at` — the former
is when the money moved, and they differ whenever a refund is drafted and
settled later.

**Run Steps 37 and 38 BEFORE deploying the code that goes with them.**

This is a hard ordering dependency, not a preference. The models now declare the
new columns and table, so every order INSERT names them. Deploying first means
the order sync fails outright — and the nightly cron with it — until the SQL
lands. SQL first, then deploy, then re-sync orders.

---

### Step 39 — Force a full order backfill, so Steps 37 and 38 actually populate

Run this **after** Steps 37 and 38 and after deploying, and **before** triggering
the orders sync.

The orders sync is incremental. `cron_sync_orders()` decides which mode to run
purely from the watermark:

```python
is_delta = watermark is not None
```

The watermark currently reads `2026-07-02`, so triggering the sync — from the
GitHub Actions "Daily Sync" workflow or anywhere else — fetches only orders
Shopify has touched since then. Around 130,000 existing rows would keep NULL in
every column Steps 37 and 38 added, and the computed sales figures would be
built from the few hundred orders that happened to change. The result is a
number that is far too low and looks like a working feature.

A NULL watermark means "never synced" and triggers a full backfill.

```sql
BEGIN;

UPDATE sync_state
   SET watermark = NULL
 WHERE kind = 'orders';

COMMIT;
```

**This is safe.** The orders sync has no delete path — `removed_count` is
initialised to 0 and never incremented. A full backfill only inserts and
updates, so nothing can be lost the way it could have been in Step 22. It also
resumes from a saved cursor if it is interrupted.

It re-fetches all ~131,000 orders, so expect it to run for a while.

**Then** trigger it: GitHub → Actions → *Daily Sync* → *Run workflow* →
`sync_type: orders`.

Afterwards the watermark sets itself again and every later run returns to being
a delta. This is a one-time reset, not a change in how the sync works.

**Separately worth looking at:** that watermark should never have been six weeks
old. The schedule runs orders every three hours, so either the job has been
failing or it has not advanced the watermark since 2 July — which is also why
`orders_cache` holds nothing newer than that date. Fixing the backfill does not
explain the six-week gap, and the gap will come back if whatever caused it is
still there.

---

### Step 40 — Correction to Step 38: refunded amounts of 0.00 are unknown, not zero

Step 38 shipped `amount_refunded` defaulting to `0.0` whenever no settled refund
transaction was found. Against production that produced:

```
refunds                 51,818
amount_refunded = 0     47,543   (92%)
  of which goods > 0    44,981   (87%)
```

Those rows do not mean nothing was refunded. `orders.json`'s **list** response
carries `refund_line_items` but not the refund **transactions** — those arrive
only on a single-order fetch. So the filter matched nothing and wrote a
confident zero. Summed, it reported KES 16.2M refunded against KES 216.3M of
goods returned: understated roughly 13x.

A column of zeroes reads as data. NULL reads as absence. This is the same rule
the Step 37 columns were built on, broken in the one place that sums money.

**The code fix** (deploy before running the SQL below): a missing `transactions`
key now yields NULL. Present-but-empty, or present with nothing settled, stays a
real 0.00 — Shopify did tell us, and the answer was none.

```sql
BEGIN;

-- Existing zeros cannot be told apart after the fact: a genuine zero and a
-- never-reported one look identical. Both become NULL, which is the honest
-- reading of "we do not know" and is what the fixed code would have written
-- for the overwhelming majority of them.
UPDATE refunds_cache
   SET amount_refunded = NULL
 WHERE amount_refunded = 0;

UPDATE orders_cache
   SET total_refunded = NULL
 WHERE total_refunded = 0;

COMMIT;
```

**No re-sync is needed, and none would help.** The list endpoint will never
return those transactions, so a full backfill would rewrite the same NULLs. Going
forward the webhook path receives complete order payloads, so refunds processed
from now on will populate it; history stays NULL.

**Nothing that matters depends on this column.** The Returns line uses
`goods_subtotal`, which comes from `refund_line_items` and is present and
healthy — 216.3M against ShopifyQL's 188.4M, and a ~30% return rate that both
sources independently agree on. `amount_refunded` answers "what did we pay back",
which is a real question and now correctly answers "unknown" for history rather
than "nothing".

---

### Step 41 — Reclaim disk: one duplicate index, one index nothing queries

Supabase reports the database at **0.356 GB of a 0.5 GB free-plan limit (71%)**,
and Steps 37/38 are actively adding to it (`refunds_cache` ~15 MB, the new order
columns ~8 MB, plus row-version churn from the backfill). This buys headroom
while the hosting plan is decided.

Indexes are **44% of the database** — 101 MB against 230 MB of total size, and
`customers_cache` carries more index (64 MB) than data (57 MB). Two of them earn
nothing.

```sql
BEGIN;

-- 1. An exact duplicate.
--
--    idx_customers_last_order       btree (last_order_date DESC)
--    idx_customers_last_order_date  btree (last_order_date DESC)
--
--    Identical definition, identical column, identical ordering. Only the first
--    appears in database/railway-backup.sql, so the second was added later
--    without anyone noticing it already existed. Neither backs a constraint, so
--    dropping one cannot change a query plan: the planner has an identical
--    index still available. Keeping the original name.
DROP INDEX IF EXISTS idx_customers_last_order_date;

-- 2. A GIN index on jsonb that no query uses.
--
--    GIN is the correct index type for jsonb — this is not a wrong-index-type
--    problem. It is that `variants_detail` is only ever written whole and read
--    whole (app/ai/generator.py reads product['variants_detail'] in Python).
--    There is no containment (@>), key-existence (?) or path query against it
--    anywhere in the codebase, and a GIN index serves no other kind.
--
--    So it is pure cost: ~8 MB of disk, plus GIN maintenance on every product
--    write — and products are re-synced in full on every products sync. Dropping
--    it should make that sync faster as well as smaller.
DROP INDEX IF EXISTS idx_products_cache_variants_detail;

COMMIT;
```

Dropping an index returns its space immediately; no VACUUM is needed for that
part. Expect roughly **13 MB** back.

**If a jsonb query on `variants_detail` is ever added** — searching products by
variant size or colour inside the JSON, say — recreate it:

```sql
CREATE INDEX idx_products_cache_variants_detail
    ON products_cache USING gin (variants_detail);
```

---

**Separately, after the order backfill finishes**, reclaim the row versions it
left behind. Re-syncing ~130,000 existing orders writes a new version of every
row, and the dead ones hold disk until vacuumed.

`VACUUM` cannot run inside a transaction — run these **on their own**, with no
`BEGIN`/`COMMIT` around them:

```sql
VACUUM (ANALYZE) orders_cache;
VACUUM (ANALYZE) customers_cache;
VACUUM (ANALYZE) products_cache;
```

Plain `VACUUM` is safe and does not lock the table against reads or writes, but
it only marks space reusable internally — Supabase's reported size may barely
move. To actually return disk to the operating system:

```sql
VACUUM FULL orders_cache;
```

`VACUUM FULL` takes an **exclusive lock** (nothing can read or write that table
while it runs) and needs free space equal to the table's size to rebuild it.
`orders_cache` is ~33 MB against ~144 MB free, so it fits — but run it in a
quiet period, not while a sync is going.

---

### Step 42 — Correct the delivery fees the assistant quotes

The zones stored in Step 36 came from the published policy page. The rates
actually charged at checkout, read off recent orders, differ — and the assistant
has been quoting the old ones.

| Zone | Was quoting | Actually charged |
|---|---|---|
| Nairobi | KES 220 | **KES 250** |
| Nairobi environs | KES 300 | **KES 350** |
| Other towns | KES 500 | KES 500 |
| Vivo store pickup | *not offered at all* | **KES 250** |

Under-quoting is the part that matters. A customer told "delivery is 220" and
then charged 250 at checkout either gets the difference absorbed or gets an
argument — over 30 shillings, on an order someone already decided to place.

**The town list changed more than the price did.** Only Ngong, Rongai and Juja
appear in both versions. The old list named Kiserian, Kiambu, Thika, Kikuyu,
Limuru, Kitengela and Athi River; the live rate names **Thindigua, KU, Kinoo,
Utawala, Ruiru, Syokimau, Ruaka, Karen and Kitisuru** instead.

Karen and Kitisuru are the expensive mistake: most people would describe both as
Nairobi, so the assistant would quote 250 against a real rate of 350.

**Vivo store pickup was missing entirely** — a whole fulfilment option customers
could not be told about. It carries an instruction the others do not: the
customer has to name the specific store in the address field. Step 32 already
loaded the Vivo store addresses, so the assistant can name them when asked.

```sql
BEGIN;

UPDATE app_settings
   SET data = jsonb_set(
         COALESCE(data, '{}'::jsonb),
         '{delivery,zones}',
         '[
           {"name": "Home delivery within Nairobi",
            "fee": "KES 250", "eta": "1-3 business days"},
           {"name": "Vivo store pickup (Nairobi orders only — the customer must name the specific Vivo store in the address section)",
            "fee": "KES 250", "eta": "1-3 business days"},
           {"name": "Nairobi environs (Ngong, Rongai, Thindigua, KU, Juja, Kinoo, Utawala, Ruiru, Syokimau, Ruaka, Karen, Kitisuru)",
            "fee": "KES 350", "eta": "1-3 business days"},
           {"name": "Other towns (outside Nairobi and its environs)",
            "fee": "KES 500", "eta": "3-5 business days"},
           {"name": "East Africa (outside Kenya)",
            "fee": "Varies by country, passed on to the customer", "eta": "7-10 business days"},
           {"name": "International",
            "fee": "Varies by country, passed on to the customer", "eta": "10-14 business days"}
         ]'::jsonb,
         true)
 WHERE id = 1;

COMMIT;
```

Nairobi is listed first because it is the common case and the assistant reads
these in order.

**Two things this step does NOT decide, deliberately.**

*East Africa and International are kept unchanged.* Neither appeared in the
recent orders that produced this correction, but absence from a sample is not
evidence a rate was withdrawn — and the returns policy in Step 36 explicitly
covers Uganda, Rwanda and the rest of the world, so international orders plainly
happen. Deleting them would have the assistant tell a Ugandan customer we do not
ship there. **Worth confirming against the live Shopify shipping rates.**

*The dropped towns are not re-homed.* Kiserian, Kiambu, Thika, Kikuyu, Limuru,
Kitengela and Athi River no longer appear in any zone name. They are presumably
covered by "Other towns" at KES 500, but that is an inference. If any of them
should still be charged the 350 environs rate, add them to that list — the
assistant can only match on the names written here.

---

### Step 43 — Drop the East Africa and International delivery zones

Step 42 kept these two rather than delete them on the strength of a sample.
Confirmed since: they are not offered, so the assistant should stop quoting them.

```sql
BEGIN;

UPDATE app_settings
   SET data = jsonb_set(
         data,
         '{delivery,zones}',
         (SELECT jsonb_agg(z)
            FROM jsonb_array_elements(data->'delivery'->'zones') z
           WHERE z->>'name' NOT IN ('East Africa (outside Kenya)', 'International')),
         true)
 WHERE id = 1;

COMMIT;
```

Filtering by exact name rather than by position: array indexes shift the moment
anyone reorders the zones, and a positional delete would then silently remove
the wrong one.

**This leaves a contradiction the assistant can walk into.** The returns policy
loaded in Step 36 opens with:

> Eligibility (Kenya, Uganda, Rwanda and rest of world)

So the assistant now believes returns are accepted from Uganda, Rwanda and the
rest of the world, while having no delivery zone that reaches any of them. Asked
"do you deliver to Kampala?" it should say no; asked "can I return this from
Kampala?" it will say yes. Both answers come from configuration we wrote.

Whichever is wrong should be corrected — either the policy text drops the
international eligibility line, or international delivery goes back in. Left as
found here because only the delivery side was confirmed.

**Still unresolved from Step 42:** Kiserian, Kiambu, Thika, Kikuyu, Limuru,
Kitengela and Athi River appear in no zone name, so they fall to "Other towns"
at KES 500. Nobody has confirmed whether that is the real rate for them.

---

### Step 44 — Make customer search usable (4.2s → milliseconds)

Linking a conversation to a Shopify customer runs `ILIKE '%term%'` across five
columns of a 162,000-row table. No index can serve a leading-wildcard match, so
every keystroke is a full sequential scan:

```
SELECT count(*) FROM customers_cache WHERE ... ILIKE '%pat mbugua%';
Time: 4239.287 ms
```

**4.2 seconds, typed while a customer waits.** The visible symptom is worse than
slowness: searching "pat mbugua" showed three unrelated high-spending customers,
because the query for an earlier keystroke ("pa" — 4,266 matches, ordered by
spend) returned *after* the one for the full name and overwrote it. The right
customer had been found — "pat mbugua" matches exactly one row — and was then
replaced by stale results.

`pg_trgm` is already installed, so trigram indexes work immediately. They are the
one index type that can serve `%term%`.

```sql
BEGIN;

-- One index per searched column. Trigram GIN is what makes a leading-wildcard
-- ILIKE indexable at all.
CREATE INDEX IF NOT EXISTS ix_customers_first_name_trgm
    ON customers_cache USING gin (lower(first_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_customers_last_name_trgm
    ON customers_cache USING gin (lower(last_name) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_customers_email_trgm
    ON customers_cache USING gin (lower(email) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_customers_phone_trgm
    ON customers_cache USING gin (lower(phone) gin_trgm_ops);

COMMIT;

ANALYZE customers_cache;
```

`ANALYZE` runs outside the transaction. Without it the planner keeps its old
statistics and may ignore the new indexes.

**Cost:** roughly 40-60 MB of disk. The database is ~184 MB of Render's 1 GB, so
this is affordable — but it is the single largest thing added since the move, and
worth remembering if space gets tight. Step 41 dropped ~13 MB of indexes that
earned nothing; these earn their space every time an agent links a customer.

**Note the `lower()`.** The index is on `lower(column)` and the query must use
`lower(column) LIKE lower(term)` to match it. A plain `ILIKE` will NOT use these
indexes — it is a different expression as far as the planner is concerned, and
the search would silently stay slow while the indexes sat unused.

---

### Step 45 — Capture the product vendor, so sizing can be brand-specific

Every vendor sizes differently. Bust 43 inches is an **L** on Shop Zetu's house
guide and a **1X** on Vivo's — a full size apart, on the same body.

Shop Zetu's own chart says so in its header:

> *"Some brands may vary from these measurements but the table can still be used
> as a guide"*

So a single chart cannot answer "what size am I?" for a multi-brand catalogue,
and answering from the wrong one produces a return — which for a sale item is
exchange-only under the returns policy in Step 36.

To pick the right chart we need to know a product's brand. Shopify sends
`vendor` on every product and we discard it, exactly as we discarded `total_tax`
before Step 37. Tags are not a substitute: they carry brand-ish strings
(`Vivo_2026_sync`, `Vivo_Sale`, `VIVO`, `Vivo_Shopzetu_SYNC`) mixed with sizes
and campaign names, inconsistently cased, several per product.

```sql
BEGIN;

ALTER TABLE products_cache
  ADD COLUMN IF NOT EXISTS vendor VARCHAR(128);

CREATE INDEX IF NOT EXISTS ix_products_cache_vendor ON products_cache (vendor);

COMMIT;
```

Nullable with no default: a product synced before this step has an unknown
vendor, which must stay distinguishable from one Shopify genuinely reports as
blank. The sizing logic treats unknown as "no brand chart — use the house guide
and say so", and that only works if the two cases can be told apart.

**After deploying, run a products sync** to populate it. Products re-sync in full
on their own schedule, so this fills in without a watermark reset.

