# Settings — how it works and how to defend it

The Settings page is the org-wide control panel: three tabs (**General**,
**Channels**, **Meta Diagnostics**), and inside General a rail of six sections.
This document explains what every control actually does, where the numbers come
from, and what was wrong before this audit.

---

## 1. Where settings live

There is exactly **one row** in the `app_settings` table (`id = 1`) holding a
single JSON blob. There is no column per setting, so adding a setting never
needs a migration — which is why nothing in this page's audit required a SQL
step.

Reads go through two functions in `app/settings.py`:

```python
get_settings()        # DEFAULTS with the stored blob layered on top
get_section("business")   # one section of the same
```

`DEFAULTS` is the source of truth for the shape and the fallback values. If the
row is missing, empty, or a key was never set, the default applies. That is why
the app behaves identically on a fresh install with an empty settings row.

**If asked "what happens if the settings row is corrupted?"** — `get_settings()`
catches the exception and returns a copy of `DEFAULTS`. The app degrades to
stock behaviour rather than erroring.

---

## 2. General → Handoff & assignment

| Control | What consumes it |
|---|---|
| Max open conversations per agent | `app/assignment.py` — agents at or above this are skipped for auto-assignment |
| Presence window | `app/assignment.py` — how recently an agent must have been active to count as present |
| Alert when unclaimed for | `app/assignment.py` — feeds the unclaimed-queue cron (runs every 15 min) |
| Flag agent's chat after | `app/logs.py` — drives the "Needs Attention" panel |
| Default handoff message | Sent to the customer on escalation |
| **Auto-resolve silent chats after** | `app/cron_routes.py` `/auto-resolve` |
| **Re-open a resolved chat within** | `app/services.py` |

### The two settings that were invisible

The last two rows were **live behaviour with no UI**. A nightly job was closing
conversations after 14 days of silence, and a customer replying within 24 hours
of a resolve was re-opening the old thread instead of starting a new one — both
real rules acting on real conversations, both governed by a constant nobody
could read off the page. They are now editable, with the same bounds enforced on
the server.

**Auto-resolve is deliberately one-sided.** It only closes conversations where
**we** spoke last:

```sql
JOIN LATERAL (
    SELECT direction FROM messages
     WHERE conversation_id = c.id
     ORDER BY created_at DESC LIMIT 1
) last_msg ON true
WHERE ... AND last_msg.direction = 'outbound'
```

If the *customer* spoke last we still owe them a reply, and auto-closing that
would bury a dropped customer instead of finishing a conversation. Setting it to
`0` disables auto-resolve entirely.

**The re-open window** exists because a customer replying minutes after you
resolved their chat almost always means it was resolved too early — same
subject, same session. Weeks later it is genuinely a new enquiry. `0` means
every reply after a resolve starts a fresh thread.

---

## 3. General → Business info (the widest blast radius on the page)

`timezone` and `week_starts_on` decide what "Today", "This week" and "This
month" mean on **both the Dashboard and Analytics**. Timestamps are stored as
naive UTC; without a business timezone, "today" would start at 3am local.

This was verified by moving the setting and watching the windows move:

| Timezone set to | UTC offset applied | Week begins |
|---|---|---|
| Africa/Nairobi | +3:00 | — |
| UTC | 0:00 | — |
| America/New_York | −4:00 | — |
| `Not/AZone` (invalid) | falls back to +3:00 | — |
| week starts **monday** | | 03 Aug |
| week starts **sunday** | | 02 Aug |

Two different behaviours on an invalid zone, deliberately:

- **At read time** (`business_timezone()`) an unknown zone silently falls back
  to Africa/Nairobi, so a bad value degrades instead of 500-ing Analytics.
- **At write time** (`_validate_patch`) it is **rejected with an error**. An
  admin who fat-fingers a zone should be told, not left wondering why the
  Dashboard's "Today" never moved.

---

## 4. General → Integrations (the Diagnostics data)

### What was wrong

"Connected" was computed as `any(last_sync.values())` — meaning *a sync
succeeded at some point in history*. On the development database the newest
successful sync is **32 days old**, and the card still displayed a green
**Connected** badge with no warning. `recent_failed` looked at a **single** row
(the newest job), so one success sitting on top of a week of failures reported a
clean bill of health.

A diagnostics panel that can only ever say "fine" is worse than not having one,
because it actively reassures you.

### What it does now

Syncs are scheduled **every 3 hours** (`.github/workflows/daily-sync.yml`). The
panel allows **three missed cycles (9 hours)** before calling a feed stale —
enough to ride out one transient failure and its retry without flapping.

- `stale_kinds` — which of products / orders / customers are behind, **by name**
- `failed_recently` — failures in the last **24 hours**, not one row
- The badge now reads **Needs attention**, and the card says which feed is late

Against the real database this now correctly reports all three feeds stale.

### The Meta card had the same flaw

It *displayed* `token_expires_at` but the expiry played no part in the verdict —
a token two days from death still showed green. Instagram tokens last 60 days
and a **daily** cron refreshes them, so anything inside a week means that
refresh has been failing for days and messaging is about to stop dead. The card
now warns at ≤7 days and states the day count.

