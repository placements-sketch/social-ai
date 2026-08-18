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
    reset_token_hash    = db.Column(db.String(64), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    # ── Sign-in by emailed one-time code ─────────────────────────────────
    # bcrypt, not sha256 like the reset token above, and the difference
    # matters. A reset token is 32 random bytes: sha256 of it is unguessable.
    # A login code is six digits — one million possibilities — so a fast hash
    # is reversible in under a second by anyone who can read this table. bcrypt
    # makes that guess cost ~100ms, which is the whole defence.
    otp_hash        = db.Column(db.String(255), nullable=True)
    otp_expires     = db.Column(db.DateTime, nullable=True)
    # Wrong guesses against the CURRENT code. Without this a six-digit code is
    # trivially brute-forced online: a million requests is minutes of scripting.
    otp_attempts    = db.Column(db.Integer, nullable=False, default=0)
    # When we last sent one, for the resend cooldown. Per-account, because a
    # per-IP rate limit does nothing against someone spamming a colleague's
    # inbox from a phone.
    otp_sent_at     = db.Column(db.DateTime, nullable=True)

    audit_logs      = db.relationship("AuditLog", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    # A tab sends a heartbeat every 30 seconds while it is visible, so 90
    # seconds is three missed beats — enough headroom for a slow request or a
    # brief network drop without flickering.
    PRESENCE_ONLINE_SECONDS = 90

    def presence_status(self):
        """
        Derive presence from last_seen_at. Two states only.

          - online:  seen within the last 90 seconds
          - offline: anything older, or never seen

        There used to be an 'idle' state between 90 seconds and 5 minutes.
        It was removed because nobody could act on it: an agent shown as idle
        might be reading a long thread, or might have shut their laptop four
        minutes ago, and the badge could not tell you which. Worse, it made
        someone who had genuinely left look half-present for five minutes, which
        is exactly when you want to route work elsewhere. Offline plus "last
        seen 4m ago" says the same thing without the false reassurance.
        """
        if not self.last_seen_at:
            return 'offline'
        delta = (datetime.utcnow() - self.last_seen_at).total_seconds()
        return 'online' if delta < self.PRESENCE_ONLINE_SECONDS else 'offline'

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

    # The Shopify customer this social profile belongs to, when an agent has
    # said so.
    #
    # There is no automatic join and there cannot be one: Instagram identifies a
    # person by IGSID, WhatsApp by phone, Shopify by email — no two of them
    # share a key. 162,186 Shopify customers and the handful who have ever
    # messaged us sit in the same database with nothing connecting them, which
    # is the single reason customer profiling was parked.
    #
    # So it is a deliberate act by a person who can see both sides of the
    # conversation, recorded here rather than inferred. On users, not
    # conversations: the same customer opens several threads over time and the
    # link belongs to the human, not to one exchange.
    #
    # Stored as the Shopify id string rather than a FK to customers_cache,
    # because that table is a cache — it is deleted and rebuilt by the sync, and
    # a foreign key would either block the rebuild or cascade the links away
    # with it.
    shopify_customer_id = db.Column(db.String(64), nullable=True, index=True)
    shopify_linked_at   = db.Column(db.DateTime, nullable=True)
    shopify_linked_by   = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = db.relationship("Conversation", backref="user", lazy=True)

    __table_args__ = (
        db.UniqueConstraint("external_id", "channel", name="uq_user_external_channel"),
    )

    @property
    def handle(self):
        """
        Display name for the inbox — the platform username where we have one.

        Falling back to the raw external_id put "2532642840503747" in front of
        agents on every shift. It reads as a field that failed to load, and two
        customers cannot be told apart by scanning 17-digit strings. Those ids
        will never resolve (see display_for_external_id), so this is permanent
        for the affected threads rather than something that fixes itself.

        One place, because handle() is what the inbox, activity feed,
        notifications and emails all read.
        """
        if self.name:
            return self.name
        from app.identity import display_for_external_id
        return display_for_external_id(self.external_id, self.channel)

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
    # Which of OUR accounts received this — the IG business account id or Page
    # id from the webhook's entry[].id. Without it a reply can only be sent
    # from whatever the single global token happens to be, which is wrong the
    # moment a second account is connected.
    business_account_id = db.Column(db.String(64), nullable=True, index=True)
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

    # WHEN the AI last escalated, and when a human last switched the AI off.
    # Analytics needs the event time: keying "Escalated" off last_message_at
    # counted conversations *touched* in a window that had *ever* escalated,
    # so one June escalation recounted in every later window it stayed active
    # in. These are set by handoff._trigger() and the takeover paths in
    # app/messages.py; both stay NULL until the event happens.
    escalated_at   = db.Column(db.DateTime, nullable=True, index=True)
    ai_disabled_at = db.Column(db.DateTime, nullable=True, index=True)
    # Set when the GLOBAL kill switch queued this conversation for humans, so
    # switching the AI back on can restore exactly that set — and nothing else.
    # Without it there is no way to tell a conversation an agent deliberately
    # took over from one the master switch happened to catch, and a restore
    # would hand agent-claimed threads back to the AI.
    ai_auto_paused_at = db.Column(db.DateTime, nullable=True, index=True)

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
            'ai_auto_paused': self.ai_auto_paused_at is not None,
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
            data['messages'] = [
                m.to_dict() for m in self.messages
                if m.sender != 'ai_pending'
            ]
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
    ai_eligible = db.Column(db.Boolean, nullable=True, index=True)
    ai_tokens_used      = db.Column(db.Integer, nullable=True)
    ai_model            = db.Column(db.String(64), nullable=True)
    platform_message_id = db.Column(db.String(256), nullable=True, unique=True)
    product_url = db.Column(db.String(1024), nullable=True)
    image_urls = db.Column(db.JSON, nullable=True)
    utm_token = db.Column(db.String(128), nullable=True, index=True)
    external_id = db.Column(db.String(255), nullable=True, index=True)
    media_id = db.Column(db.String(128), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    sender_user = db.relationship("AuthUser", foreign_keys=[sender_id])

    def to_dict(self):
        if self.direction == 'inbound':
            frm = 'user'
        else:
            # 'system' is an internal note — something the product did, not
            # something anyone said to the customer. It has to stay
            # distinguishable here, because the fallback below collapses every
            # unrecognised sender to 'ai', and an internal note rendered as an
            # AI message reads as the assistant announcing its own settings
            # changes to a customer.
            #
            # These rows are never delivered: delivery only happens where a
            # channel send is explicitly performed, and nothing walks the table
            # looking for unsent outbound messages.
            if self.sender == 'system':
                frm = 'system'
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'intent': self.intent,
            'product_keyword': self.product_keyword,
            'meta': meta,
            'external_id': self.external_id,
            'media_id': self.media_id,
            'image_urls': self.image_urls or [],
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
        
        # Whether we can actually deliver a reply here. Facebook, WhatsApp and
        # TikTok have stub dispatchers, so the toggle is refused for them — the
        # UI reads this to show the control as unavailable rather than letting
        # someone click it and get an error back.
        try:
            from app.services import SENDABLE_CHANNELS
            can_send = self.channel in SENDABLE_CHANNELS
        except Exception:
            can_send = True

        return {
            'id': self.id,
            'channel': self.channel,
            'display_name': self.display_name,
            'enabled': self.enabled,
            'can_send': can_send,
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
    handle             = db.Column(db.String(256), nullable=True, index=True)
    name        = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price       = db.Column(db.Numeric(10, 2), nullable=True)
    variants    = db.Column(db.JSON, nullable=True)
    variants_detail = db.Column(db.JSON, nullable=True)
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
    email               = db.Column(db.String(512), nullable=True)
    first_name          = db.Column(db.String(512), nullable=True)
    last_name           = db.Column(db.String(512), nullable=True)
    phone               = db.Column(db.String(128), nullable=True)
    city                = db.Column(db.String(256), nullable=True)
    country             = db.Column(db.String(128), nullable=True)
    accepts_marketing   = db.Column(db.Boolean, default=False)
    tags                = db.Column(db.JSON, nullable=True)
    total_orders        = db.Column(db.Integer, default=0)
    total_spent         = db.Column(db.Numeric(12, 2), default=0)
    last_order_date     = db.Column(db.DateTime, nullable=True)
    segment             = db.Column(db.String(32), nullable=True, index=True)
    rfm_r = db.Column(db.SmallInteger, nullable=True)
    rfm_f = db.Column(db.SmallInteger, nullable=True)
    rfm_m = db.Column(db.SmallInteger, nullable=True)
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
    order_number        = db.Column(db.String(128), nullable=True)
    total               = db.Column(db.Numeric(12, 2), default=0)
    currency            = db.Column(db.String(8), nullable=True)
    items_count         = db.Column(db.Integer, default=0)
    products            = db.Column(db.JSON, nullable=True)
    financial_status    = db.Column(db.String(64), nullable=True)
    fulfillment_status  = db.Column(db.String(64), nullable=True)
    order_date          = db.Column(db.DateTime, nullable=True)
    cached_at           = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Added by Step 37, to compute Shopify's sales figures from the
    # transactional payload instead of the analytics layer behind Reports —
    # which was measured short on orders in 52 of 52 months.
    #
    # `total` alone cannot produce any of this: it is one number with tax and
    # shipping already folded in and refunds not taken out. Shopify sends all of
    # the below on every order; we were discarding it.
    #
    # NULL means "synced before Step 37", NOT zero — and the difference matters.
    # A missing tax value that reads as 0.0 silently inflates net sales, which
    # is precisely the class of quiet wrongness this replaces. Anything reading
    # these must treat None as unknown and fall back explicitly.
    gross_sales         = db.Column(db.Numeric(12, 2), nullable=True)   # total_line_items_price
    total_discounts     = db.Column(db.Numeric(12, 2), nullable=True)
    total_tax           = db.Column(db.Numeric(12, 2), nullable=True)
    total_shipping      = db.Column(db.Numeric(12, 2), nullable=True)
    total_refunded      = db.Column(db.Numeric(12, 2), nullable=True)
    # Shopify's analytics excludes both. A computed total that counts them will
    # not reconcile against anything.
    cancelled_at        = db.Column(db.DateTime, nullable=True)
    is_test             = db.Column(db.Boolean, nullable=True)

    def __repr__(self):
        return f"<OrderCache #{self.order_number} KES {self.total}>"
    

# ─────────────────────────────────────────────────────────────────────────────
# STOCK CACHE
# ─────────────────────────────────────────────────────────────────────────────

class RefundCache(db.Model):
    """
    One row per refund, added by Step 38.

    Separate from orders_cache because monthly Returns belongs to the month the
    REFUND was processed, not the month of the order. A per-order total summed
    by order_date silently moves money between months while leaving the annual
    figure correct — so nothing would ever flag it except finance.

    `goods_subtotal` is Shopify's "Returns" line (items sent back, excluding
    refunded tax and shipping). `amount_refunded` is the money that actually
    moved. Using the second where the first belongs double-counts tax and
    shipping, which are subtracted by their own lines in the breakdown.
    """
    __tablename__ = 'refunds_cache'

    id                = db.Column(db.Integer, primary_key=True)
    shopify_refund_id = db.Column(db.String(64), unique=True, nullable=False)
    shopify_order_id  = db.Column(db.String(64), nullable=False, index=True)
    # processed_at (when the money moved), falling back to created_at.
    refund_date       = db.Column(db.DateTime, nullable=True, index=True)
    goods_subtotal    = db.Column(db.Numeric(12, 2), nullable=True)
    goods_tax         = db.Column(db.Numeric(12, 2), nullable=True)
    amount_refunded   = db.Column(db.Numeric(12, 2), nullable=True)
    currency          = db.Column(db.String(8), nullable=True)
    cached_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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

    # 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
    status      = db.Column(db.String(16), nullable=False, default='pending', index=True)

    # Set by a person who wants this to stop.
    #
    # A flag rather than killing the thread: the sync writes in chunks inside a
    # transaction, and terminating it mid-chunk would leave the cache half
    # updated with no record of where it stopped. The loop checks this between
    # chunks and unwinds cleanly, so "cancelled" means a known state rather than
    # an unknown one.
    cancel_requested = db.Column(db.Boolean, nullable=False, default=False)

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

    resume_cursor = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'kind': self.kind,
            'status': self.status,
            # Exposed so the button can say "Stopping…" the moment it is
            # pressed, rather than looking dead until the next chunk boundary.
            'cancel_requested': bool(self.cancel_requested),
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

# ─────────────────────────────────────────────────────────────────────────────
# SYNC STATE — per-entity incremental-sync watermark
# ─────────────────────────────────────────────────────────────────────────────

class SyncState(db.Model):
    """
    One row per sync entity ('orders' | 'customers' | 'products').
    Holds the high-water mark: the moment we last *successfully* pulled that
    entity from Shopify. Each delta run asks Shopify for records with
    updated_at >= (watermark - safety buffer), so only changes get fetched.

    watermark is NULL until the first successful sync — NULL means
    "never synced, do a full backfill".
    """
    __tablename__ = "sync_state"

    id         = db.Column(db.Integer, primary_key=True)
    kind       = db.Column(db.String(64), unique=True, nullable=False)
    watermark  = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SyncState {self.kind} watermark={self.watermark}>"
    
# ─────────────────────────────────────────────────────────────────────────────
# META CONNECTIONS — stores OAuth-issued tokens per IG/Page connection
# ─────────────────────────────────────────────────────────────────────────────

class MetaConnection(db.Model):
    """
    One row per IG Business Account + Facebook Page connected through OAuth.
    Replaces the FB_ACCESS_TOKEN env var approach with per-connection tokens
    issued through the proper Facebook Login for Business flow.
    """
    __tablename__ = "meta_connections"

    id                       = db.Column(db.Integer, primary_key=True)
    # Which auth user inside our app connected this — supports multi-tenant later.
    auth_user_id             = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=True)
    # Facebook Page identity
    # Nullable: an Instagram-Login connection authorises the IG account
    # directly and has no Facebook Page behind it. Postgres allows repeated
    # NULLs under a UNIQUE index, so several such rows coexist fine.
    page_id                  = db.Column(db.String(64), unique=True, nullable=True)
    page_name                = db.Column(db.String(256), nullable=True)
    page_access_token        = db.Column(db.Text, nullable=True)
    # Instagram Business Account connected to that Page
    ig_business_account_id   = db.Column(db.String(64), nullable=True)
    ig_username              = db.Column(db.String(256), nullable=True)
    # Long-lived user token (60-day expiry; used to refresh page tokens if needed)
    user_access_token        = db.Column(db.Text, nullable=True)
    token_expires_at         = db.Column(db.DateTime, nullable=True)
    # ── Instagram API with Instagram Login ──────────────────────────────────
    # A second, independent credential for the same account. Facebook Login
    # gives a Page token that cannot message a customer without Advanced
    # Access; the Instagram Login token can. Stored per connection so several
    # accounts stay live at once — replies go out from whichever account the
    # customer actually messaged.
    #
    # Unlike page tokens these EXPIRE (60 days) and must be refreshed while
    # still valid — see refresh_ig_login_tokens().
    ig_login_user_id         = db.Column(db.String(64), nullable=True)
    ig_login_token           = db.Column(db.Text, nullable=True)
    ig_login_expires_at      = db.Column(db.DateTime, nullable=True)
    # Permissions granted in this connection
    scopes                   = db.Column(db.JSON, nullable=True)
    # Lifecycle
    connected_at             = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_verified_at         = db.Column(db.DateTime, nullable=True)
    is_active                = db.Column(db.Boolean, default=True, nullable=False)

    auth_user = db.relationship("AuthUser", foreign_keys=[auth_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'page_id': self.page_id,
            'page_name': self.page_name,
            'ig_business_account_id': self.ig_business_account_id,
            'ig_username': self.ig_username,
            'scopes': self.scopes or [],
            'connected_at': self.connected_at.isoformat() if self.connected_at else None,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
            'token_expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f"<MetaConnection page={self.page_name} ig={self.ig_username}>"

# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION ATTRIBUTIONS — links a Shopify order back to the DM that drove it
# ─────────────────────────────────────────────────────────────────────────────

class ConversionAttribution(db.Model):
    __tablename__ = "conversion_attributions"

    id                 = db.Column(db.Integer, primary_key=True)

    shopify_order_id   = db.Column(db.String(64), unique=True, nullable=False)
    order_number       = db.Column(db.String(128), nullable=True)
    order_total        = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    # Shopify's own total_tax for the order. NULL means we never captured it
    # (rows written before this column existed) — those fall back to the flat
    # VAT divisor, which is the old guess, so old data doesn't silently change
    # meaning. total_price includes tax, so net revenue = order_total - order_tax.
    order_tax          = db.Column(db.Numeric(12, 2), nullable=True)
    order_currency     = db.Column(db.String(8), nullable=True)
    order_date         = db.Column(db.DateTime, nullable=False)

    conversation_id    = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=True, index=True)
    message_id         = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=True, index=True)
    utm_token          = db.Column(db.String(128), nullable=True, index=True)

    minutes_to_convert = db.Column(db.Integer, nullable=True)
    attributed_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    product_handle     = db.Column(db.String(255), nullable=True)

    conversation = db.relationship("Conversation", foreign_keys=[conversation_id])
    message      = db.relationship("Message", foreign_keys=[message_id])

    def to_dict(self):
        return {
            'id': self.id,
            'shopify_order_id': self.shopify_order_id,
            'order_number': self.order_number,
            'order_total': float(self.order_total or 0),
            'order_tax': float(self.order_tax) if self.order_tax is not None else None,
            'order_currency': self.order_currency,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'conversation_id': self.conversation_id,
            'message_id': self.message_id,
            'utm_token': self.utm_token,
            'minutes_to_convert': self.minutes_to_convert,
            'attributed_at': self.attributed_at.isoformat() if self.attributed_at else None,
            'product_handle': self.product_handle,
        }

    def __repr__(self):
        return f"<ConversionAttribution order={self.order_number} via msg={self.message_id}>"
    
class AppSettings(db.Model):
    """Singleton (id=1) JSON-backed org settings. Edited via the Settings page."""
    __tablename__ = 'app_settings'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class InventoryMap(db.Model):
    """inventory_item_id → product/variant, so inventory_levels/update webhooks
    (which carry only inventory_item_id) resolve to a product in O(1)."""
    __tablename__ = "inventory_map"
    inventory_item_id  = db.Column(db.String(64), primary_key=True)
    shopify_product_id = db.Column(db.String(64), nullable=False, index=True)
    shopify_variant_id = db.Column(db.String(64), nullable=True)
    updated_at         = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConversationRead(db.Model):
    """Per-user read state — tracks how far each staff member has read in each
    conversation, so unread is personal (an admin opening a chat doesn't clear
    an agent's unread)."""
    __tablename__ = "conversation_reads"
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey("auth_users.id"), nullable=False)
    conversation_id      = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    last_read_message_id = db.Column(db.Integer, nullable=True)
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'conversation_id', name='uq_conv_read_user_conv'),)