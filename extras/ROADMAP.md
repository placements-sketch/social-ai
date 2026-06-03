# Social AI Assistant — Build Roadmap

---

## Phase 1 — PostgreSQL Database

- [ ] Install PostgreSQL locally (postgresql.org)
- [ ] Create database: `createdb social_ai_db`
- [ ] Update `DATABASE_URL` in `.env`
- [ ] Install Flask-Migrate: `pip install flask-migrate`
- [ ] Wire Flask-Migrate into `app/__init__.py`
- [ ] Run `flask db init` → `flask db migrate` → `flask db upgrade`
- [ ] Send a test webhook POST and confirm rows appear in DB

---

## Phase 2 — OpenAI

- [ ] Get API key from platform.openai.com
- [ ] Paste key into `.env` as `OPENAI_API_KEY`
- [ ] Set `USE_MOCK_AI = False` in `app/ai/generator.py`
- [ ] Test a live AI reply end-to-end
- [ ] Add conversation memory — fetch last N messages from DB and pass as chat history to OpenAI
- [ ] Tune the system prompt via the AI Settings page

---

## Phase 3 — Shopify

- [ ] Shopify Admin → Settings → Apps → Develop apps → create app
- [ ] Grant `read_products` and `read_inventory` scopes
- [ ] Copy Admin API access token → `.env` as `SHOPIFY_ACCESS_TOKEN`
- [ ] Implement `_real_get_product_info()` in `app/integrations/shopify.py`
- [ ] Test product fetch by keyword
- [ ] Add product caching to `products_cache` table (1hr TTL)

---

## Phase 4 — Odoo

- [ ] Get Odoo URL, database name, username, password → `.env`
- [ ] Create a read-only API user in Odoo (access to `stock.quant` only)
- [ ] Implement `_real_get_stock_level()` in `app/integrations/odoo.py`
- [ ] Test stock query by product name
- [ ] Add short-lived stock cache (5–10 min TTL) to handle Odoo slowness
- [ ] Add fallback to cached value on Odoo timeout

---

## Phase 5 — Instagram + Facebook Webhooks

- [ ] Install ngrok for local development (`ngrok http 5000`)
- [ ] Create app in Meta Developer Console (developers.facebook.com)
  - [ ] Add Messenger product
  - [ ] Add Instagram product
  - [ ] Add Webhooks product
- [ ] Register webhook URLs in Meta Developer Console
  - [ ] `https://yourdomain.com/webhook/instagram`
  - [ ] `https://yourdomain.com/webhook/facebook`
  - [ ] `https://yourdomain.com/webhook/facebook/comments`
- [ ] Set `META_VERIFY_TOKEN` in `.env` and in Meta Developer Console
- [ ] Subscribe to webhook events: `messages`, `messaging_postbacks`, `feed`
- [ ] Connect Instagram Business account to Facebook Page
- [ ] Generate Page Access Token → `.env` as `META_PAGE_ACCESS_TOKEN`
- [ ] Implement `_real_send_instagram()` in `app/integrations/meta.py`
- [ ] Implement `_real_send_facebook()` in `app/integrations/meta.py`
- [ ] Test full loop: send DM → AI replies back

---

## Phase 6 — WhatsApp

> ⚠ Start the Meta business verification process early — approval takes days.

- [ ] Apply for WhatsApp Business API access in Meta Developer Console
- [ ] Complete Meta business verification
- [ ] Register a phone number (must not already be on WhatsApp)
- [ ] Copy `WHATSAPP_PHONE_NUMBER_ID` → `.env`
- [ ] Submit message templates in Meta Business Manager and wait for approval
- [ ] Implement `_real_send_whatsapp()` in `app/integrations/meta.py`
- [ ] Register webhook URL: `https://yourdomain.com/webhook/whatsapp`
- [ ] Test full loop: send WhatsApp message → AI replies back

---

## Phase 7 — Wire Frontend to Real Backend

