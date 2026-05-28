-- =============================================================================
-- Social AI Assistant — PostgreSQL Schema
-- =============================================================================
-- Two ways to use this file:
--
-- Option A (recommended): Flask-Migrate
--   pip install -r requirements.txt
--   flask db init
--   flask db migrate -m "initial schema"
--   flask db upgrade
--
-- Option B: Run this SQL file directly
--   psql -U postgres -d social_ai_db -f database/schema.sql
--   (or paste into pgAdmin / TablePlus / DBeaver query window)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- USERS
-- One row per unique customer per channel.
-- The same real person on Instagram and WhatsApp = two rows (different IDs).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,

    -- Platform-specific user ID (Instagram PSID, WhatsApp phone number, etc.)
    external_id      VARCHAR(128)  NOT NULL,

    -- Channel this user came from
    -- Values: instagram_dm | instagram_comment | whatsapp | facebook_dm | facebook_comment
    channel          VARCHAR(32)   NOT NULL,

    -- Display name from the platform (optional)
    name             VARCHAR(128),

    -- Profile picture URL (optional)
    avatar_url       VARCHAR(512),

    -- True if a human agent has taken over this user's conversations
    is_human_handled BOOLEAN       NOT NULL DEFAULT FALSE,

    -- True if AI auto-reply is disabled for this user
    ai_disabled      BOOLEAN       NOT NULL DEFAULT FALSE,

    created_at       TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP     NOT NULL DEFAULT NOW(),

    -- Same external_id can exist on different channels (e.g. same person on IG + WA)
    CONSTRAINT uq_user_external_channel UNIQUE (external_id, channel)
);

CREATE INDEX IF NOT EXISTS idx_users_channel ON users (channel);


-- ─────────────────────────────────────────────────────────────────────────────
-- CONVERSATIONS
-- Groups messages into threads. One conversation = one continuous chat session
-- with a user on a specific channel.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Denormalised for fast inbox queries without joining users
    channel         VARCHAR(32)   NOT NULL,

    -- Conversation status
    -- Values: active | resolved | human_override | pending
    status          VARCHAR(32)   NOT NULL DEFAULT 'active',

    -- Whether AI is enabled for this specific conversation
    ai_enabled      BOOLEAN       NOT NULL DEFAULT TRUE,

    -- Cached last message for inbox list display
    last_message     TEXT,
    last_message_at  TIMESTAMP,

    -- Count of unread inbound messages
    unread_count    INTEGER       NOT NULL DEFAULT 0,

    created_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id  ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_channel  ON conversations (channel);