### The tab rail carries the answer

The rail was six identical buttons. To learn that Shopify hadn't synced in a
month you had to guess which tab to open. A stale feed or a dying token is
exactly what you came here to find, so it now shows an amber dot on the
Integrations tab — the navigation tells you there is a problem instead of hiding
it behind itself.

---

## 5. Notifications

Discord alerts are real and wired: `app/cron_routes.py` raises warnings and
`app/sync_jobs.py` raises failures, both filtered through
`discord_min_severity`. The **Send test** button posts a real message, so you
can prove the webhook works without waiting for a failure.

---

## 6. Validation — why the server checks what the form already checks

The form range-checks every number before sending. That is not a boundary: the
`PATCH /api/settings` route accepts any JSON, and each of these values is read
back through `int()` **inside a background job** — auto-assignment, the
unclaimed sweep, the auto-resolve cron. A string `int()` cannot parse does not
fail where an admin would see it; it fails later, in a job nobody is watching,
and assignment quietly stops.

Bounds now live in one table in `app/settings.py`:

```python
NUMERIC_BOUNDS = {
    ('handoff', 'max_agent_load'):          ('Max load', 1, 100, None),
    ('handoff', 'presence_window_seconds'): ('Presence window', 30, 3600, None),
    ('handoff', 'unclaimed_alert_minutes'): ('Unclaimed alert', 1, 1440, None),
    ('handoff', 'agent_waiting_minutes'):   ('Agent wait flag', 1, 1440, None),
    ('handoff', 'auto_resolve_days'):       ('Auto-resolve', 0, 365, 'disables auto-resolve'),
    ('conversations', 'reopen_resolved_within_hours'):
                                            ('Re-open window', 0, 720, 'always starts a new chat'),
}
```

Values are also **coerced** — `"12"` is stored as the integer `12`, not the
string — so nothing downstream has to guess. `True` is rejected explicitly,
because `bool` is a subclass of `int` in Python and would otherwise sail through
as `1`.

All twelve validator cases and six through-the-route cases pass.

---

## 7. Permissions — the recurring finding

The question asked on every page of this audit is **"is the button hidden, or is
the action prevented?"** Settings produced the fourth and fifth instances.

### `app/channels.py` had no role checks at all

All four routes carried `@jwt_required()` and nothing else. Proven by calling
them as each role:

| Role | GET list | PATCH | POST test |
|---|---|---|---|
| admin | 200 | 200 | 200 |
| supervisor | 200 | **200** | **200** |
| agent | **200** | **200** | **200** |

An **agent could disable Instagram DMs entirely** — the widest switch on the
platform. It stops the AI answering on that channel *and* takes the channel down
with it. After the fix:

| Role | GET list | PATCH | POST test |
|---|---|---|---|
| admin | 200 | 200 | 200 |
| supervisor | 200 | 403 | 403 |
| agent | 403 | 403 | 403 |

Reads are allowed for supervisors (they oversee the floor); writes are admin.
The guard helpers mirror `app/ai_settings.py` deliberately — one rule, expressed
identically, so the two cannot drift.

### Deactivating a user did not end their session

This is the more serious one, and it is app-wide rather than Settings-specific.

Access tokens live **24 hours** and carry the role baked in at login. Nothing in
the request path looked at `status`. Proven with a throwaway admin account:

```
--- after DEACTIVATING the account (same token) ---
  /api/settings            200
  /api/channels            200
  /api/meta-test/profile   200
```

Deactivation only blocked the *next login*. The live token kept full admin
access for up to a day — and deactivation is the primary offboarding control on
the Users page.

Separately, `app/meta_test.py` read the role from the **JWT claim** instead of
the database, so demoting an admin left them with admin access to routes that
proxy the Graph API with our page token and can rewrite webhook subscriptions.
Every other module resolved the role against `AuthUser`, so demotion took effect
immediately *everywhere except there*.

Both are fixed by a single hook in `app/__init__.py`, so the rule holds in one
place rather than needing a status check added to every route and remembered for
every route added later:

```python
@jwt.token_in_blocklist_loader
def account_no_longer_active(jwt_header, jwt_data):
    user = AuthUser.query.get(int(jwt_data.get('sub')))
    return (user is None) or (user.status != 'active')
```

After the fix:

```
--- after DEACTIVATING the account ---   all three -> 401
--- after DEMOTING admin -> agent  ---   all three -> 403
```

**Machine callers are unaffected**: cron authenticates with an `X-Cron-Secret`
header, not a JWT, and there are no `jwt_required(optional=True)` routes. A
regression sweep of 8 real endpoints across all three roles produced **zero**
incorrect 401s.

---

## 8. Presentation fixes

- **Nine hand-rolled panels** used `bg-white rounded-2xl border border-gray-200`
  with zero uses of the shared `card` class, so none of the glass tuning reached
  this page. All nine now use `card` — future tuning of that surface reaches
  Settings for free instead of needing nine more edits.
