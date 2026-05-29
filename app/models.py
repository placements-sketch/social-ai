"""
app/models.py
Full PostgreSQL schema for the Social AI Assistant.

Tables:
  users            — customers who contact us via any channel
  conversations    — a thread of messages with one user on one channel
  messages         — every individual inbound/outbound message
  products_cache   — Shopify product metadata cache
  stock_cache      — Odoo stock level cache (short TTL)
  ai_settings      — persisted AI configuration (tone, prompt, rules)
  automation_rules — IF/THEN automation rules
  logs             — full pipeline audit trail
  auth_users       — internal company users (admin, agent, supervisor)
  audit_logs       — audit trail for user actions
"""

from datetime import datetime
from app import db
import bcrypt


# ─────────────────────────────────────────────────────────────────────────────
# AUTH USERS
# Internal company users (admin, agent, supervisor) — NOT customers.
# ─────────────────────────────────────────────────────────────────────────────

class AuthUser(db.Model):
    __tablename__ = "auth_users"

    id              = db.Column(db.Integer, primary_key=True)
    email           = db.Column(db.String(255), unique=True, nullable=False)
    password_hash   = db.Column(db.String(255), nullable=False)
    full_name       = db.Column(db.String(255), nullable=False)

    # Role: admin | agent | supervisor
    role            = db.Column(db.String(32), nullable=False, default="agent")

    # Status: active | inactive | suspended
    status          = db.Column(db.String(32), nullable=False, default="active")

    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login      = db.Column(db.DateTime, nullable=True)

    # Relationships
    audit_logs      = db.relationship("AuditLog", backref="user", lazy=True)

    def set_password(self, password):
        """Hash and set the password."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        """Check if the provided password matches the hash."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    @property
    def handle(self):
        """Display name for the inbox — platform name if known, else external_id."""
        return self.name or self.external_id

    def to_dict(self):
        """Return user data as dictionary (for JSON responses)."""
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

    def __repr__(self):
        return f"<AuthUser {self.email} role={self.role}>"


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOGS
# Track all user actions for compliance and debugging.
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=False)

    # Action: login | logout | create_user | update_user | delete_user | view_messages | etc.
    action          = db.Column(db.String(255), nullable=False)

    # Resource type: user | message | conversation | settings | etc.
    resource_type   = db.Column(db.String(100), nullable=True)

    # Resource ID (e.g., user_id, conversation_id, etc.)
    resource_id     = db.Column(db.String(100), nullable=True)

    # JSON object with changes made (for update actions)
    changes         = db.Column(db.JSON, nullable=True)

    # IP address of the request
    ip_address      = db.Column(db.String(45), nullable=True)

    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Return audit log as dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'changes': self.changes,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat()
        }

    def __repr__(self):
        return f"<AuditLog {self.action} by user {self.user_id}>"





# ─────────────────────────────────────────────────────────────────────────────
# USERS
# One row per unique customer, identified by their channel-specific ID.
# The same real person on Instagram and WhatsApp = two User rows (different IDs).
# ─────────────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id          = db.Column(db.Integer, primary_key=True)

    # The ID the platform gives us — Instagram PSID, WhatsApp phone number, Facebook PSID, etc.
    external_id = db.Column(db.String(128), nullable=False)

    # Which channel this user came from
    # Values: instagram_dm | instagram_comment | whatsapp | facebook_dm | facebook_comment
    channel     = db.Column(db.String(32), nullable=False)

    # Display name if the platform provides it (optional)
    name        = db.Column(db.String(128), nullable=True)

    # Profile picture URL from the platform (optional, populated later)
    avatar_url  = db.Column(db.String(512), nullable=True)

    # Whether a human agent has taken over this user's conversations
    is_human_handled = db.Column(db.Boolean, default=False, nullable=False)

    # Soft block — if True, AI will not auto-reply to this user
    ai_disabled = db.Column(db.Boolean, default=False, nullable=False)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversations = db.relationship("Conversation", backref="user", lazy=True)

    # Unique constraint: same external_id can exist on different channels
    __table_args__ = (
        db.UniqueConstraint("external_id", "channel", name="uq_user_external_channel"),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'external_id': self.external_id,
            'channel': self.channel,
            'name': self.name,
            'handle': self.name or self.external_id,
            'avatar_url': self.avatar_url,
            'is_human_handled': self.is_human_handled,
            'ai_disabled': self.ai_disabled,
        }

    def __repr__(self):
        return f"<User {self.external_id} via {self.channel}>"


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATIONS
# Groups messages into threads. One conversation = one continuous chat session
# with a user on a specific channel.
# ─────────────────────────────────────────────────────────────────────────────

