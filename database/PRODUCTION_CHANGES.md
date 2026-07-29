# Production database changes

A running record of the SQL to run against **production** (Supabase), grouped
by the frontend page the work belonged to. Kept because the review is
happening page by page, so production is touched once per page rather than
after every commit.

There is no `migrations/` directory in this project, so schema changes ship as
SQL here. Everything below is idempotent — `IF NOT EXISTS` on DDL and
`WHERE ... IS NULL` guards on backfills — so re-running a block is safe.

**Paste into the Supabase SQL editor and run.** Deploy the code first; every
change is additive, so the old code keeps working against the new columns.

---

## Dashboard page

Status: **not yet run in production.**

### 0. Before you run — check `messages.ai_eligible`

This column predates the current work, and it is not in `schema.sql`, so it
may not exist in production. The Dashboard's **Success Rate** and **Response
Rate** both filter on it — if it is missing the endpoint errors, and if it is
present but NULL both rates silently read 0.

```sql
-- Does the column exist?
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'messages' AND column_name = 'ai_eligible';

-- Is it populated? NULLs are excluded from both rates.
SELECT ai_eligible, count(*)
FROM messages
WHERE direction = 'inbound'
GROUP BY 1;
```

If the column is **missing entirely**, stop and say so — that needs a separate
piece of work. If it exists, carry on to the repair below.

### 0b. Repair `messages.ai_eligible`

`ai_eligible` is meant to be a snapshot of whether the AI was allowed to
answer a message **at the moment it arrived**. The original backfill instead
derived it from whatever `conversations.ai_enabled` and `channels.enabled`
happened to say at backfill time, so any conversation or channel switched off
later had its entire history retroactively marked ineligible — including
messages the AI verifiably answered.

That matters because Success Rate, Response Rate and every per-channel
answered rate filter on this column. On local dev, **25 inbound messages were
marked ineligible despite the AI having replied in that conversation
afterwards.**

The three statements below go from strongest evidence to weakest, and each is
guarded so it can't overwrite a better answer:

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
           AND r.direction = 'outbound'
           AND r.sender    = 'ai'
           AND r.created_at >= m.created_at);

-- 2. HARD EVIDENCE the other way: the message arrived after the AI was
--    switched off for that conversation. Only fills gaps, never overwrites.
UPDATE messages m
SET ai_eligible = false
FROM conversations c
WHERE c.id = m.conversation_id
  AND m.direction    = 'inbound'
  AND m.ai_eligible IS NULL
  AND c.ai_disabled_at IS NOT NULL
  AND m.created_at >= c.ai_disabled_at;

-- 3. NO EVIDENCE: fall back to the current gates. Same guess the original
--    backfill made, but now only for rows nothing better could be said about.
UPDATE messages m
SET ai_eligible = COALESCE(ch.enabled, true) AND c.ai_enabled
FROM conversations c
LEFT JOIN channels ch ON ch.channel = c.channel
WHERE c.id = m.conversation_id
  AND m.direction    = 'inbound'
  AND m.ai_eligible IS NULL;
```

Run **after** section 1/2 below, since statement 2 reads `ai_disabled_at`.

Local dev: 25 / 0 / 0 rows, moving the distribution from `false: 44, true: 83`
to `false: 19, true: 108`. Success Rate went 18.8% → 21.9% and WhatsApp and
Facebook went from "AI off here" to 100% answered.

**What this does not fix.** There is no history for `channels.enabled` or the
global AI master switch, so messages with no AI reply and no recorded
disable stay as they are — genuinely ambiguous. Locally that's 17 rows.
Snapshots taken from the deploy onwards are captured live and are exact.

### 1. Escalation timestamps — schema

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

### 2. Escalation timestamps — backfill

**"Escalated" on the Dashboard reads these, so it shows 0 for all history
until this runs.**

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
Escalations recorded from here on are exact — nothing is approximated going
forward. Query 3 below shows you the split for production.

### 3. Verify

```sql
-- Columns exist — expect 2 rows.
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'conversations'
  AND column_name IN ('escalated_at', 'ai_disabled_at');

-- Backfill landed. Both should be > 0 if there is any handoff history.
SELECT count(*) FILTER (WHERE escalated_at IS NOT NULL)   AS escalated,
       count(*) FILTER (WHERE ai_disabled_at IS NOT NULL) AS ai_off
FROM conversations;

-- How many escalation dates are exact vs approximated?
SELECT count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM logs l
          WHERE l.conversation_id = c.id
            AND l.source = 'handoff.triggered')) AS exact_from_logs,
       count(*) FILTER (WHERE NOT EXISTS (
         SELECT 1 FROM logs l
          WHERE l.conversation_id = c.id
            AND l.source = 'handoff.triggered')) AS approximated
FROM conversations c
WHERE c.escalated_at IS NOT NULL;
```

Local dev returns `(7, 11)` for the second query, and `0 exact / 7
approximated` for the third.

### 4. Not a DB change, but required — `tzdata`

The deploy crashes without it. Analytics resolves calendar windows in the
business timezone, and `zoneinfo` has no tz database of its own on some hosts.

```
pip install -r requirements.txt      # tzdata==2026.3 was added
```

Confirm after deploy: `from zoneinfo import ZoneInfo; ZoneInfo("Africa/Nairobi")`
must not raise.

### 5. No DB change needed — new settings

`business.timezone` (default `Africa/Nairobi`) and `business.week_starts_on`
(default `monday`) live in the existing `app_settings` JSON row and fall back
to their defaults, so production works untouched. Worth confirming in
**Settings → Business info → Reporting** after deploy, since they decide when
"Today", "This week" and "This month" begin.

---

## Later pages

Appended as each page is finished.