- **`?tab=diagnostics` silently opened General.** The wrapper hardcoded
  `params.get('tab') === 'channels' ? 'channels' : 'settings'`, so the third tab
  could not be linked or bookmarked, and a fourth would have failed the same way
  without a word. It is now derived from the `TABS` list.
- **`bg-gray-900` had no dark-mode mapping.** Its *hover* state did, but the
  resting state did not — and `#111827` on the dark card surface (~`#101114`) is
  about **1.05:1**. The white label stayed readable but the chip's *shape*
  disappeared, so nothing showed which period was selected on Dashboard,
  Analytics or Messages until you hovered it. Now mapped to the brand colour,
  matching `bg-black`, which these same buttons already pair with.
  - **Exception:** paired with `text-gray-100` it is not a chip but a deliberate
    dark code surface (the raw-JSON dumps in Meta Diagnostics). Those were
    already correct and the new rule would have turned them lime with pale grey
    text. They are explicitly kept dark.
- `text-red-900` titled the **"Reset all settings"** block while sitting on a
  `bg-red-50` panel that *is* remapped — so the heading of the most destructive
  control on the page was near-black on near-black. Fixed, along with the
  `-300` border shades.

---

## 9. Questions you might get

**"How do you know the timezone setting actually works?"**
It was changed to four values and the resulting reporting windows measured. The
UTC offset moved with it (+3:00 → 0:00 → −4:00), the week start moved from 3 Aug
to 2 Aug, and an invalid zone fell back safely.

**"Why allow reads for supervisors but not agents?"**
Supervisors oversee the floor and need to see whether a channel is healthy;
agents work inside conversations and never need the channel roster. Writes are
admin for both.

**"Why is `recent_failed` still in the API response?"**
Backwards compatibility — but it now means "something is wrong right now",
which is what every caller already assumed it meant.

**"Did any of this need a database change?"**
No. Every setting lives in the existing JSON blob and every permission fix is
code. There is no SQL step for this page.

---

# Addendum — findings after the original pass

Everything above still holds. These came out of later work on the same page and
change some of its conclusions.

## 1. The Discord "not delivering" badge was wrong

The header badge I added judged delivery from the form field alone. But
`discord_config()` resolves the webhook from **settings OR the
`DISCORD_WEBHOOK_URL` environment variable**, and this deployment sets it by
env — so the field is legitimately blank while alerts are going out fine.

The badge would have reported "not delivering" on a healthy system, which is
the same category of mistake as the diagnostics card that could only say "fine",
just inverted.

`GET /api/settings` now returns a `resolved` block computed server-side:

```json
"resolved": { "discord_delivering": true, "discord_url_source": "env" }
```

The page reports that instead of re-deriving it badly, and the webhook field
says *"Using the server's environment-configured webhook"* so an empty box does
not read as broken.

**The lesson worth keeping:** a UI must not re-implement a rule the server
already owns. It had two of the three inputs and got the answer wrong.

## 2. CORS falls back instead of failing closed

`CORS_ORIGINS` unset meant every browser request was rejected, and the only
signal was one warning line at boot. It now falls back to `FRONTEND_BASE_URL` /
`FRONTEND_URL`, and logs which source it used:

```
CORS origins (FRONTEND_BASE_URL / FRONTEND_URL): https://…
```

If nothing resolves at all, that is now an **error**, not a warning — an API
that rejects every request deserves louder than a warning.

## 3. Channels that cannot send cannot be enabled

`facebook_dm`, `facebook_comment`, `whatsapp` and `tiktok_*` have stub
dispatchers: inbound is accepted and stored, replies are logged and never
delivered. Enabling one means customers message a channel nobody can answer.

`SENDABLE_CHANNELS` now lives beside `_dispatch_reply` — the code that actually
knows — and is imported by `channels.py`. `PATCH /channels/<id>` returns **409**
for anything outside it, and the toggle renders as unavailable rather than
erroring on click. `Channel.to_dict()` exposes `can_send` so the UI reads the
answer rather than hardcoding a list that would drift.

Existing rows already enabled in the database are a separate matter — see
**Step 18** in `PRODUCTION_CHANGES.md`.

## 4. Two more settings surfaces gained real guards

Both were the same shape as the channels finding in the original pass — the
link was hidden, the action was not prevented:

- **`app/customers.py`** — ten routes with `@jwt_required()` and no role check.
  Any agent could read the full customer list with gross lifetime spend, or
  `POST /customers/sync` to start a full Shopify sync. Reads are now
  admin+supervisor, writes admin.
- **`/logs/feed?raw=true`** — opted out of the source allowlist with no role
  check, handing a supervisor the same rows `/logs/system` refuses them. Now
  admin-only, and *ignored* rather than rejected for others so a stray query
  parameter cannot blank the page.

## 5. Verify what is resolved, not what is stored

The pattern behind items 1 and 2, and worth stating on its own: several bugs on
this page came from a caller re-deriving a value the server resolves from
multiple sources. Settings + environment, form field + env fallback, requested
scopes + granted scopes. In each case the partial view looked authoritative and
was wrong.

Where a value has more than one source, the resolver returns the answer and
callers report it.
