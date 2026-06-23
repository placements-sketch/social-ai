"""
app/models.py
Full PostgreSQL schema for the Social AI Assistant.

Tables:
  auth_users       — internal company users (admin, agent, supervisor)
  audit_logs       — audit trail for staff actions
  users            — customers who contact us via any channel
  conversations    — a thread of messages with one user on one channel
  messages         — every individual inbound/outbound message
  channels         — per-channel operational state (enabled, last_verified_at)
  products_cache   — Shopify product metadata cache
  stock_cache      — short-TTL stock-level cache
  ai_settings      — persisted AI configuration (tone, prompt, rules)
  automation_rules — IF/THEN automation rules
  logs             — full pipeline audit trail
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
    role            = db.Column(db.String(32), nullable=False, default="agent")
    status          = db.Column(db.String(32), nullable=False, default="active")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login      = db.Column(db.DateTime, nullable=True)
    last_seen_at    = db.Column(db.DateTime, nullable=True)

    audit_logs      = db.relationship("AuditLog", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def presence_status(self):
        """
        Derive presence from last_seen_at.
          - online: seen within last 90 seconds (3x heartbeat headroom)
          - idle:   seen within last 5 minutes
          - offline: anything older, or never seen
        """
        if not self.last_seen_at:
            return 'offline'
        delta = (datetime.utcnow() - self.last_seen_at).total_seconds()
        if delta < 90:
            return 'online'
        if delta < 300:
            return 'idle'
        return 'offline'

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'presence': self.presence_status(),
        }

    def to_brief(self):
        """Light dict for embedding inside other resources (assigned_to, sender, etc.)."""
        return {'id': self.id, 'email': self.email, 'full_name': self.full_name, 'role': self.role}

    def __repr__(self):
        return f"<AuthUser {self.email} role={self.role}>"


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOGS — staff actions
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=False)
    action          = db.Column(db.String(255), nullable=False)
    resource_type   = db.Column(db.String(100), nullable=True)
    resource_id     = db.Column(db.String(100), nullable=True)
    changes         = db.Column(db.JSON, nullable=True)
    ip_address      = db.Column(db.String(45), nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'changes': self.changes,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<AuditLog {self.action} by user {self.user_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# USERS — external customers (one row per (external_id, channel))
# ─────────────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id          = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(128), nullable=False)
    channel     = db.Column(db.String(32), nullable=False)
    name        = db.Column(db.String(128), nullable=True)
    avatar_url  = db.Column(db.String(512), nullable=True)
    is_human_handled = db.Column(db.Boolean, default=False, nullable=False)
    ai_disabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = db.relationship("Conversation", backref="user", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("external_id", "channel", name="uq_user_external_channel"),
    )

    @property
    def handle(self):
        """Display name for the inbox — platform name if known, else external_id."""
        return self.name or self.external_id

    def to_dict(self):
        return {
            'id': self.id,
            'external_id': self.external_id,
            'channel': self.channel,
            'name': self.name,
            'handle': self.handle,
            'avatar_url': self.avatar_url,
            'is_human_handled': self.is_human_handled,
            'ai_disabled': self.ai_disabled,
        }

    def __repr__(self):
        return f"<User {self.external_id} via {self.channel}>"


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATIONS
# ─────────────────────────────────────────────────────────────────────────────

class Conversation(db.Model):
    __tablename__ = "conversations"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel    = db.Column(db.String(32), nullable=False)
    status     = db.Column(db.String(32), default="active", nullable=False)
    ai_enabled = db.Column(db.Boolean, default=True, nullable=False)
    last_message     = db.Column(db.Text, nullable=True)
    last_message_at  = db.Column(db.DateTime, nullable=True)
    unread_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Assignment foundations ───────────────────────────────────────────
    assigned_to = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)

    # ── Resolution foundations ───────────────────────────────────────────
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)

    # ── Handoff (AI → human) ─────────────────────────────────────────────
    # Latest reason the AI handed this conversation to humans.
    # Possible values: 'keyword', 'intent', 'rule', or null.
    # Full history lives in the logs table.
    handoff_reason = db.Column(db.String(64), nullable=True)

    # Relationships use explicit foreign_keys because there are 3 FKs to auth_users
    assignee   = db.relationship("AuthUser", foreign_keys=[assigned_to])
    assigner   = db.relationship("AuthUser", foreign_keys=[assigned_by])
    resolver   = db.relationship("AuthUser", foreign_keys=[resolved_by])

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
            # Assignment fields
            'assigned_to': self.assigned_to,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'assigned_by': self.assigned_by,
            'assignee': self.assignee.to_brief() if self.assignee else None,
            # Resolution fields
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolved_by': self.resolved_by,
            'resolver': self.resolver.to_brief() if self.resolver else None,
            'handoff_reason': self.handoff_reason,
        }
        if include_messages:
            data['messages'] = [m.to_dict() for m in self.messages]
        return data

    def __repr__(self):
        return f"<Conversation {self.id} [{self.channel}] status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

class Message(db.Model):
    __tablename__ = "messages"

    id              = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel   = db.Column(db.String(32), nullable=False)
    direction = db.Column(db.String(8), nullable=False)
    sender    = db.Column(db.String(16), nullable=True)
    # Which staff member sent this — NULL for AI/system and for inbound messages.
    sender_id = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)
    content   = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(255), nullable=True)    
    product_keyword = db.Column(db.String(128), nullable=True)
    ai_response_time_ms = db.Column(db.Integer, nullable=True)
    ai_tokens_used      = db.Column(db.Integer, nullable=True)
    ai_model            = db.Column(db.String(64), nullable=True)
    platform_message_id = db.Column(db.String(256), nullable=True, unique=True)
    external_id = db.Column(db.String(255), nullable=True, index=True)
    media_id = db.Column(db.String(128), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sender_user = db.relationship("AuthUser", foreign_keys=[sender_id])

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
            'sender_id': self.sender_id,
            'sender_user': self.sender_user.to_brief() if self.sender_user else None,
            'text': self.content,
            'content': self.content,
            'time': self.created_at.strftime('%H:%M') if self.created_at else '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'intent': self.intent,
            'product_keyword': self.product_keyword,
            'meta': meta,
            'external_id': self.external_id,
            'media_id': self.media_id,
        }

    def __repr__(self):
        return f"<Message {self.direction} [{self.channel}] intent={self.intent}>"


# ─────────────────────────────────────────────────────────────────────────────
# CHANNELS
# ─────────────────────────────────────────────────────────────────────────────

class Channel(db.Model):
    __tablename__ = "channels"

    id           = db.Column(db.Integer, primary_key=True)
    channel      = db.Column(db.String(32), unique=True, nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    enabled      = db.Column(db.Boolean, nullable=False, default=True)
    webhook_path = db.Column(db.String(128), nullable=False)
    last_verified_at = db.Column(db.DateTime, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    token_scopes     = db.Column(db.Text, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    def to_dict(self, public_base_url=None, stats=None, credentials_set=None):
        stats = stats or {}
        webhook_url = (
            f"{public_base_url.rstrip('/')}{self.webhook_path}"
            if public_base_url else self.webhook_path
        )
        
        # A channel is "connected" if:
        # 1. Credentials are set, OR
        # 2. There are recent messages (indicates it's receiving data)
        has_messages = (stats.get('message_count', 0) or 0) > 0
        connected = bool(credentials_set) or has_messages
        
        return {
            'id': self.id,
            'channel': self.channel,
            'display_name': self.display_name,
            'enabled': self.enabled,
            'connected': connected,
            'credentials_set': bool(credentials_set),
            'webhook_url': webhook_url,
            'webhook_path': self.webhook_path,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
            'token_expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
            'token_scopes': self.token_scopes.split(',') if self.token_scopes else [],
            'message_count': stats.get('message_count', 0),
            'unread_count': stats.get('unread_count', 0),
            'last_message_at': stats.get('last_message_at'),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Channel {self.channel} enabled={self.enabled}>"


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTS CACHE
# ─────────────────────────────────────────────────────────────────────────────

class ProductCache(db.Model):
    __tablename__ = "products_cache"

    id                 = db.Column(db.Integer, primary_key=True)
    shopify_product_id = db.Column(db.String(64), unique=True, nullable=False)
    name        = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price       = db.Column(db.Numeric(10, 2), nullable=True)
    variants    = db.Column(db.JSON, nullable=True)
    images      = db.Column(db.JSON, nullable=True)
    tags        = db.Column(db.JSON, nullable=True)
    stock_quantity    = db.Column(db.Integer, nullable=True)
    inventory_tracked = db.Column(db.Boolean, default=False, nullable=False)
    cached_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ProductCache {self.name} (Shopify {self.shopify_product_id})>"


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMERS CACHE
# ─────────────────────────────────────────────────────────────────────────────

class CustomerCache(db.Model):
    __tablename__ = "customers_cache"

    id                  = db.Column(db.Integer, primary_key=True)
    shopify_customer_id = db.Column(db.String(64), unique=True, nullable=False)
    email               = db.Column(db.String(256), nullable=True)
    first_name          = db.Column(db.String(128), nullable=True)
    last_name           = db.Column(db.String(128), nullable=True)
    phone               = db.Column(db.String(64), nullable=True)
    city                = db.Column(db.String(128), nullable=True)
    country             = db.Column(db.String(128), nullable=True)
    accepts_marketing   = db.Column(db.Boolean, default=False)
    tags                = db.Column(db.JSON, nullable=True)
    total_orders        = db.Column(db.Integer, default=0)
    total_spent         = db.Column(db.Numeric(12, 2), default=0)
    last_order_date     = db.Column(db.DateTime, nullable=True)
    first_order_date    = db.Column(db.DateTime, nullable=True)
    shopify_created_at  = db.Column(db.DateTime, nullable=True)
    cached_at           = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def full_name(self):
        parts = [self.first_name, self.last_name]
        return ' '.join(p for p in parts if p) or 'Unknown'

    def __repr__(self):
        return f"<CustomerCache {self.full_name} ({self.email})>"


# ─────────────────────────────────────────────────────────────────────────────
# ORDERS CACHE
# ─────────────────────────────────────────────────────────────────────────────

class OrderCache(db.Model):
    __tablename__ = "orders_cache"

    id                  = db.Column(db.Integer, primary_key=True)
    shopify_order_id    = db.Column(db.String(64), unique=True, nullable=False)
    shopify_customer_id = db.Column(db.String(64), nullable=True, index=True)
    order_number        = db.Column(db.String(64), nullable=True)
    total               = db.Column(db.Numeric(12, 2), default=0)
    currency            = db.Column(db.String(8), nullable=True)
    items_count         = db.Column(db.Integer, default=0)
    products            = db.Column(db.JSON, nullable=True)
    financial_status    = db.Column(db.String(32), nullable=True)
    fulfillment_status  = db.Column(db.String(32), nullable=True)
    order_date          = db.Column(db.DateTime, nullable=True)
    cached_at           = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<OrderCache #{self.order_number} KES {self.total}>"
    

# ─────────────────────────────────────────────────────────────────────────────
# STOCK CACHE
# ─────────────────────────────────────────────────────────────────────────────

class StockCache(db.Model):
    __tablename__ = "stock_cache"

    id           = db.Column(db.Integer, primary_key=True)
    product_key  = db.Column(db.String(256), unique=True, nullable=False)
    quantity     = db.Column(db.Integer, default=0, nullable=False)
    unit         = db.Column(db.String(32), default="pcs", nullable=True)
    warehouse    = db.Column(db.String(128), nullable=True)
    cached_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<StockCache {self.product_key}: {self.quantity} {self.unit}>"

class StoreInfoCache(db.Model):
    """
    Singleton-per-kind cache for Shopify store-wide data that doesn't fit
    cleanly into ProductCache / CustomerCache / OrderCache.
    
    Each `kind` is a singleton — exactly one row per kind, replaced on sync.
    Kinds: 'locations', 'shipping_zones', 'active_discounts'
    """
    __tablename__ = "store_info_cache"
    
    id         = db.Column(db.Integer, primary_key=True)
    kind       = db.Column(db.String(64), nullable=False, unique=True, index=True)
    data       = db.Column(db.JSON, nullable=False, default=list)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<StoreInfoCache kind={self.kind}>"
# ─────────────────────────────────────────────────────────────────────────────
# AI SETTINGS — single active row (id=1)
# ─────────────────────────────────────────────────────────────────────────────

class AISettings(db.Model):
    __tablename__ = "ai_settings"

    id             = db.Column(db.Integer, primary_key=True)
    tone           = db.Column(db.String(32), default="friendly", nullable=False)
    system_prompt  = db.Column(db.Text, nullable=False)
    slider_formal  = db.Column(db.Integer, default=40, nullable=False)
    slider_length  = db.Column(db.Integer, default=50, nullable=False)
    slider_sales   = db.Column(db.Integer, default=60, nullable=False)
    response_rules = db.Column(db.JSON, nullable=True)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'tone': self.tone,
            'system_prompt': self.system_prompt,
            'slider_formal': self.slider_formal,
            'slider_length': self.slider_length,
            'slider_sales': self.slider_sales,
            'response_rules': self.response_rules or {},
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<AISettings tone={self.tone}>"


# ─────────────────────────────────────────────────────────────────────────────
# AUTOMATION RULES
# ─────────────────────────────────────────────────────────────────────────────

class AutomationRule(db.Model):
    __tablename__ = "automation_rules"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(128), nullable=False)
    trigger     = db.Column(db.Text, nullable=False)
    action      = db.Column(db.Text, nullable=False)
    trigger_config = db.Column(db.JSON, nullable=True)
    action_config  = db.Column(db.JSON, nullable=True)
    enabled     = db.Column(db.Boolean, default=True, nullable=False)
    sort_order  = db.Column(db.Integer, default=0, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'trigger': self.trigger,
            'action': self.action,
            'trigger_config': self.trigger_config or {},
            'action_config': self.action_config or {},
            'enabled': self.enabled,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<AutomationRule '{self.name}' enabled={self.enabled}>"


# ─────────────────────────────────────────────────────────────────────────────
# LOGS — pipeline audit trail
# ─────────────────────────────────────────────────────────────────────────────

class Log(db.Model):
    __tablename__ = "logs"

    id         = db.Column(db.Integer, primary_key=True)
    level      = db.Column(db.String(16), nullable=False)
    source     = db.Column(db.String(64), nullable=False)
    message    = db.Column(db.Text, nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=True)
    payload    = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'level': self.level,
            'source': self.source,
            'message': self.message,
            'conversation_id': self.conversation_id,
            'payload': self.payload,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Log [{self.level}] {self.source}: {self.message[:60]}>"
    
# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS — in-app alerts for staff
# ─────────────────────────────────────────────────────────────────────────────

class Notification(db.Model):
    __tablename__ = "notifications"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('auth_users.id', ondelete='CASCADE'),
                              nullable=False)
    type          = db.Column(db.String(64), nullable=False)
    severity      = db.Column(db.String(16), nullable=False, default='info')  # 'info' | 'warning' | 'urgent'
    title         = db.Column(db.String(256), nullable=False)
    body          = db.Column(db.Text, nullable=True)
    resource_type = db.Column(db.String(64), nullable=True)
    resource_id   = db.Column(db.String(64), nullable=True)
    actor_id      = db.Column(db.Integer, db.ForeignKey('auth_users.id', ondelete='SET NULL'),
                              nullable=True)
    read_at       = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'severity': self.severity or 'info',
            'title': self.title,
            'body': self.body,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'actor_id': self.actor_id,
            'read': self.read_at is not None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Notification user={self.user_id} {self.type}: {self.title[:40]}>"
    

# ─────────────────────────────────────────────────────────────────────────────
# SYNC JOBS — background job tracking for long-running Shopify operations
# ─────────────────────────────────────────────────────────────────────────────

class SyncJob(db.Model):
    """
    Tracks the state of a long-running sync operation (products check,
    products sync, orders sync, etc.). Each call to a sync endpoint creates
    a row, runs the work in a background thread, and updates this row when done.
    The frontend polls /api/products/sync/status to see if the job is finished.
    """
    __tablename__ = "sync_jobs"

    id          = db.Column(db.Integer, primary_key=True)

    # What kind of sync this is. Reuse the same values across endpoints so a
    # single status query can find "the most recent products-related job".
    # Values: 'products_check' | 'products_apply' | 'orders_apply' | 'customers_apply'
    kind        = db.Column(db.String(64), nullable=False, index=True)

    # 'pending' | 'running' | 'success' | 'failed'
    status      = db.Column(db.String(16), nullable=False, default='pending', index=True)

    # Who triggered it
    created_by  = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)

    # Optional progress hint: "Fetching products from Shopify..." etc.
    progress    = db.Column(db.String(256), nullable=True)

    # When the job actually started running (worker picked it up)
    started_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # When it finished (success OR failed)
    finished_at = db.Column(db.DateTime, nullable=True)

    # Result data on success: e.g. {"added": [...], "updated": [...], "removed": [...]}
    # For products_check this is the diff. For products_apply this is the counts applied.
    result      = db.Column(db.JSON, nullable=True)

    # Error message on failure
    error       = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'kind': self.kind,
            'status': self.status,
            'progress': self.progress,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'result': self.result,
            'error': self.error,
            'elapsed_ms': (
                int((self.finished_at - self.started_at).total_seconds() * 1000)
                if self.finished_at and self.started_at else None
            ),
        }

    def __repr__(self):
        return f"<SyncJob #{self.id} {self.kind} {self.status}>"