- [ ] Add Flask API endpoints:
  - [ ] `GET /api/stats`
  - [ ] `GET /api/conversations`
  - [ ] `GET /api/conversations/<id>`
  - [ ] `GET /api/products`
  - [ ] `GET /api/logs`
  - [ ] `GET /api/ai-settings`
  - [ ] `POST /api/ai-settings`
  - [ ] `POST /api/automation-rules`
- [ ] Replace mock data in `frontend/src/data/mock.js` with real `fetch()` calls
- [ ] Add loading states and error handling to each page
- [ ] Add real-time updates to Dashboard and Messages (Server-Sent Events or WebSocket)

---

## Phase 8 — Production Deployment

- [ ] Choose hosting platform (Railway / Render / DigitalOcean)
- [ ] Set up production PostgreSQL database on host
- [ ] Switch from `flask run` to Gunicorn: `gunicorn "app:create_app()" -w 4`
- [ ] Set all `.env` values as environment variables on host
- [ ] Run `flask db upgrade` on production DB
- [ ] Build frontend: `npm run build`
- [ ] Deploy frontend (Vercel recommended) or serve `dist/` from Flask
- [ ] Point domain to server
- [ ] Confirm SSL certificate is active (HTTPS)
- [ ] Update all webhook URLs in Meta Developer Console to production domain
- [ ] Smoke test every channel end-to-end on production

---

## Recommended Order

```
Phase 1 → 2 → 3 → 4 → 5 → 7 → 8 → 6
```
Start WhatsApp (Phase 6) verification in parallel with Phase 3 — don't wait.

---
---

# What You Need From the Company

## Credentials & Access

| What | Where to get it | Notes |
|---|---|---|
| Shopify store URL | Shopify Admin → Settings → Domains | e.g. `yourstore.myshopify.com` |
| Shopify Admin API token | Shopify Admin → Settings → Apps → Develop apps | Needs `read_products`, `read_inventory` scopes |
| Odoo instance URL | IT / whoever manages Odoo | e.g. `https://yourcompany.odoo.com` |
| Odoo database name | IT / Odoo admin | Found in Odoo Settings |
| Odoo username + password | IT / Odoo admin | Create a dedicated read-only API user |
| Facebook Page admin access | Social media manager | Must be Admin role on the Page |
| Instagram Business account | Social media manager | Must be linked to the Facebook Page |
| Meta Developer Console access | IT or create at developers.facebook.com | Needs to be linked to the company Facebook account |
| WhatsApp phone number | IT / company SIM | Must be a number NOT already registered on WhatsApp |
| OpenAI API key | platform.openai.com | Company pays per token used |
| Production domain name | IT / whoever manages DNS | e.g. `ai.yourcompany.com` |
| Server / hosting account | IT or you set it up | Railway / Render / DigitalOcean |

---

## What Costs Money

| Service | Cost | Notes |
|---|---|---|
| OpenAI API | ~$0.01–0.03 per conversation | GPT-4o; budget ~$20–50/month for moderate volume |
| Shopify | Already paying | Just needs API access enabled, no extra cost |
| Odoo | Already paying | Just needs API user created, no extra cost |
| Meta (Instagram/Facebook) | Free | Graph API is free |
| WhatsApp Business API | Free for inbound + first 1000 conversations/month | Outbound template messages cost ~$0.005 each after free tier |
| Hosting (backend) | $5–20/month | Railway or Render free tier works for MVP |
| Hosting (frontend) | Free | Vercel free tier is fine |
| Domain | $10–15/year | If not already owned |
| PostgreSQL | Free | Included with most hosting platforms |

---

## What You Need to Know From the Business

- [ ] What is the brand's Instagram handle?
- [ ] What Facebook Page should the bot reply from?
- [ ] What WhatsApp number should customers message?
- [ ] What are the business hours? (for escalation routing)
- [ ] What is the fallback message when AI fails?
- [ ] What is the out-of-stock message?
- [ ] What tone should the AI use? (already configurable in AI Settings)
- [ ] Are there product categories or keywords the AI should never discuss?
- [ ] Who gets notified when a human override is needed?
- [ ] What is the max response time SLA? (affects rate limit settings)