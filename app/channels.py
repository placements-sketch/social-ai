"""
app/channels.py
Channels (social platform) administration.

Endpoints (all JWT-protected, /api prefix):
  GET    /api/channels                  list all channels with derived stats
  GET    /api/channels/<id>             single channel detail
  PATCH  /api/channels/<id>             update mutable fields (enabled)
  POST   /api/channels/<id>/test        test connection (stubbed for now)

Design notes:
- Credentials live in .env and are reported only as set/not set.
  The body never echoes secret values.
- "Connected" is currently derived from whether the relevant .env vars
  exist. A future real test-connection call would set last_verified_at
  and we'd consider connection healthy = recently verified.
- last_message_at, message_count, unread_count come from the messages
  and conversations tables — channels.last_message_at would drift, so
  we compute it at read time instead of denormalising it.
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app import db
from app.models import AuthUser, Channel, Conversation, Message
from app.auth import log_audit, current_user_id

channels_bp = Blueprint('channels', __name__, url_prefix='/api')


# ─────────────────────────────────────────────
# Which .env keys back each channel
# ─────────────────────────────────────────────
# When ANY of a channel's required keys is missing/blank, credentials_set=False.
# Keep this in lockstep with config.py — adding a channel without updating
# this map will make that channel always read as "not connected".

CHANNEL_CREDENTIAL_KEYS = {
    'instagram_dm':      ['META_PAGE_ACCESS_TOKEN', 'META_VERIFY_TOKEN', 'META_APP_SECRET'],
    'instagram_comment': ['META_PAGE_ACCESS_TOKEN', 'META_VERIFY_TOKEN', 'META_APP_SECRET'],
    'whatsapp':          ['META_PAGE_ACCESS_TOKEN', 'META_VERIFY_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID'],
    'facebook_dm':       ['META_PAGE_ACCESS_TOKEN', 'META_VERIFY_TOKEN', 'META_APP_SECRET'],
    'facebook_comment':  ['META_PAGE_ACCESS_TOKEN', 'META_VERIFY_TOKEN', 'META_APP_SECRET'],
    'tiktok_dm':         ['TIKTOK_APP_ID', 'TIKTOK_ACCESS_TOKEN', 'TIKTOK_VERIFY_TOKEN'],
    'tiktok_comment':    ['TIKTOK_APP_ID', 'TIKTOK_ACCESS_TOKEN', 'TIKTOK_VERIFY_TOKEN'],
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _credentials_set(channel_key: str) -> bool:
    """True iff every .env key required for this channel is populated."""
    keys = CHANNEL_CREDENTIAL_KEYS.get(channel_key, [])
    if not keys:
        return False
    return all(bool(current_app.config.get(k)) for k in keys)


def _public_base_url() -> str:
    """
    Public URL the webhook receivers are reachable at. Configured via
    PUBLIC_BASE_URL in .env (e.g. https://abc123.ngrok-free.app). If not
    set, we fall back to the request's host_url so local Postman testing
    still produces a sensible URL.
    """
    configured = current_app.config.get('PUBLIC_BASE_URL')
    if configured:
        return configured.rstrip('/')
    return request.host_url.rstrip('/')


def _stats_for_channels(channel_keys: list[str]) -> dict[str, dict]:
    """
    Single bulk query returning message_count, unread_count, last_message_at
    for each channel key. Avoids N+1 over the channels list.
    """
    msg_counts = dict(
        db.session.query(Message.channel, func.count(Message.id))
        .filter(Message.channel.in_(channel_keys))
        .group_by(Message.channel)
        .all()
    )
    unread_rows = (
        db.session.query(Conversation.channel, func.sum(Conversation.unread_count))
        .filter(Conversation.channel.in_(channel_keys))
        .group_by(Conversation.channel)
        .all()
    )
    unread_counts = {ch: int(n or 0) for ch, n in unread_rows}

    last_rows = (
        db.session.query(Conversation.channel, func.max(Conversation.last_message_at))
        .filter(Conversation.channel.in_(channel_keys))
        .group_by(Conversation.channel)
        .all()
    )
    last_at = {ch: dt for ch, dt in last_rows}

    return {
        ch: {
            'message_count': int(msg_counts.get(ch, 0)),
            'unread_count': unread_counts.get(ch, 0),
            'last_message_at': last_at[ch].isoformat() if last_at.get(ch) else None,
        }
        for ch in channel_keys
    }


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@channels_bp.route('/channels', methods=['GET'])
@jwt_required()
def list_channels():
    """
    List all channels with derived stats.

    Response:
    {
      "channels": [
        { id, channel, display_name, enabled, connected, credentials_set,
          webhook_url, webhook_path, last_verified_at,
          message_count, unread_count, last_message_at,
          created_at, updated_at },
        ...
      ],
      "public_base_url": "https://..."
    }
    """
    channels = Channel.query.order_by(Channel.id.asc()).all()
    keys = [c.channel for c in channels]
    stats = _stats_for_channels(keys) if keys else {}
    base = _public_base_url()

    return jsonify({
        'channels': [
            c.to_dict(
                public_base_url=base,
                stats=stats.get(c.channel),
                credentials_set=_credentials_set(c.channel),
            )
            for c in channels
        ],
        'public_base_url': base,
    }), 200


@channels_bp.route('/channels/<int:channel_id>', methods=['GET'])
@jwt_required()
def get_channel(channel_id):
    """Single channel detail."""
    channel = Channel.query.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    stats = _stats_for_channels([channel.channel]).get(channel.channel)
    return jsonify({
        'channel': channel.to_dict(
            public_base_url=_public_base_url(),
            stats=stats,
            credentials_set=_credentials_set(channel.channel),
        ),
    }), 200


@channels_bp.route('/channels/<int:channel_id>', methods=['PATCH'])
@jwt_required()
def update_channel(channel_id):
    """
    Update mutable fields on a channel. Currently supports `enabled`.

    Body:
    { "enabled": false }
    """
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    channel = Channel.query.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    data = request.get_json(silent=True) or {}
    changes = {}

    if 'enabled' in data:
        channel.enabled = bool(data['enabled'])
        changes['enabled'] = channel.enabled

    if not changes:
        return jsonify({'error': 'No updatable fields provided'}), 400

    channel.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        current_user.id,
        'update_channel',
        resource_type='channel',
        resource_id=str(channel.id),
        changes=changes,
    )

    stats = _stats_for_channels([channel.channel]).get(channel.channel)
    return jsonify({
        'channel': channel.to_dict(
            public_base_url=_public_base_url(),
            stats=stats,
            credentials_set=_credentials_set(channel.channel),
        ),
    }), 200


@channels_bp.route('/channels/<int:channel_id>/test', methods=['POST'])
@jwt_required()
def test_channel(channel_id):
    """
    Test connection for a channel. STUBBED — returns a realistic structured
    response that the UI can render. When real credentials land, replace the
    body with calls to the integrations.* layer (e.g. ping Meta /me).

    Behaviour:
      - If credentials are not set     -> ok=false, "credentials_not_set"
      - If channel disabled            -> ok=false, "channel_disabled"
      - Otherwise                      -> ok=true, mocked details
    """
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    channel = Channel.query.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    creds_ok = _credentials_set(channel.channel)
    now = datetime.utcnow()

    if not creds_ok:
        return jsonify({
            'ok': False,
            'reason': 'credentials_not_set',
            'message': (
                f'Cannot test {channel.display_name}: required environment variables '
                f'are not set ({", ".join(CHANNEL_CREDENTIAL_KEYS.get(channel.channel, []))}).'
            ),
            'checked_at': now.isoformat(),
            'mocked': True,
        }), 200

    if not channel.enabled:
        return jsonify({
            'ok': False,
            'reason': 'channel_disabled',
            'message': f'{channel.display_name} is disabled. Enable it before testing.',
            'checked_at': now.isoformat(),
            'mocked': True,
        }), 200

    # Stubbed "happy path" — replace with real integration calls when ready.
    channel.last_verified_at = now
    db.session.commit()

    log_audit(
        current_user.id,
        'test_channel',
        resource_type='channel',
        resource_id=str(channel.id),
        changes={'result': 'ok_mocked'},
    )

    return jsonify({
        'ok': True,
        'message': f'{channel.display_name} connection healthy (mocked).',
        'checked_at': now.isoformat(),
        'mocked': True,
        'details': {
            'token_valid': True,
            'token_expires_in_days': 47,
            'webhook_subscribed': True,
            'permissions_granted': True,
        },
    }), 200
