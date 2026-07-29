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

Local dev returns the column plus `false: 44, true: 83`. If production differs
— missing, or mostly NULL — stop and say so; it needs its own backfill, which
does not exist yet.

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
