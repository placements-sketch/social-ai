# Production database changes

A running record of the SQL to run against **production** (Supabase), grouped
by the frontend page the work belonged to. Kept because the review is
happening page by page, so production is touched once per page rather than
after every commit.

There is no `migrations/` directory in this project, so schema changes ship as
SQL here.

## If you already ran part of this

**Just run the whole page's steps again, in order.** Every block is
idempotent — `IF NOT EXISTS` on the DDL, and `WHERE ... IS NULL` /
`IS DISTINCT FROM` guards on the backfills — so anything already applied
matches zero rows the second time and nothing is double-counted.

**Order matters within a page.** Later steps read columns that earlier steps
create and fill, so run them top to bottom. Step 1 of each page tells you what
state production is actually in, so you never have to remember what you ran.

**Paste into the Supabase SQL editor.** Deploy the code first; every change is
additive, so the running code keeps working against the new columns.

---

## Dashboard page

Run steps 1 → 7 in order. Steps 5–7 are queries and deploy notes, not changes.

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

### Step 5 — Verify

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

### Step 5b — Link historical inbound logs to their conversations

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

### Step 6 — Optional: see why anything went unanswered

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

### Step 6b — Schedule the unclaimed-queue check

No database change. A new cron endpoint alerts when a conversation sits in the
human queue with nobody assigned. Point your scheduler at it every ~5 minutes,
same auth as the other cron jobs:

```
POST /api/cron/check-unclaimed      header: X-Cron-Secret: <CRON_SECRET>
```

Threshold is `handoff.unclaimed_alert_minutes` in settings (default 15, or the
`UNCLAIMED_ALERT_MINUTES` env var). It alerts **once per waiting spell**, not
once per tick, so a short interval is safe.

To see the queue without waiting for an alert (supervisor/admin only):

```
GET /api/conversations/unclaimed?threshold_minutes=0
```

### Step 6c — Schedule the conversion attribution job

**No database change, but Conversion Rate stays permanently 0 without it.**

`POST /api/cron/attribute` scans recent Shopify orders, reads our UTM token
out of each order's `landing_site`, and writes the `conversion_attributions`
row that links the order back to the message that earned it. Nothing else
writes that table.

It has **never run** — `sync_jobs` has rows for `products_apply`,
`orders_apply` and `customers_apply`, but none for `attribute`, and there are
no `cron.attribute.*` log entries at all. So every conversion figure on the
Dashboard has been structurally zero since launch, regardless of how many
customers actually bought.

```
POST /api/cron/attribute      header: X-Cron-Secret: <CRON_SECRET>
```

Schedule it **at least daily**. It looks back only `window_days = 7`
(`app/cron_routes.py`), so an order that isn't picked up within a week of its
last update is never attributed — the data is lost, not delayed. If the job is
paused for longer than that, widen the window before re-enabling.

Verify after the first run:

```sql
SELECT count(*) AS rows,
       min(order_date) AS oldest,
       max(order_date) AS newest
FROM conversion_attributions;
```

### Step 7 — Not database changes

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
