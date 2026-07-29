"""
app/settings.py
Org-level application settings — one JSON-backed row (id=1), admin-editable.
Consumers read via get_section(); values fall back to env/hardcoded defaults
until an admin overrides them, so behavior is unchanged out of the box.
"""
import os
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app import db
from app.models import AppSettings, AuthUser
from app.auth import current_user_id

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
        "bridging_reply": (
            "Thanks for reaching out — I'm connecting you with a member of our team "
            "who'll get back to you shortly. We appreciate your patience."
        ),
    },
    "business": {
        "store_name": "Shop Zetu",
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
    return jsonify({'settings': get_settings()}), 200


@settings_bp.route('/settings/timezones', methods=['GET'])
@jwt_required()
def list_timezones():
    """Every IANA zone this host knows, for the Business info picker."""
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403
    from zoneinfo import available_timezones
    return jsonify({'timezones': sorted(available_timezones())}), 200


def _validate_patch(patch: dict):
    """
    Reject values that would silently misbehave. business_timezone() falls
    back to Nairobi on an unknown zone, which is right at read time but wrong
    at write time — an admin who fat-fingers a zone should be told, not left
    wondering why the Dashboard's "Today" never moved.
    Returns an error string, or None if the patch is fine.
    """
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
            meta = {
                'connected': True, 'source': 'oauth',
                'page_name': conn.page_name,
                'ig_username': conn.ig_username,
                'token_expires_at': conn.token_expires_at.isoformat() if conn.token_expires_at else None,
            }
        elif os.getenv('FB_PAGE_ID') and os.getenv('FB_ACCESS_TOKEN'):
            meta = {'connected': True, 'source': 'env'}
    except Exception:
        pass

    # ── Shopify: inferred from sync-job health ──
    shopify = {'connected': False, 'last_sync': {}, 'recent_failed': False}
    try:
        last_sync = {}
        for label in ('products', 'orders', 'customers'):
            job = (SyncJob.query
                   .filter(SyncJob.kind.like(f'{label}%'), SyncJob.status == 'success')
                   .order_by(SyncJob.finished_at.desc())
                   .first())
            last_sync[label] = job.finished_at.isoformat() if (job and job.finished_at) else None
        recent = SyncJob.query.order_by(SyncJob.started_at.desc()).first()
        shopify = {
            'connected': any(last_sync.values()),
            'last_sync': last_sync,
            'recent_failed': bool(recent and recent.status == 'failed'),
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
    if b.get("hours"):
        lines.append(f"Opening hours: {b['hours']}")
    contact = []
    if b.get("phone"):    contact.append(f"phone {b['phone']}")
    if b.get("whatsapp"): contact.append(f"WhatsApp {b['whatsapp']}")
    if b.get("email"):    contact.append(f"email {b['email']}")
    if contact:
        lines.append("Contact: " + ", ".join(contact))
    return "\n".join(lines)


@settings_bp.route('/settings/business-locations', methods=['GET'])
@jwt_required()
def business_locations():
    if not _require_admin():
        return jsonify({'error': 'Only admins can view settings'}), 403
    from app.models import StoreInfoCache
    row = StoreInfoCache.query.filter_by(kind='locations').first()
    return jsonify({
        'locations': (row.data if (row and isinstance(row.data, list)) else []),
        'updated_at': row.updated_at.isoformat() if (row and row.updated_at) else None,
    }), 200

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