"""
app/settings.py
Org-level application settings — one JSON-backed row (id=1), admin-editable.
Consumers read via get_section(); values fall back to env/hardcoded defaults
until an admin overrides them, so behavior is unchanged out of the box.
"""
import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app import db
from app.models import AppSettings, AuthUser
from app.auth import current_user_id
from app.utils.logger import log_event

settings_bp = Blueprint('settings', __name__, url_prefix='/api')

DEFAULTS = {
    "handoff": {
        "max_agent_load": int(os.getenv("MAX_AGENT_LOAD", "10")),
        "presence_window_seconds": int(os.getenv("PRESENCE_WINDOW_SECONDS", "300")),
        # How long a conversation may sit in the human queue with nobody on it
        # before supervisors are told. Escalations auto-assign, so anything
        # reaching this threshold means auto-assignment couldn't place it (no
        # active agents) or someone deliberately unassigned it.
        "unclaimed_alert_minutes": int(os.getenv("UNCLAIMED_ALERT_MINUTES", "15")),
        # How long a customer may wait on an agent who already owns the
        # conversation before it shows in that agent's "Needs Attention" panel.
        "agent_waiting_minutes": int(os.getenv("AGENT_WAITING_MINUTES", "10")),
        # Close a conversation after this many days of silence — but only when
        # WE spoke last. If the customer spoke last we still owe them a reply,
        # and auto-closing that would hide a dropped customer rather than
        # finish a conversation. 0 disables auto-resolution entirely.
        "auto_resolve_days": int(os.getenv("AUTO_RESOLVE_DAYS", "14")),
        "bridging_reply": (
            "Thanks for reaching out — I'm connecting you with a member of our team "
            "who'll get back to you shortly. We appreciate your patience."
        ),
    },
    "business": {
        "store_name": "Shop Zetu",
        # Email patterns that mark a Shopify customer as OURS, not a customer.
        #
        # Retail tills are recorded as customers. "Vivo - Yaya Centre" bills
        # walk-in sales to vivo.yaya@vivoactivewear.com, which then ranks first
        # in Top Spenders and Most Frequent Buyers — a shop, presented as your
        # best customer, on the one list people read to answer "who should we
        # look after".
        #
        # Excluded accounts are NOT deleted or hidden from the database: they
        # stay searchable, stay linkable to a conversation, and stay in the
        # totals. They stop being *ranked* as customers, and the page carries a
        # "Show internal" toggle so the filtering is visible rather than a
        # silent rule nobody can see.
        #
        # SQL LIKE patterns, matched case-insensitively.
        "internal_email_patterns": ["%@vivoactivewear.com"],
        # Freeform knowledge the assistant should have about the business.
        #
        # Every other field here answers one specific question — hours, phone,
        # email — and there was nowhere to put anything that did not fit that
        # shape. Shop Zetu is an amalgamation of brands, it is online-only, and
        # Vivo products are also carried in Vivo's own physical stores. None of
        # that is a field, all of it changes the answer, and until now the only
        # place to say it was the system prompt — the one control that governs
        # every reply on every channel and is deliberately hard to reach.
        #
        # Goes into the prompt verbatim under "About the business", so it is
        # also the fastest way to correct the assistant when it states
        # something wrong: write the true version here and it stops.
        "about": "",
        "hours": "",
        "phone": "",
        "whatsapp": "",
        "email": "",
        # IANA zone the business operates in. Analytics windows ("today",
        # "this week", "this month") are calendar periods in THIS zone —
        # timestamps are stored as naive UTC, so without it "today" would
        # start at 3am local.
        "timezone": os.getenv("BUSINESS_TIMEZONE", "Africa/Nairobi"),
        # 'monday' (ISO) or 'sunday' — where "this week" starts.
        "week_starts_on": os.getenv("WEEK_STARTS_ON", "monday"),
    },
    "delivery": {
        "zones": [],
        "notes": "",
    },
    "notifications": {
        "discord_enabled": True,
        "discord_webhook_url": "",
        "discord_min_severity": "warning",
    },
    "ai": {
        # Master switch. When False, NO automated reply is sent on any channel.
        # Inbound is still received, stored and displayed — agents reply by hand.
        "enabled": True,
    },
    "conversations": {
        # A customer replying soon after you resolved their chat almost always
        # means the chat was resolved too early — same subject, same session.
        # Weeks later it is a new enquiry. Within this many hours we re-open the
        # resolved conversation instead of starting a fresh one. 0 disables it
        # and every reply after resolve starts a new thread.
        "reopen_resolved_within_hours": 24,
    },
    "alerts": {
        # Per-source watermarks: {"integrations.meta.send": "2026-07-31T13:45:00"}.
        # A fault group is hidden while its newest occurrence is older than the
        # watermark for that source. Deliberately NOT a list of dismissed ids —
        # a watermark is bounded (one entry per source, ~13 of them) and it means
        # a FRESH failure of an already-acknowledged source alerts again, which
        # is the behaviour you want: you acknowledged what you had seen, not the
        # problem forever.
        "acknowledged": {},
    },
}

