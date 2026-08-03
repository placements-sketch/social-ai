# Activity — Notifications and System Logs

One route, `/activity`, with two tabs. `/notifications` and `/logs` still exist
but only as redirects into it. The sidebar now links straight to `/activity`
with **no child link** — System Logs is a tab on this route, not a route of its
own, so a child entry could never highlight correctly. Same reason Settings and
AI & Automation lost theirs.

---

## 1. Who can see what

| Endpoint | admin | supervisor | agent |
|---|---|---|---|
| `GET /notifications` | 200 | 200 | 200 (own only) |
| `GET /logs/me` | 200 | 200 | 200 |
| `GET /logs/feed` | 200 | 200 | 200 (own conversations only) |
| `GET /logs/audit` | 200 | 200 | **403** |
| `GET /logs/system` | 200 | **403** | **403** |
| `POST /alerts/dismiss` | 200 | 200 | **403** |

Notifications are scoped by owner at the query (`filter_by(id=..., user_id=uid)`),
so nobody can read or mark another person's — verified: zero foreign owners in
any payload.

### The hole this audit found

`/logs/system` is admin-only because raw pipeline logs leak internals —
database hostnames, tokens, stack traces. But `/logs/feed` accepted
**`?raw=true`**, which opted out of the source allowlist, and nothing checked
the caller's role.

A supervisor was refused at `/logs/system` with a 403 and then got the identical
rows through the feed — 50 of them, including `integrations.shopify.token` and
`integrations.meta.legacy_credentials_used`.

`raw=true` is now admin-only. Non-admins have the flag **ignored** rather than
rejected, because the feed is the page's main content and a stray query
parameter shouldn't blank it. Agents were never exposed — conversation scoping
already limited them to their own rows.

| After the fix | rows outside the allowlist |
|---|---|
| admin | 11 (intended) |
| supervisor | 0 |
| agent | 0 |

---

## 2. Urgent notifications by email

**Yes, they send.** Urgent notifications are produced from four places —
`channels.py` (channel disabled, token expiring), `handoff.py` (escalations),
`routes.py`, and `services.py` — and each one triggers an email through Brevo.

Four things were wrong with that path.

### a. The email was sent before the transaction committed

`create_notification()` documents that *"the caller is responsible for the
commit"* — but it sent the email inside the function, before that commit. If the
caller's transaction then rolled back, the notification never existed and the
recipient had already been emailed about it. Verified: **1 email sent, 0 rows
saved.**

Emails are now queued on the session and flushed by an `after_commit` hook,
dropped on rollback. Nobody gets paged about something that didn't happen.

### b. The commit hook couldn't talk to the database

First attempt at the fix looked up the recipient inside `after_commit`. That
fails — SQLAlchemy refuses to emit SQL with the session in `committed` state
("this session is in 'committed' state; no further SQL can be emitted"). Worse,
it failed **silently**: the exception was caught and logged as a warning, so
urgent emails would simply have stopped.

The recipient and the full rendered message are now resolved *before* the
commit. The hook only performs the HTTP send — no database access at all.

### c. Escalating severity made the alert quieter

Coalescing merges a repeat notification into an existing unread one, keyed on
**type + resource — not severity**. So a situation that started as `info` and
escalated to `urgent` merged into the info row, **kept severity `info`**, and
sent no email. The event got quieter precisely as it got worse.

Severity now only ever ratchets upward, and crossing into `urgent` sends the
mail:

| Case | Email |
|---|---|
| info / warning | no |
| urgent | **yes** |
| first urgent with coalesce | **yes** |
| repeat urgent, same resource, within 5 min | no (deliberate — anti-spam) |
| urgent coalescing into an existing info row | **yes**, and the row becomes urgent |
| caller rolls back | no |

### d. The email's only button was dead

`FRONTEND_URL` is not set in this environment, and the template fell back to
`href="#"` — so the single call-to-action in an urgent email did nothing when
clicked. It now falls back through `FRONTEND_URL` → `PUBLIC_BASE_URL` →
`APP_BASE_URL`, deep-links to `/activity`, and if none are set it **drops the
button** rather than rendering a dead one.

The template also now HTML-escapes the title and body. Those carry
customer-supplied text — usernames, message excerpts — and were being
interpolated raw, which let a customer's message rewrite an email going to
staff.

> **Deploy note:** set `FRONTEND_URL` on Render to the frontend origin. It
> currently resolves to `PUBLIC_BASE_URL`, which is the API host.

---

## 3. The unread count was not the unread count

The bell badge and the page both read `unread_count` from the same endpoint —
but that count carried the **same `created_at` cutoff as the list**. The bell
polls with the 7-day default, so it was reporting *"unread in the last 7 days"*
while calling itself unread.

Measured on this database:

| User | badge said | actually unread |
|---|---|---|
| admin | 7 | **17** |
| supervisor | 6 | **16** |
| duck | 4 | **13** |
| agent | 2 | **11** |

The oldest unread is **53 days old** — and it is *"New escalation assigned to
you."* It had become invisible: past the badge's window, and past the page's
filter, which stopped at 30 days.

It also disagreed with the button meant to clear it — `mark_all_read` has never
been windowed, so it clears every unread row, including the ones the badge
refused to count.

Three changes:

- `unread_count` is now a true, unwindowed count. Unread is a **state**, not a
  time window.
- The endpoint also returns `unread_outside_window`, so the page can say *"10
  older unread aren't shown"* instead of silently dropping them.
- The days filter gained an **All** option — previously nothing older than 30
  days could be reached at all.

All four users now report the same number at every window setting.

---

## 4. What was already right

Worth recording, because the audit checked and found nothing to fix:

- The `Activity` tab wrapper filters tabs by role and falls back safely — a
  non-admin landing on `?tab=logs` from an old bookmark gets Notifications
  rather than a missing tab.
- `Notifications` and `Logs` both drop their own `max-width` when embedded, so
  the heading and content share one left edge. (Settings was the page that got
  this wrong.)
- `/alerts/dismiss` was already restricted to admins and supervisors — the
  guard reads `role not in {...}`, which an earlier grep of mine missed. Read
  before reporting.
- The alerts panel filters to **fault levels only** and groups by source: 378
  fault rows collapse to 13 distinct problems. Acknowledgement is a per-source
  **watermark**, not a dismissed-ID list, so a *fresh* failure from an
  already-acknowledged source alerts again.
- The activity feed uses an **allowlist** of sources, not a poller blocklist —
  excluding `%_poller%` still left the feed 84% engineering chatter.

---

## 5. Presentation

- `divide-gray-50` had no dark mapping (`-100` and `-200` did). It separates the
  System Logs rows, so in dark mode every log row was divided by a near-white
  `#f9fafb` hairline — the brightest thing on the page.
- `border-black` likewise: `bg-black` is remapped to the brand lime, so the
  active filter chip was a lime pill wearing a hard black outline.

---

## 6. Questions you might get

**"If an urgent thing happens, how do I know?"**
Three ways, in order of loudness: an email to your address, a toast in the app
if you have it open, and the bell badge. The email is queued and sent only once
the underlying event is committed.

**"Why doesn't every repeat urgent event email me?"**
Repeats of the same event on the same resource inside 5 minutes coalesce into
one notification and send one email. An event *escalating* into urgent always
emails, even if it merges into an existing row.

**"Why can supervisors see the audit log but not system logs?"**
The audit log is who-did-what — supervisors oversee agents, so it's theirs.
System logs are raw pipeline output containing tokens and stack traces, which
nobody outside engineering can act on.

**"Did this need a database change?"**
No. Every fix is code. There is no SQL step for this page.
