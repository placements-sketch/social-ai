# Social AI Assistant — Architecture & Contract

> **Purpose of this file.** Single source of truth for the project's structure, data model,
> API contract, and conventions. Paste it (or sync it) at the start of any session to orient
> quickly. When a contract changes, change it *here first*, then update the code to match.
> This file documents the **actual current state of the repo**, including known mismatches
> that still need reconciling — those are flagged with ⚠️.

_Last updated from a repo sync on 2026-05-28. Re-sync and update the dated sections when code changes._

---

## 1. What this is

A Flask + React app for managing customer conversations across social channels
(Instagram, WhatsApp, Facebook, TikTok) with AI-generated replies, a rules engine,
and a human-override inbox.

### Tech stack
- **Backend:** Flask (app-factory pattern), SQLAlchemy, Flask-Migrate, Flask-JWT-Extended, Flask-CORS, bcrypt
- **DB:** PostgreSQL (SQLite fallback for dev via `DATABASE_URL`)
- **Frontend:** React, React Router, Tailwind CSS, Vite, lucide-react, clsx
- **AI:** Anthropic Claude API (`config.CLAUDE_MODEL`)
- **Integrations:** Meta Graph API (IG/WA/FB), Shopify (products + stock), TikTok, Odoo (stock)

---

## 2. Repo layout (synced folders)

```
app/
  __init__.py        # App factory: create_app(), db/migrate/jwt instances, CORS, blueprint registration
  config.py          # (root-level config.py) env-driven Config class
  models.py          # SQLAlchemy models (10 tables)
  auth.py            # auth_bp  — /api/auth/*  (login, signup, verify, users CRUD, audit-logs)
  messages.py        # messages_bp — /api/conversations/*  (inbox)
  routes.py          # bp (main) — webhook receivers for Meta channels -> process_message()
  services.py        # process_message(): intent -> fetch context -> generate -> dispatch -> persist
  router.py          # ⚠️ LEGACY single-intent detector (see §7) — not used by services.py
  ai/
    generator.py     # generate_reply(...) — Claude call (referenced by services.py)
  integrations/
    meta.py          # send_instagram_reply / send_whatsapp_reply / send_facebook_reply (USE_MOCK=True)
    shopify.py       # get_product_info / get_stock_level
    tiktok.py        # send_tiktok_reply
  utils/
    intent.py        # detect_intents() multi-intent + intents_to_label()
    logger.py        # log_event(level, source, message) -> console + logs table (best-effort)
database/
  schema.sql         # full PostgreSQL DDL (option B: run directly)
  auth_migration.sql # auth_users + audit_logs + seed test users
frontend/src/
  api/messages.js    # fetch wrapper for the inbox endpoints
  pages/Messages.jsx # inbox UI
  data/mock.js       # (referenced historically) mock conversations
```

> **Note on freshness:** the GitHub connector provides a *snapshot* from the last sync, not a
> live view. Before relying on file contents in a session, click **Sync now** in the project.

---

## 3. Data model (authoritative: `app/models.py` + `database/schema.sql`)

### Two distinct "user" concepts — do not conflate
- **`auth_users`** (`AuthUser`): internal staff who log into the dashboard. Roles: `admin | agent | supervisor`. Status: `active | inactive | suspended`.
- **`users`** (`User`): external **customers** who message in. Identified by `(external_id, channel)` — the *same human* on IG and WhatsApp is **two rows**.

### Tables
| Table | Model | Notes |
|-------|-------|-------|
| `auth_users` | `AuthUser` | bcrypt `password_hash`; `to_dict()` exists |
| `audit_logs` | `AuditLog` | staff action trail; written by `log_audit()` in `auth.py` |
| `users` | `User` | customers; unique `(external_id, channel)` |
| `conversations` | `Conversation` | one thread = one customer on one channel |
| `messages` | `Message` | `direction` inbound/outbound; `sender` ai/human/system |
| `products_cache` | `ProductCache` | Shopify metadata; **never** store stock here |
| `stock_cache` | `StockCache` | short-TTL Odoo stock |
| `ai_settings` | `AISettings` | single active row (id=1) |
| `automation_rules` | `AutomationRule` | IF/THEN rules; `trigger_config`/`action_config` JSON |
| `logs` | `Log` | pipeline audit trail (separate from `audit_logs`) |