def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _row():
    row = AppSettings.query.get(1)
    if row is None:
        row = AppSettings(id=1, data={})
        db.session.add(row)
        db.session.commit()
    return row


def get_settings() -> dict:
    """Full settings dict — stored overrides layered over DEFAULTS."""
    try:
        return _merge(DEFAULTS, _row().data or {})
    except Exception:
        return {k: dict(v) for k, v in DEFAULTS.items()}


def get_section(name: str) -> dict:
    """One section's settings with defaults applied."""
    return get_settings().get(name, {}) or {}


def _require_admin():
    user = AuthUser.query.get(current_user_id())
    return user if (user and user.role == 'admin') else None


def business_timezone():
    """
    The org's IANA timezone as a tzinfo. Falls back to Africa/Nairobi if the
    setting is missing or names a zone this host's tz database doesn't know,
    so a bad value degrades to the old behaviour instead of 500-ing analytics.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    name = "Africa/Nairobi"
    try:
        name = (get_section("business").get("timezone") or "").strip() or name
    except Exception:
        pass
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("Africa/Nairobi")


def week_starts_on_sunday() -> bool:
    """True if 'this week' should run Sunday–Saturday rather than Monday–Sunday."""
    try:
        return (get_section("business").get("week_starts_on") or "").strip().lower() == "sunday"
    except Exception:
        return False

def format_delivery_for_prompt() -> str:
    """Delivery zones + notes for the AI system prompt. Empty if unconfigured."""
    try:
        d = get_section("delivery")
    except Exception:
        return ""
    lines = []
    for z in (d.get("zones") or []):
        if not isinstance(z, dict):
            continue
        name = (z.get("name") or "").strip()
        if not name:
            continue
        bits = [name]
        if (z.get("fee") or "").strip(): bits.append(f"fee: {z['fee'].strip()}")
        if (z.get("eta") or "").strip(): bits.append(f"ETA: {z['eta'].strip()}")
        lines.append("  - " + " | ".join(bits))
    zone_block = ("Delivery zones:\n" + "\n".join(lines)) if lines else ""
    notes = (d.get("notes") or "").strip()
    parts = [p for p in (zone_block, (f"Notes: {notes}" if notes else "")) if p]
    return "\n".join(parts)

def discord_config() -> dict:
    """Resolved Discord config: URL (settings → env fallback), enabled, min severity."""
    n = {}
    try:
        n = get_section("notifications")
    except Exception:
        pass
    url = (n.get("discord_webhook_url") or "").strip() or os.getenv("DISCORD_WEBHOOK_URL", "")
    return {
        "url": url,
        "enabled": n.get("discord_enabled", True),
        "min_severity": n.get("discord_min_severity", "warning"),
    }


def discord_webhook_for(severity: str):
    """Webhook URL if a `severity` ('warning'|'failure') alert should send, else None."""
    cfg = discord_config()
    if not cfg["url"] or not cfg["enabled"]:
        return None
    if cfg["min_severity"] == "failure" and severity == "warning":
        return None
    return cfg["url"]


@settings_bp.route('/settings/notifications/test', methods=['POST'])
@jwt_required()
def test_discord():
    if not _require_admin():
        return jsonify({'error': 'Only admins can update settings'}), 403
    import requests as _r
    data = request.get_json(silent=True) or {}
    url = (data.get('webhook_url') or '').strip() or discord_config()["url"]
    if not url:
        return jsonify({'error': 'No Discord webhook configured.'}), 400
    try:
        r = _r.post(url, json={
            "username": "Sync Alerts",
            "embeds": [{"title": "✅ Test alert",
                        "description": "Your Shop Zetu Discord alerts are working.",
                        "color": 3066993}],
        }, timeout=5)
        if r.status_code >= 400:
            return jsonify({'error': f'Discord returned {r.status_code}'}), 400
        return jsonify({'message': 'Test alert sent.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 502
    
@settings_bp.route('/settings', methods=['GET'])
@jwt_required()
def read_settings():
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403
    cfg = discord_config()
    return jsonify({
        'settings': get_settings(),
        # The webhook URL can come from the settings row OR from the
        # DISCORD_WEBHOOK_URL environment variable, and discord_config()
        # resolves both. The page was reading the stored blob directly, so a
        # webhook configured by env showed as "not delivering" when alerts were
        # in fact going out. The resolved answer is reported here instead of
        # being re-derived — badly — in the UI.
        'resolved': {
            'discord_delivering': bool(cfg['url'] and cfg['enabled']),
            'discord_url_source': ('settings' if (get_section('notifications').get('discord_webhook_url') or '').strip()
                                   else ('env' if cfg['url'] else None)),
        },
    }), 200


@settings_bp.route('/settings/timezones', methods=['GET'])
@jwt_required()
def list_timezones():
    """Every IANA zone this host knows, for the Business info picker."""
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403
    from zoneinfo import available_timezones
    return jsonify({'timezones': sorted(available_timezones())}), 200


# Bounds for every numeric setting, checked server-side.
#   section, key -> (label, minimum, maximum, what 0 means if it is allowed)
# The form already range-checks these, but a form is not a boundary: the PATCH
# route accepts any JSON, and each of these is read back through int() inside a
# background job — auto-assignment, the unclaimed-alert sweep, the auto-resolve
# cron. A string that int() can't parse doesn't fail here where an admin would
# see it; it fails later, in a job nobody is watching, and assignment quietly
# stops. Bounds live here so the rule holds no matter what calls the API.
NUMERIC_BOUNDS = {
    ('handoff', 'max_agent_load'):             ('Max load', 1, 100, None),
    ('handoff', 'presence_window_seconds'):    ('Presence window', 30, 3600, None),
    ('handoff', 'unclaimed_alert_minutes'):    ('Unclaimed alert', 1, 1440, None),
    ('handoff', 'agent_waiting_minutes'):      ('Agent wait flag', 1, 1440, None),
    ('handoff', 'auto_resolve_days'):          ('Auto-resolve', 0, 365, 'disables auto-resolve'),
    ('conversations', 'reopen_resolved_within_hours'):
                                               ('Re-open window', 0, 720, 'always starts a new chat'),
}


def _validate_patch(patch: dict):
    """
    Reject values that would silently misbehave. business_timezone() falls
    back to Nairobi on an unknown zone, which is right at read time but wrong
    at write time — an admin who fat-fingers a zone should be told, not left
    wondering why the Dashboard's "Today" never moved.
    Returns an error string, or None if the patch is fine.
    """
    for (section, key), (label, lo, hi, zero_means) in NUMERIC_BOUNDS.items():
        body = patch.get(section)
        if not isinstance(body, dict) or key not in body:
            continue
        raw = body.get(key)
        if isinstance(raw, bool):          # bool is an int subclass; not a count
            return f'{label} must be a number.'
        try:
            val = int(raw)
        except (TypeError, ValueError):
            return f'{label} must be a whole number, not "{raw}".'
        if val < lo or val > hi:
            hint = f' ({lo} {zero_means})' if zero_means and lo == 0 else ''
            return f'{label} must be between {lo} and {hi}{hint}.'
        body[key] = val                    # store the int, not "14"

    biz = patch.get('business')
    if not isinstance(biz, dict):
        return None

    if 'timezone' in biz:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        name = (biz.get('timezone') or '').strip()
        if not name:
            return 'Timezone is required.'
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            return f'Unknown timezone "{name}". Use an IANA name such as Africa/Nairobi.'

    if 'week_starts_on' in biz:
        if (biz.get('week_starts_on') or '').strip().lower() not in ('monday', 'sunday'):
            return 'Week starts on must be either "monday" or "sunday".'

    return None


@settings_bp.route('/settings', methods=['PATCH'])
@jwt_required()
def update_settings():
    if not _require_admin():
        return jsonify({'error': 'Only admins can update settings'}), 403
    patch = request.get_json(silent=True) or {}
    if not isinstance(patch, dict):
        return jsonify({'error': 'Invalid payload'}), 400
    err = _validate_patch(patch)
    if err:
        return jsonify({'error': err}), 400
    row = _row()
    row.data = _merge(row.data or {}, patch)
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'settings': get_settings()}), 200

def _ai_handover_counts():
    """How many conversations the global switch is currently affecting."""
    from app.models import Conversation
    live = (Conversation.query
            .filter(Conversation.status != 'resolved',
                    Conversation.ai_enabled.is_(True))
            .count())
    restorable = (Conversation.query
                  .filter(Conversation.status != 'resolved',
                          Conversation.ai_auto_paused_at.isnot(None))
                  .count())
    return live, restorable


@settings_bp.route('/settings/ai/handover', methods=['GET'])
@jwt_required()
def ai_handover_status():
    """
    What turning the master switch would affect right now.

    The Settings toggle asks this before it acts so the prompt can state a real
    number instead of a vague warning.

    Admin-only, like every other read in this file. It was added without a
    guard while the POST beside it got one — the page is admin-only so nothing
    was reachable in practice, but "nothing links to it" is not a permission
    check, and every neighbouring route here proves the expectation.
    """
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    live, restorable = _ai_handover_counts()
    return jsonify({
        'ai_enabled': bool(get_section('ai').get('enabled', True)),
        'live_ai_conversations': live,
        'restorable': restorable,
    }), 200


@settings_bp.route('/settings/ai/handover', methods=['POST'])
@jwt_required()
def ai_handover():
    """
    Move conversations between the AI and the human queue when the master
    switch flips.

    Two actions, and the split matters:

      queue   — everything the AI currently holds is switched off and stamped
                with ai_auto_paused_at, which drops it into the Unclaimed
                bucket where agents can see it. The stamp is what makes this
                reversible.

      restore — hands back exactly the stamped set. Conversations an agent
                turned off by hand were never stamped (and the per-conversation
                toggle clears the stamp), so a restore cannot take a thread away
                from the person who claimed it.

    Doing this as an explicit action rather than a side effect of PATCHing the
    setting keeps the destructive part opt-in: an admin who just wants the AI
    quiet for ten minutes should not have their whole queue redistributed.
    """
    if not _require_admin():
        return jsonify({'error': 'Only admins can change AI handover'}), 403

    from app.models import Conversation
    action = (request.get_json(silent=True) or {}).get('action')
    now = datetime.utcnow()

    if action == 'queue':
        rows = (Conversation.query
                .filter(Conversation.status != 'resolved',
                        Conversation.ai_enabled.is_(True))
                .all())
        for c in rows:
            c.ai_enabled = False
            c.ai_auto_paused_at = now
            if c.ai_disabled_at is None:
                c.ai_disabled_at = now
            # Also flip the status, or "queue them for agents" queues them where
            # no agent can look. An agent's inbox is scoped to
            #   assigned_to == me  OR  (assigned_to IS NULL AND status = 'human_override')
            # so an unassigned conversation left at 'active' is visible only to
            # supervisors and admins. It would sit in the Unclaimed chip — which
            # is not role-scoped the same way — while every agent's inbox showed
            # nothing. This mirrors what the per-conversation AI toggle already
            # does when a human takes over.
            if c.status == 'active':
                c.status = 'human_override'
        db.session.commit()
        log_event("info", "settings.ai_queued_for_humans",
                  f"Global AI switch off — {len(rows)} conversations queued for agents")
        return jsonify({'action': 'queue', 'affected': len(rows)}), 200

    if action == 'restore':
        rows = (Conversation.query
                .filter(Conversation.status != 'resolved',
                        Conversation.ai_auto_paused_at.isnot(None))
                .all())
        for c in rows:
            c.ai_enabled = True
            c.ai_auto_paused_at = None
            c.ai_disabled_at = None
            # Undo the status flip too, so a restored conversation is back to
            # plain AI-handled rather than looking half-escalated forever.
            if c.status == 'human_override':
                c.status = 'active'
        db.session.commit()
        log_event("info", "settings.ai_restored_from_queue",
                  f"Global AI switch on — {len(rows)} conversations handed back to the AI")
        return jsonify({'action': 'restore', 'affected': len(rows)}), 200

    return jsonify({'error': "action must be 'queue' or 'restore'"}), 400


@settings_bp.route('/settings/integrations', methods=['GET'])
@jwt_required()
def integrations_status():
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403

    import os
    from app.models import MetaConnection, SyncJob

    # ── Meta: OAuth connection row, else legacy env token ──
    meta = {'connected': False, 'source': None}
    try:
        conn = (MetaConnection.query
                .filter_by(is_active=True)
                .order_by(MetaConnection.connected_at.desc())
                .first())
        if conn:
            # The expiry date was already displayed, but it played no part in
            # the verdict — a token two days from death still showed a green
            # "Connected". Instagram tokens last 60 days and a daily cron
            # refreshes them, so anything inside a week means that refresh has
            # been failing for days and messaging is about to stop dead.
            exp = conn.token_expires_at
            days_left = None
            if exp:
                days_left = int((exp - datetime.utcnow()).total_seconds() // 86400)
            meta = {
                'connected': True, 'source': 'oauth',
                'page_name': conn.page_name,
                'ig_username': conn.ig_username,
                'token_expires_at': exp.isoformat() if exp else None,
                'token_days_left': days_left,
                'token_expired': days_left is not None and days_left < 0,
                'token_expiring_soon': days_left is not None and 0 <= days_left <= 7,
            }
        elif os.getenv('FB_PAGE_ID') and os.getenv('FB_ACCESS_TOKEN'):
            meta = {'connected': True, 'source': 'env'}
    except Exception:
        pass

    # ── Shopify: inferred from sync-job health ──
    #
    # "Connected" used to mean "a sync succeeded at some point in history", so
    # the card stayed green forever once the first sync landed. On this very
    # database the newest success is 32 days old and the badge still read
    # Connected with no warning — a diagnostics panel that can only say "fine"
    # is worse than none, because it reassures you instead of staying silent.
    # Freshness is now part of the verdict: syncs run every 3h, so we allow
    # three missed cycles before calling a feed stale — enough to ride out one
    # transient failure and its retry without flapping.
    STALE_AFTER_HOURS = 9
    shopify = {'connected': False, 'last_sync': {}, 'recent_failed': False,
               'stale': False, 'stale_kinds': [], 'failed_recently': 0}
    try:
        now = datetime.utcnow()
        last_sync, stale_kinds = {}, []
        for label in ('products', 'orders', 'customers'):
            job = (SyncJob.query
                   .filter(SyncJob.kind.like(f'{label}%'), SyncJob.status == 'success')
                   .order_by(SyncJob.finished_at.desc())
                   .first())
            when = job.finished_at if (job and job.finished_at) else None
            last_sync[label] = when.isoformat() if when else None
            if when is None or (now - when).total_seconds() > STALE_AFTER_HOURS * 3600:
                stale_kinds.append(label)

        # A window, not a single row. Looking only at the newest job meant one
        # success on top of a week of failures reported a clean bill of health.
        failed_recently = (SyncJob.query
                           .filter(SyncJob.status == 'failed',
                                   SyncJob.started_at > now - timedelta(hours=24))
                           .count())

        shopify = {
            'connected': any(last_sync.values()),
            'last_sync': last_sync,
            'stale': bool(stale_kinds),
            'stale_kinds': stale_kinds,
            'stale_after_hours': STALE_AFTER_HOURS,
            'failed_recently': failed_recently,
            # Kept for compatibility, but now means "something is wrong right
            # now", which is what every caller already assumed it meant.
            'recent_failed': bool(stale_kinds) or failed_recently > 0,
        }
    except Exception:
        pass

    # ── Brevo: key + verified sender present ──
    brevo = {
        'configured': bool(os.getenv('BREVO_API_KEY') and os.getenv('SMTP_FROM')),
        'sender': os.getenv('SMTP_FROM'),
    }

    return jsonify({'integrations': {'meta': meta, 'shopify': shopify, 'brevo': brevo}}), 200

def format_business_for_prompt() -> str:
    """Business-info block (name / hours / contact) for the AI system prompt."""
    try:
        b = get_section("business")
    except Exception:
        return ""
    lines = []
    if b.get("store_name"):
        lines.append(f"Store name: {b['store_name']}")
    # Before the contact details on purpose. This is the part that shapes what
    # the assistant says rather than just supplying a fact to read out, and the
    # model weights early context more heavily.
    about = (b.get("about") or "").strip()
    if about:
        lines.append("About the business:\n" + about)
    if b.get("hours"):
        lines.append(f"Opening hours: {b['hours']}")
    contact = []
    if b.get("phone"):    contact.append(f"phone {b['phone']}")
    if b.get("whatsapp"): contact.append(f"WhatsApp {b['whatsapp']}")
    if b.get("email"):    contact.append(f"email {b['email']}")
    if contact:
        lines.append("Contact: " + ", ".join(contact))
    return "\n".join(lines)


# Replaces GET /settings/business-locations, which read kind='locations' —
# Shopify's FULFILMENT locations, warehouses and pickup points, not shops a
# customer can walk into. Nothing ever called it, so the only thing it could
# have done was mislead whoever wired a UI to it first.
STORE_FIELDS = ('name', 'address', 'area', 'phone', 'hours')


@settings_bp.route('/settings/brand-stores', methods=['GET'])
@jwt_required()
def get_brand_stores():
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403
    from app.models import StoreInfoCache
    row = StoreInfoCache.query.filter_by(kind='brand_stores').first()
    return jsonify({
        'stores': (row.data if (row and isinstance(row.data, list)) else []),
        'updated_at': row.updated_at.isoformat() if (row and row.updated_at) else None,
    }), 200


@settings_bp.route('/settings/brand-stores', methods=['PUT'])
@jwt_required()
def put_brand_stores():
    """
    Replace the whole list. A store is only kept if it has a name.

    Whole-list replacement rather than per-row edits because the list is short,
    always edited as a table, and the alternative needs stable ids on rows that
    have none. The cost is that two admins saving at once lose one set of
    edits; the benefit is that a half-applied reorder can't leave the assistant
    reciting an address that belongs to a different branch.
    """
    if not _require_admin():
        return jsonify({'error': 'Only admins can edit settings'}), 403

    payload = request.get_json(silent=True) or {}
    incoming = payload.get('stores')
    if not isinstance(incoming, list):
        return jsonify({'error': 'Expected a "stores" array'}), 400

    cleaned = []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        store = {k: str(item.get(k) or '').strip() for k in STORE_FIELDS}
        # A nameless row is a half-filled form, not a shop. Dropping it here
        # keeps the prompt free of "  - | Ground Floor | +254…" lines, which
        # read to the model as a store whose name it simply doesn't know.
        if store['name']:
            cleaned.append(store)

    from app.models import StoreInfoCache
    row = StoreInfoCache.query.filter_by(kind='brand_stores').first()
    if row is None:
        row = StoreInfoCache(kind='brand_stores', data=cleaned)
        db.session.add(row)
    else:
        row.data = cleaned
        row.updated_at = datetime.utcnow()
    db.session.commit()

    # The prompt reads through a process-local cache, so without this the
    # assistant keeps giving the old address until the worker restarts.
    try:
        from app.store_info import _cache_invalidate
        _cache_invalidate('brand_stores')
    except Exception:
        pass

    log_event("info", "settings.brand_stores_saved",
              f"Brand store list saved — {len(cleaned)} stores")
    return jsonify({'stores': cleaned}), 200

@settings_bp.route('/settings/reset', methods=['POST'])
@jwt_required()
def reset_settings():
    if not _require_admin():
        return jsonify({'error': 'Only admins can reset settings'}), 403
    row = _row()
    row.data = {}                       # clears overrides — DEFAULTS take over
    row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'settings': get_settings()}), 200

@settings_bp.route('/settings/webhooks', methods=['GET'])
@jwt_required()
def list_webhooks():
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403
    from app.integrations.shopify import list_shopify_webhooks
    try:
        hooks = list_shopify_webhooks()
        return jsonify({'webhooks': [
            {'id': w.get('id'), 'topic': w.get('topic'),
             'address': w.get('address'), 'created_at': w.get('created_at')}
            for w in hooks
        ]}), 200
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 502


@settings_bp.route('/settings/webhooks/register', methods=['POST'])
@jwt_required()
def register_webhooks():
    if not _require_admin():
        return jsonify({'error': 'Only admins can register webhooks'}), 403
    import os
    from flask import current_app
    from app.integrations.shopify import register_shopify_webhooks
    base_url = (os.getenv('PUBLIC_BASE_URL')
                or current_app.config.get('PUBLIC_BASE_URL')
                or request.host_url).rstrip('/')
    if not base_url:
        return jsonify({'error': 'PUBLIC_BASE_URL not configured'}), 400
    try:
        return jsonify(register_shopify_webhooks(base_url)), 200
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 502