class Conversation(db.Model):
    __tablename__ = "conversations"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Denormalised for fast filtering without joining users
    channel    = db.Column(db.String(32), nullable=False)

    # Status of this conversation
    # Values: active | resolved | human_override | pending
    status     = db.Column(db.String(32), default="active", nullable=False)

    # Whether AI is currently enabled for this specific conversation
    ai_enabled = db.Column(db.Boolean, default=True, nullable=False)

    # The last message text — stored here so the inbox list doesn't need a subquery
    last_message     = db.Column(db.Text, nullable=True)
    last_message_at  = db.Column(db.DateTime, nullable=True)

    # Count of unread inbound messages
    unread_count = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    messages = db.relationship("Message", backref="conversation", lazy=True,
                               order_by="Message.created_at")

    def to_dict(self, include_messages=False):
        handle = self.user.handle if self.user else None
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'handle': handle,
            'platform': self.channel,
            'channel': self.channel,
            'status': self.status,
            'ai_enabled': self.ai_enabled,
            'ai_disabled': not self.ai_enabled,
            'lastMessage': self.last_message,
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'time': self.last_message_at.strftime('%H:%M') if self.last_message_at else '',
            'unread': self.unread_count > 0,
            'unread_count': self.unread_count,
        }
        if include_messages:
            data['messages'] = [m.to_dict() for m in self.messages]
        return data

    def __repr__(self):
        return f"<Conversation {self.id} [{self.channel}] status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES
# Every individual message — inbound from customer or outbound from AI/agent.
# ─────────────────────────────────────────────────────────────────────────────

class Message(db.Model):
    __tablename__ = "messages"

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Which channel this message came from / was sent to
    channel   = db.Column(db.String(32), nullable=False)

    # inbound = from customer, outbound = from AI or human agent
    direction = db.Column(db.String(8), nullable=False)

    # Who sent the outbound message: ai | human | system
    sender    = db.Column(db.String(16), nullable=True)

    # The actual message text
    content   = db.Column(db.Text, nullable=False)

    # Detected intent for inbound messages
    intent    = db.Column(db.String(64), nullable=True)

    # The product keyword extracted from this message (if any)
    product_keyword = db.Column(db.String(128), nullable=True)

    # AI response metadata — stored for the Logs / debug panel
    ai_response_time_ms = db.Column(db.Integer, nullable=True)   # milliseconds
    ai_tokens_used      = db.Column(db.Integer, nullable=True)
    ai_model            = db.Column(db.String(64), nullable=True)

    # Platform-specific message ID (for deduplication)
    platform_message_id = db.Column(db.String(256), nullable=True, unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        if self.direction == 'inbound':
            frm = 'user'
        else:
            frm = self.sender if self.sender in ('ai', 'human') else 'ai'

        meta = None
        if self.intent or self.product_keyword or self.ai_response_time_ms:
            meta = {
                'intent': self.intent,
                'product': self.product_keyword,
                'stock': None,
                'responseTime': (f"{self.ai_response_time_ms} ms"
                                 if self.ai_response_time_ms is not None else None),
            }

        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'from': frm,
            'direction': self.direction,
            'sender': self.sender,
            'text': self.content,
            'content': self.content,
            'time': self.created_at.strftime('%H:%M') if self.created_at else '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'intent': self.intent,
            'product_keyword': self.product_keyword,
            'meta': meta,
        }

    def __repr__(self):
        return f"<Message {self.direction} [{self.channel}] intent={self.intent}>"


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTS CACHE
# Shopify product metadata. Odoo is source of truth for stock — never store
# stock quantities here.
# ─────────────────────────────────────────────────────────────────────────────

class ProductCache(db.Model):
    __tablename__ = "products_cache"

    id                 = db.Column(db.Integer, primary_key=True)
    shopify_product_id = db.Column(db.String(64), unique=True, nullable=False)

    name        = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Price in KES (or whatever the store currency is)
    price       = db.Column(db.Numeric(10, 2), nullable=True)

    # JSON array of variant objects: [{"size": "M", "color": "Black", "sku": "BW-M-BLK"}]
    variants    = db.Column(db.JSON, nullable=True)

    # JSON array of image URLs
    images      = db.Column(db.JSON, nullable=True)

    # JSON array of tag strings
    tags        = db.Column(db.JSON, nullable=True)

    # When this cache entry was last refreshed from Shopify
    cached_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ProductCache {self.name} (Shopify {self.shopify_product_id})>"


# ─────────────────────────────────────────────────────────────────────────────
# STOCK CACHE
# Short-lived Odoo stock level cache. Separate from products_cache because
# stock changes frequently and has a much shorter TTL (5–10 min).
# ─────────────────────────────────────────────────────────────────────────────

