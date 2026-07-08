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


@settings_bp.route('/settings', methods=['PATCH'])
@jwt_required()
def update_settings():
    if not _require_admin():
        return jsonify({'error': 'Only admins can update settings'}), 403
    patch = request.get_json(silent=True) or {}
    if not isinstance(patch, dict):
        return jsonify({'error': 'Invalid payload'}), 400
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