### Key conventions
- **Channel** values (used everywhere — DB column is `channel`):
  `instagram_dm | instagram_comment | whatsapp | facebook_dm | facebook_comment | tiktok_dm | tiktok_comment`
- **Conversation.status:** `active | resolved | human_override | pending`
- **AI enabled** is tracked at *two* levels: `User.ai_disabled` (per customer) and `Conversation.ai_enabled` (per thread). The inbox toggle operates on the **conversation**.

> ⚠️ **`AISettings` references OpenAI/`gpt-4o`** in column comments and the `model` default,
> but the project standardized on Claude (`config.CLAUDE_MODEL`). Reconcile the default and
> comments when the AI Settings page is built.

---

## 4. API contract

Base URL (frontend default): `http://127.0.0.1:5000/api` (`VITE_API_BASE` overrides).
All non-auth endpoints require `Authorization: Bearer <JWT>`.

### 4.1 Auth (`app/auth.py`, prefix `/api/auth`) — STABLE
| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/login` | `{email, password}` | `{token, user}` |
| POST | `/signup` | `{email, password, full_name, role}` (admin only) | `{user}` |
| GET | `/verify` | — | user dict |
| POST | `/logout` | — | `{message}` |
| GET | `/me` | — | user dict |
| GET | `/users` | — (admin) | `{users}` |
| GET | `/users/<id>` | — (admin) | user dict |
| PUT | `/users/<id>` | `{full_name?, role?, status?}` (admin) | `{user}` |
| DELETE | `/users/<id>` | — (admin) | `{message}` |
| GET | `/audit-logs` | `?user_id&action&limit&offset` (admin) | `{logs, total, limit, offset}` |

### 4.2 Inbox / Messages — ⚠️ **CONTRACT IN CONFLICT** (see §6)

This is the area that needs reconciling. The three layers currently disagree. The
**canonical contract below is the PROPOSED target** — code does not yet fully match it.

**Decisions (proposed canonical):**
- Pagination: **`page` / `per_page`** (offset-style, friendly convention). Response includes `total`, `page`, `per_page`.
- Channel filter param: **`channel`** (mirror the DB column; no `platform` on the wire).
- List response: `{ conversations: [...], total, page, per_page }`
- Single conversation: returned **wrapped** as `{ conversation: {...} }`.
- Send reply: `POST /conversations/<id>/messages` with `{ content, sender }`, returns the created message (+ updated conversation).

| Method | Path | Params / Body | Returns (canonical) |
|--------|------|---------------|---------------------|
| GET | `/conversations` | `?page&per_page&channel&status&search` | `{conversations, total, page, per_page}` |
| GET | `/conversations/<id>` | — | `{conversation: {..., messages: [...]}}` |
| GET | `/conversations/<id>/messages` | — | `{messages}` |
| POST | `/conversations/<id>/messages` | `{content, sender}` | `{message, conversation}` |
| PATCH | `/conversations/<id>` | `{status?}` | `{conversation}` |
| PATCH | `/conversations/<id>/ai` | `{ai_enabled}` | `{conversation}` |
| PATCH | `/conversations/<id>/read` | — | `{conversation}` |

### 4.3 Webhooks (`app/routes.py`, blueprint `main`) — STABLE
- `GET /` health check
- `GET /webhook/{instagram,whatsapp,facebook}` — Meta verification challenge (`hub.challenge`)
- `POST /webhook/instagram`, `/webhook/instagram/comments`, `/webhook/whatsapp`, `/webhook/facebook`, `/webhook/facebook/comments`
- All inbound POSTs funnel into `services.process_message(message, user_id, channel)`.

---

## 5. AI / message pipeline (`app/services.py`)

`process_message(message, user_id, channel)`:
1. `detect_intents(message)` → list (multi-intent), via `app/utils/intent.py`
2. Fetch context: Shopify product+stock for product/price/stock intents; flag delivery/order-status
3. `ai.generator.generate_reply(message, intents, context_data, channel)`
4. `_dispatch_reply(...)` → correct `integrations` sender (currently **mocked**, `meta.USE_MOCK=True`)
5. Persist inbound + outbound `Message` rows; intents stored pipe-joined (`a|b|c`) via `intents_to_label`

---

## 6. ⚠️ Known contract mismatch — Inbox (the thing to fix next)

As of the last sync, the three layers were written against different assumptions:

| Layer | Pagination | Channel param | Reply endpoint | Single-conv shape |
|-------|-----------|---------------|----------------|-------------------|
| `frontend/src/api/messages.js` (repo) | `page` / `per_page` | `channel` | `POST .../messages` `{content, sender}` | reads `data.conversation` |
| `frontend/src/pages/Messages.jsx` (repo) | calls `listConversations({platform, search})` | `platform` | — | `data.conversation` |
| `app/messages.py` (repo) | `limit` / `offset` | `platform` (filters `Conversation.channel`) | `POST .../reply` `{text}` | wraps `{conversation}` |

**Resolution plan:** adopt §4.2 canonical contract. Concretely:
- Backend `list_conversations`: switch `limit/offset` → `page/per_page`, rename `platform` → `channel`, return `page/per_page` in body.
- Backend reply: standardize on `POST /conversations/<id>/messages` `{content, sender}` (retire `/reply` `{text}` or keep as alias).
- `Messages.jsx`: call `listConversations({ page, per_page, channel, status })`; the component may keep an internal `platform` label but must send `channel`.
- `api/messages.js`: already close to canonical; align `toggleAI` to the dedicated `PATCH .../ai` endpoint rather than overloading status.

**Pagination note:** `page/per_page` is the chosen convention for now. The conversation list is
really an infinite-scroll feed ordered by `last_message_at`; at higher volume, migrate the list
endpoint (only) to keyset/cursor pagination for stable, index-seek performance. Contained change.

---

## 7. ⚠️ Duplicate intent systems

There are **two** intent detectors with different label vocabularies:
- `app/utils/intent.py` — `detect_intents()` (multi-intent). **This is the one `services.py` uses.**
  Labels include: `greeting, stock_inquiry, product_inquiry, price_inquiry, delivery_inquiry, order_status, complaint, unknown`.
- `app/router.py` — `detect_intent()` (single-intent, regex). Different labels (`price_query`, `stock_query`, `escalation`, `ai_fallback`) and contains a typo (`goo morning`). **Appears unused by the pipeline.**

`automation_rules` seed data references intents like `complaint` and `order_status` (the `utils/intent.py`
vocabulary). **Recommendation:** treat `utils/intent.py` as canonical; delete or refactor `router.py`
to avoid drift. Pick one label set and document it here.

---

## 8. Conventions & gotchas

- **JWT storage key (frontend):** `localStorage['authToken']` (per repo `api/messages.js`). Use this key everywhere.
- **Auth identity:** JWT `identity` is `AuthUser.id`; `get_jwt_identity()` returns it.
- **Two log tables:** `audit_logs` (staff actions, via `log_audit`) vs `logs` (pipeline events, via `log_event`). Don't mix.
- **Secrets:** everything comes from env (`config.py`). Ensure `.env` is gitignored and never committed — the GitHub sync reads file contents verbatim.
- **CORS:** currently `origins: "*"` for `/api/*`. Tighten before production.
- **Mock flags:** `integrations/meta.py` has `USE_MOCK = True`. Real sends raise `NotImplementedError` until credentials + `requests` calls are added.
- **Test users** (`database/auth_migration.sql`): `admin@company.com / admin123`, `agent@company.com / agent123`, `supervisor@company.com / supervisor123`. Dev only.

---

## 9. TODO (priority order)
1. **Messages/Inbox** — reconcile the §6 contract, then verify end-to-end. ← current focus
2. Channels page — connect/disconnect social accounts
3. Products page — Shopify sync + inventory display
4. AI Settings & Automation — rules engine backend
5. Analytics & Logs — surface `logs` / `audit_logs`
6. AI message generation — finish `ai/generator.py` Claude integration
7. Channel integrations — real Meta webhooks/sends, Shopify, TikTok (flip `USE_MOCK`)
8. Testing & deployment

---

## 10. How to keep this doc honest
- Change the **contract here first**, then the code. PRs that change an endpoint must update §4.
- When you resolve a ⚠️, delete the warning and move the fact into the stable section.
- Re-sync the GitHub connector before a session that depends on current code, and bump the date in the header.