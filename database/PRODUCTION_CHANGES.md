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

Run steps 1 → 6 in order. Steps 5 and 6 are not database changes.

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
```

Local dev: 25 / 0 / 0 rows, moving the distribution from `false: 44, true: 83`
to `false: 19, true: 108`. Success Rate went 18.8% → 21.9%, and WhatsApp and
Facebook went from "AI off here" to 100% answered.

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

### Step 6 — Not database changes

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
