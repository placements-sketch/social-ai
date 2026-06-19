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
    'instagram_dm':      ['FB_ACCESS_TOKEN'],
    'instagram_comment': ['FB_ACCESS_TOKEN'],
    'whatsapp':          ['FB_ACCESS_TOKEN'],
    'facebook_dm':       ['FB_ACCESS_TOKEN'],
    'facebook_comment':  ['FB_ACCESS_TOKEN'],
    'tiktok_dm':         ['TIKTOK_ACCESS_TOKEN'],
    'tiktok_comment':    ['TIKTOK_ACCESS_TOKEN'],
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _credentials_set(channel_key: str) -> bool:
    """True iff every .env key required for this channel is populated."""
    import os
    keys = CHANNEL_CREDENTIAL_KEYS.get(channel_key, [])
    if not keys:
        return False
    return all(bool(os.getenv(k)) for k in keys)


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

    # Notify other admins of enable/disable. Coalesce in case of rapid toggling.
    if 'enabled' in changes:
        from app.notifications import notify_admins
        state = 'enabled' if channel.enabled else 'disabled'
        # Disabling a channel is more impactful than enabling — bump severity.
        sev = 'warning' if not channel.enabled else 'info'
        notify_admins(
            type_='channel_toggled',
            title=f"{channel.display_name} {state}",
            body=f"{current_user.full_name} turned this channel {state}",
            severity=sev,
            resource_type='channel',
            resource_id=channel.id,
            actor_id=current_user.id,
            coalesce=True,
        )

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
    Test connection for a channel by hitting the upstream API.

    Meta channels: GET graph.facebook.com/v25.0/me?access_token=<token>
      - 200 + name field → token valid
      - error JSON → token invalid / expired / wrong scope

    TikTok: not implemented yet — credential presence only.

    Behaviour:
      - credentials not set     → ok=false, "credentials_not_set"
      - channel disabled        → ok=false, "channel_disabled"
      - upstream API call fails → ok=false, "api_error" with detail
      - everything OK           → ok=true with token info
    """
    import os
    import requests as _requests

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
        }), 200

    if not channel.enabled:
        return jsonify({
            'ok': False,
            'reason': 'channel_disabled',
            'message': f'{channel.display_name} is disabled. Enable it before testing.',
            'checked_at': now.isoformat(),
        }), 200

    # ── Meta channels: real /me ping ───────────────────────────────────
    meta_channels = {
        'instagram_dm', 'instagram_comment',
        'facebook_dm', 'facebook_comment',
        'whatsapp',
    }
    if channel.channel in meta_channels:
        token = os.getenv('FB_ACCESS_TOKEN')
        try:
            r = _requests.get(
                'https://graph.facebook.com/v25.0/me',
                params={'access_token': token, 'fields': 'id,name'},
                timeout=10,
            )
            body = r.json() if r.text else {}
        except _requests.RequestException as e:
            from app.notifications import notify_admins
            notify_admins(
                type_='channel_test_failed',
                title=f"{channel.display_name} unreachable",
                body=f"Network error when testing: {str(e)[:200]}",
                severity='urgent',
                resource_type='channel',
                resource_id=channel.id,
                actor_id=current_user.id,
                coalesce=True,
            )
            db.session.commit()
            return jsonify({
                'ok': False,
                'reason': 'network_error',
                'message': f'Could not reach Meta Graph API: {str(e)[:150]}',
                'checked_at': now.isoformat(),
            }), 200

        if r.status_code >= 400 or 'error' in body:
            err = body.get('error', {})
            from app.notifications import notify_admins
            notify_admins(
                type_='channel_test_failed',
                title=f"{channel.display_name} test failed",
                body=f"Meta returned an error: {err.get('message', 'Unknown error')[:200]}",
                severity='urgent',
                resource_type='channel',
                resource_id=channel.id,
                actor_id=current_user.id,
                coalesce=True,
            )
            db.session.commit()
            return jsonify({
                'ok': False,
                'reason': 'api_error',
                'message': (
                    f'Meta returned an error: '
                    f'{err.get("message", "Unknown error")[:200]}'
                ),
                'details': {
                    'status': r.status_code,
                    'code': err.get('code'),
                    'type': err.get('type'),
                },
                'checked_at': now.isoformat(),
            }), 200

        # ── /me succeeded. Now query /debug_token for expiry + scopes ──
        app_id = os.getenv('META_APP_ID')
        app_secret = os.getenv('META_APP_SECRET')
        token_expires_at = None
        token_scopes = None
        debug_error = None

        if app_id and app_secret:
            try:
                dr = _requests.get(
                    'https://graph.facebook.com/v25.0/debug_token',
                    params={
                        'input_token': token,
                        'access_token': f'{app_id}|{app_secret}',
                    },
                    timeout=10,
                )
                dbody = dr.json() if dr.text else {}
                ddata = dbody.get('data') or {}

                # expires_at: Unix timestamp. 0 means "never expires" (long-lived).
                expires_unix = ddata.get('expires_at')
                if expires_unix and expires_unix > 0:
                    token_expires_at = datetime.utcfromtimestamp(expires_unix)
                # else: leave as None — we'll interpret None as "no expiry"

                scopes = ddata.get('scopes') or []
                if scopes:
                    token_scopes = ','.join(scopes)

                if 'error' in dbody:
                    debug_error = dbody['error'].get('message')
            except _requests.RequestException as e:
                debug_error = f'debug_token request failed: {str(e)[:120]}'
        else:
            debug_error = 'META_APP_ID or META_APP_SECRET not set — token expiry unknown'

        # Persist verification + token metadata
        channel.last_verified_at = now
        channel.token_expires_at = token_expires_at
        channel.token_scopes = token_scopes

        # If the token expires within 14 days, warn admins.
        # Coalesced so retesting the same channel doesn't spam.
        if token_expires_at:
            days_left = (token_expires_at - now).days
            if days_left <= 14:
                from app.notifications import notify_admins
                sev = 'urgent' if days_left <= 3 else 'warning'
                notify_admins(
                    type_='channel_token_expiring',
                    title=f"{channel.display_name} token expires in {days_left} days",
                    body=(
                        f"The access token for {channel.display_name} will expire on "
                        f"{token_expires_at.strftime('%b %d')}. Refresh it via Meta soon."
                    ),
                    severity=sev,
                    resource_type='channel',
                    resource_id=channel.id,
                    actor_id=current_user.id,
                    coalesce=True,
                )

        db.session.commit()

        log_audit(
            current_user.id,
            'test_channel',
            resource_type='channel',
            resource_id=str(channel.id),
            changes={'result': 'ok'},
        )

        # Build response with expiry info
        if token_expires_at:
            days_left = (token_expires_at - now).days
            expiry_display = f'Expires in {days_left} days' if days_left > 0 else 'Expired'
        elif debug_error:
            expiry_display = 'Expiry unknown'
        else:
            expiry_display = 'No expiry (long-lived)'

        return jsonify({
            'ok': True,
            'message': f'Connected as "{body.get("name", "unknown")}" — {expiry_display}',
            'checked_at': now.isoformat(),
            'details': {
                'page_id': body.get('id'),
                'page_name': body.get('name'),
                'token_expires_at': token_expires_at.isoformat() if token_expires_at else None,
                'token_scopes': token_scopes.split(',') if token_scopes else [],
                'debug_error': debug_error,
            },
        }), 200

    # ── TikTok: not implemented yet ────────────────────────────────────
    if channel.channel in ('tiktok_dm', 'tiktok_comment'):
        return jsonify({
            'ok': False,
            'reason': 'not_implemented',
            'message': 'TikTok connection test not implemented yet. Credentials are set but cannot be verified.',
            'checked_at': now.isoformat(),
        }), 200

    return jsonify({
        'ok': False,
        'reason': 'unknown_channel',
        'message': f'No test implementation for channel "{channel.channel}".',
        'checked_at': now.isoformat(),
    }), 200