CREATE INDEX IF NOT EXISTS idx_conversations_status   ON conversations (status);
CREATE INDEX IF NOT EXISTS idx_conversations_updated  ON conversations (updated_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- MESSAGES
-- Every individual message — inbound from customer or outbound from AI/agent.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS messages (
    id                  SERIAL PRIMARY KEY,
    conversation_id     INTEGER       NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id             INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Which channel this message belongs to
    channel             VARCHAR(32)   NOT NULL,

    -- inbound = from customer, outbound = from AI or human agent
    direction           VARCHAR(8)    NOT NULL CHECK (direction IN ('inbound', 'outbound')),

    -- Who sent the outbound message: ai | human | system
    sender              VARCHAR(16),

    -- The actual message text
    content             TEXT          NOT NULL,

    -- Detected intent for inbound messages
    -- Values: greeting | price_inquiry | stock_inquiry | product_inquiry | order_status | complaint | unknown
    intent              VARCHAR(64),

    -- Product keyword extracted from this message
    product_keyword     VARCHAR(128),

    -- AI metadata (populated for outbound AI messages)
    ai_response_time_ms INTEGER,       -- how long OpenAI took in milliseconds
    ai_tokens_used      INTEGER,       -- total tokens consumed
    ai_model            VARCHAR(64),   -- e.g. gpt-4o

    -- Platform message ID for deduplication (prevents processing the same webhook twice)
    platform_message_id VARCHAR(256)  UNIQUE,

    created_at          TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id         ON messages (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at      ON messages (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_intent          ON messages (intent);


-- ─────────────────────────────────────────────────────────────────────────────
-- PRODUCTS CACHE
-- Shopify product metadata. Odoo is source of truth for stock — never store
-- stock quantities here. Refresh TTL: 1 hour.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS products_cache (
    id                  SERIAL PRIMARY KEY,

    -- Shopify's internal product ID
    shopify_product_id  VARCHAR(64)    NOT NULL UNIQUE,

    name                VARCHAR(256)   NOT NULL,
    description         TEXT,

    -- Price in store currency (KES)
    price               NUMERIC(10, 2),

    -- JSON array of variant objects
    -- e.g. [{"size": "M", "color": "Black", "sku": "BW-M-BLK", "shopify_variant_id": "123"}]
    variants            JSONB,

    -- JSON array of image URLs
    -- e.g. ["https://cdn.shopify.com/...jpg"]
    images              JSONB,

    -- JSON array of tag strings
    -- e.g. ["dress", "summer", "floral"]
    tags                JSONB,

    -- When this entry was last refreshed from Shopify
    cached_at           TIMESTAMP      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_cache_name      ON products_cache USING gin(to_tsvector('english', name));
CREATE INDEX IF NOT EXISTS idx_products_cache_cached_at ON products_cache (cached_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- STOCK CACHE
-- Short-lived Odoo stock level cache. Separate from products_cache because
-- stock changes frequently. Refresh TTL: 5–10 minutes.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stock_cache (
    id           SERIAL PRIMARY KEY,

    -- Product name or SKU used to query Odoo
    product_key  VARCHAR(256)  NOT NULL UNIQUE,

    -- Current quantity from Odoo
    quantity     INTEGER       NOT NULL DEFAULT 0,

    -- Unit of measure
    unit         VARCHAR(32)   DEFAULT 'pcs',

    -- Warehouse name from Odoo
    warehouse    VARCHAR(128),

    -- When this was last fetched from Odoo
    cached_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stock_cache_cached_at ON stock_cache (cached_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- AI SETTINGS
-- Persisted AI configuration. One active row (id = 1).
-- The frontend AI Settings page reads and writes to this table.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_settings (
    id             SERIAL PRIMARY KEY,

    -- Brand tone: luxury | friendly | gen_z | minimalist | bold_sales
    tone           VARCHAR(32)   NOT NULL DEFAULT 'friendly',

    -- Full system prompt sent to OpenAI before every conversation
    system_prompt  TEXT          NOT NULL,

    -- Personality sliders (0–100)
    slider_formal  INTEGER       NOT NULL DEFAULT 40,  -- 0=formal,   100=casual
    slider_length  INTEGER       NOT NULL DEFAULT 50,  -- 0=short,    100=detailed
    slider_sales   INTEGER       NOT NULL DEFAULT 60,  -- 0=neutral,  100=salesy

    -- Response rule toggles as JSON
    -- e.g. {"no_invent_stock": true, "use_emojis": true, "include_price": true}
    response_rules JSONB,

    -- OpenAI model to use
    model          VARCHAR(64)   NOT NULL DEFAULT 'gpt-4o',

    -- Max tokens per reply
    max_tokens     INTEGER       NOT NULL DEFAULT 200,

    updated_at     TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- Insert the default settings row so the app always has something to read
INSERT INTO ai_settings (id, tone, system_prompt, response_rules)
VALUES (
    1,
    'friendly',
    'You are a friendly, professional customer support agent for a fashion & beauty brand based in Nairobi, Kenya.

You help customers with product inquiries, pricing, stock availability, and order status.

Rules:
- Always check Odoo for stock levels before confirming availability
- Never guess or invent stock quantities
- Keep replies concise (2–4 sentences)
- Be warm, on-brand, and helpful
- If you don''t know something, say so honestly and offer to find out',
    '{"no_invent_stock": true, "odoo_first": true, "include_price": true, "hide_errors": true, "use_emojis": true, "suggest_similar": true, "ask_order_number": true, "notify_oos": false}'
)
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- AUTOMATION RULES
-- IF/THEN rules evaluated before the AI generates a reply.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS automation_rules (
    id             SERIAL PRIMARY KEY,

    -- Display name shown in the UI
    name           VARCHAR(128)  NOT NULL,

    -- Human-readable trigger description (shown in UI)
    trigger        TEXT          NOT NULL,

    -- Human-readable action description (shown in UI)
    action         TEXT          NOT NULL,

    -- Machine-readable trigger config
    -- e.g. {"type": "keyword", "keywords": ["price", "how much"]}
    -- e.g. {"type": "intent", "intent": "stock_inquiry"}
    -- e.g. {"type": "odoo_stock", "condition": "eq", "value": 0}
    trigger_config JSONB,

    -- Machine-readable action config
    -- e.g. {"type": "include_price"}
    -- e.g. {"type": "reply_template", "template": "Currently out of stock..."}
    -- e.g. {"type": "trigger_dm_flow"}
    action_config  JSONB,

    -- Whether this rule is currently active
    enabled        BOOLEAN       NOT NULL DEFAULT TRUE,

    -- Rules are evaluated in ascending order of this value
    sort_order     INTEGER       NOT NULL DEFAULT 0,

    created_at     TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_automation_rules_enabled    ON automation_rules (enabled);
CREATE INDEX IF NOT EXISTS idx_automation_rules_sort_order ON automation_rules (sort_order);

-- Insert the default rules that match the frontend mock data
INSERT INTO automation_rules (name, trigger, action, trigger_config, action_config, enabled, sort_order) VALUES
(
    'Price Reply',
    'Message contains: "price", "how much", "bei", "ksh"',
    'Always include price from Shopify in reply',
    '{"type": "keyword", "keywords": ["price", "how much", "bei", "ksh"]}',
    '{"type": "include_price"}',
    TRUE, 1
),
(
    'Out of Stock',
    'Odoo stock = 0',
    'Reply: "Currently out of stock" + suggest similar product',
    '{"type": "odoo_stock", "condition": "eq", "value": 0}',
    '{"type": "reply_template", "template": "This item is currently out of stock. Would you like to be notified when it''s back? 📦", "suggest_similar": true}',
    TRUE, 2
),
(
    'Comment → DM',
    'Instagram or Facebook comment contains: "price?", "how much?"',
    'Reply publicly: "Check your DMs!" + trigger DM flow',
    '{"type": "keyword", "keywords": ["price?", "how much?"], "channels": ["instagram_comment", "facebook_comment"]}',
    '{"type": "trigger_dm_flow", "public_reply": "Hey! 👋 We''ve sent you a DM with all the details. Check your inbox! 💌"}',
    TRUE, 3
),
(
    'After Hours',
    'Any message (always on)',
    'Auto-reply normally — no after-hours delay',
    '{"type": "always"}',
    '{"type": "normal_reply"}',
    TRUE, 4
),
(
    'Complaint Escalate',
    'Intent = complaint',
    'Flag for human review + send empathy reply',
    '{"type": "intent", "intent": "complaint"}',
    '{"type": "human_escalate", "empathy_reply": true}',
    FALSE, 5
),
(
    'Order Status',
    'Intent = order_status',
    'Ask for order number + flag for human follow-up',
    '{"type": "intent", "intent": "order_status"}',
    '{"type": "ask_order_number", "flag_human": true}',
    TRUE, 6
)
ON CONFLICT DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- LOGS
-- Full pipeline audit trail. Every webhook, AI call, API response,
-- error, and human action is recorded here.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS logs (
    id              SERIAL PRIMARY KEY,

    -- Log level: info | warning | error | success
    level           VARCHAR(16)   NOT NULL,

    -- Which module produced this log
    -- e.g. services | integrations.odoo | ai.generator | webhook.instagram
    source          VARCHAR(64)   NOT NULL,

    -- The log message
    message         TEXT          NOT NULL,

    -- Optional link to the conversation this log relates to
    conversation_id INTEGER       REFERENCES conversations(id) ON DELETE SET NULL,

    -- Optional raw JSON payload (webhook body, API response, etc.)
    payload         JSONB,

    created_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_level          ON logs (level);
CREATE INDEX IF NOT EXISTS idx_logs_source         ON logs (source);
CREATE INDEX IF NOT EXISTS idx_logs_created_at     ON logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_conversation   ON logs (conversation_id);