class StockCache(db.Model):
    __tablename__ = "stock_cache"

    id           = db.Column(db.Integer, primary_key=True)

    # Product name or SKU used to query Odoo
    product_key  = db.Column(db.String(256), unique=True, nullable=False)

    # Current quantity from Odoo
    quantity     = db.Column(db.Integer, default=0, nullable=False)

    # Unit of measure (pcs, kg, etc.)
    unit         = db.Column(db.String(32), default="pcs", nullable=True)

    # Warehouse name from Odoo
    warehouse    = db.Column(db.String(128), nullable=True)

    # When this was last fetched from Odoo — used to check if cache is stale
    cached_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<StockCache {self.product_key}: {self.quantity} {self.unit}>"


# ─────────────────────────────────────────────────────────────────────────────
# AI SETTINGS
# Persisted AI configuration. One active row at a time (id=1).
# The frontend AI Settings page reads and writes to this table.
# ─────────────────────────────────────────────────────────────────────────────

class AISettings(db.Model):
    __tablename__ = "ai_settings"

    id            = db.Column(db.Integer, primary_key=True)

    # Brand tone selection
    # Values: luxury | friendly | gen_z | minimalist | bold_sales
    tone          = db.Column(db.String(32), default="friendly", nullable=False)

    # The full system prompt sent to OpenAI before every conversation
    system_prompt = db.Column(db.Text, nullable=False)

    # Personality slider values (0–100)
    slider_formal = db.Column(db.Integer, default=40, nullable=False)  # 0=formal, 100=casual
    slider_length = db.Column(db.Integer, default=50, nullable=False)  # 0=short, 100=detailed
    slider_sales  = db.Column(db.Integer, default=60, nullable=False)  # 0=neutral, 100=salesy

    # Response rule toggles stored as JSON: {"no_invent_stock": true, "use_emojis": true, ...}
    response_rules = db.Column(db.JSON, nullable=True)

    # OpenAI model to use
    model         = db.Column(db.String(64), default="gpt-4o", nullable=False)

    # Max tokens per reply
    max_tokens    = db.Column(db.Integer, default=200, nullable=False)

    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AISettings tone={self.tone} model={self.model}>"


# ─────────────────────────────────────────────────────────────────────────────
# AUTOMATION RULES
# IF/THEN rules that run before the AI generates a reply.
# Matches the Automation page in the frontend.
# ─────────────────────────────────────────────────────────────────────────────

class AutomationRule(db.Model):
    __tablename__ = "automation_rules"

    id          = db.Column(db.Integer, primary_key=True)

    # Display name shown in the UI
    name        = db.Column(db.String(128), nullable=False)

    # Human-readable trigger description (shown in UI)
    trigger     = db.Column(db.Text, nullable=False)

    # Human-readable action description (shown in UI)
    action      = db.Column(db.Text, nullable=False)

    # Machine-readable trigger config stored as JSON
    # e.g. {"type": "keyword", "keywords": ["price", "how much"]}
    # e.g. {"type": "intent", "intent": "stock_inquiry"}
    # e.g. {"type": "odoo_stock", "condition": "eq", "value": 0}
    trigger_config = db.Column(db.JSON, nullable=True)

    # Machine-readable action config stored as JSON
    # e.g. {"type": "include_price"}
    # e.g. {"type": "reply_template", "template": "Currently out of stock..."}
    # e.g. {"type": "trigger_dm_flow"}
    action_config  = db.Column(db.JSON, nullable=True)

    # Whether this rule is currently active
    enabled     = db.Column(db.Boolean, default=True, nullable=False)

    # Rules are evaluated in ascending order of this value
    sort_order  = db.Column(db.Integer, default=0, nullable=False)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AutomationRule '{self.name}' enabled={self.enabled}>"


# ─────────────────────────────────────────────────────────────────────────────
# LOGS
# Full pipeline audit trail. Every webhook received, AI call made,
# API response, error, and human action is recorded here.
# ─────────────────────────────────────────────────────────────────────────────

class Log(db.Model):
    __tablename__ = "logs"

    id         = db.Column(db.Integer, primary_key=True)

    # Log level: info | warning | error | success
    level      = db.Column(db.String(16), nullable=False)

    # Which module or function produced this log
    # e.g. services | integrations.odoo | ai.generator | webhook.instagram
    source     = db.Column(db.String(64), nullable=False)

    # The log message
    message    = db.Column(db.Text, nullable=False)

    # Optional: link to the conversation this log relates to
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=True)

    # Optional: raw JSON payload (for webhook logs, API responses, etc.)
    payload    = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Log [{self.level}] {self.source}: {self.message[:60]}>"
