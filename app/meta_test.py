"""
app/meta_test.py
Admin-only diagnostic endpoints that proxy raw Meta Graph API calls, so the
Meta Diagnostics panel can test connectivity without the Page token ever
touching the browser. The token is read server-side via _get_meta_credentials.
"""

import os
import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from app.integrations.meta import (
    _get_meta_credentials,
    GRAPH_API_VERSION,
    subscribe_page_webhooks,
)
from app.utils.logger import log_event

meta_test_bp = Blueprint('meta_test', __name__)

GRAPH = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
IG_USER_ID = "17841412308701394"   # @shopzetu IG business account
PAGE_ID    = "115573226545299"     # Shop Zetu Page


def _require_admin():
    """
    Read the role from the database, not from the token.

    This used to be `get_jwt().get('role') == 'admin'`. The role is stamped into
    the access token at login and those live 24 hours, so demoting an admin left
    them with admin access to these routes — which proxy the Graph API using our
    page token and can rewrite webhook subscriptions — until the token aged out.
    Every other module in the app resolves the role against AuthUser, so
    demotion took effect immediately everywhere except here.
    """
    from app.models import AuthUser
    from app.auth import current_user_id
    user = AuthUser.query.get(current_user_id())
    return bool(user and user.role == 'admin' and user.status == 'active')


def _proxy(url, params):
    """Call Graph with the server-side token, return (json, status)."""
    _, token = _get_meta_credentials()
    if not token:
        return {"error": "No Meta token configured (MetaConnection + env both empty)"}, 400
    params = {**params, "access_token": token}
    try:
        r = requests.get(url, params=params, timeout=15)
        try:
            body = r.json()
        except ValueError:
            body = {"raw": (r.text or "")[:1000]}
        return body, r.status_code
    except requests.RequestException as e:
        log_event("warning", "meta_test.proxy_error", str(e))
        return {"error": str(e)}, 502


@meta_test_bp.route('/api/meta-test/profile', methods=['GET'])
@jwt_required()
def test_profile():
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    body, status = _proxy(f"{GRAPH}/{IG_USER_ID}", {
        "fields": "username,name,followers_count,media_count",
    })
    return jsonify(body), status


@meta_test_bp.route('/api/meta-test/conversations', methods=['GET'])
@jwt_required()
def test_conversations():
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    body, status = _proxy(f"{GRAPH}/{PAGE_ID}/conversations", {
        "platform": "instagram",
        "fields": "id,updated_time",
        "limit": 5,
    })
    return jsonify(body), status


@meta_test_bp.route('/api/meta-test/conversation', methods=['GET'])
@jwt_required()
def test_conversation():
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    conv_id = (request.args.get('id') or '').strip()
    if not conv_id:
        return jsonify({'error': 'Pass ?id=<conversation_id>'}), 400
    body, status = _proxy(f"{GRAPH}/{conv_id}", {
        "fields": "participants,message_count,updated_time,"
                  "messages.limit(15){id,created_time,from,to,message,attachments}",
    })
    return jsonify(body), status


@meta_test_bp.route('/api/meta-test/media', methods=['GET'])
@jwt_required()
def test_media():
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    body, status = _proxy(f"{GRAPH}/{IG_USER_ID}/media", {
        "fields": "id,permalink,caption,timestamp,comments_count,like_count",
        "limit": 10,
    })
    return jsonify(body), status


@meta_test_bp.route('/api/meta-test/subscribed-apps', methods=['GET'])
@jwt_required()
def test_subscribed_apps():
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    page_id, _ = _get_meta_credentials()
    body, status = _proxy(f"{GRAPH}/{page_id or PAGE_ID}/subscribed_apps", {})
    return jsonify(body), status


@meta_test_bp.route('/api/meta-test/webhook-health', methods=['GET'])
@jwt_required()
def webhook_health():
    """
    One call that answers "why am I not receiving webhooks?".

    Checks the three things that silently break delivery and are invisible in
    the App Dashboard:
      1. Is the Page actually subscribed, and to which app?
      2. Does META_APP_SECRET belong to the SAME app that issued the Page
         token? If not, every delivered event fails signature verification.
      3. Does IG_BUSINESS_ACCOUNT_ID match the IG account really linked to the
         Page? If not, outbound-echo filtering misfires.
    """
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403

    page_id, token = _get_meta_credentials()
    if not token:
        return jsonify({'error': 'No Meta token configured'}), 400

    app_id = os.getenv('META_APP_ID')
    app_secret = os.getenv('META_APP_SECRET')
    report = {'page_id': page_id, 'configured_app_id': app_id, 'problems': []}

    # 1. Which apps are subscribed to this Page, and to what fields?
    subs, _ = _proxy(f"{GRAPH}/{page_id}/subscribed_apps", {})
    subscribed = subs.get('data') or []
    report['subscribed_apps'] = [
        {'app_id': a.get('id'), 'name': a.get('name'),
         'fields': a.get('subscribed_fields')}
        for a in subscribed
    ]
    if not subscribed:
        report['problems'].append(
            'Page has NO subscribed apps — POST /{page-id}/subscribed_apps is '
            'required; App Dashboard toggles alone deliver nothing.'
        )
    token_app_ids = [a.get('id') for a in subscribed]

    # 2. Does our app secret belong to the app that owns the Page token?
    if app_id and app_secret:
        try:
            r = requests.get(f"{GRAPH}/debug_token", params={
                'input_token': token,
                'access_token': f'{app_id}|{app_secret}',
            }, timeout=15)
            data = (r.json() or {}).get('data') or {}
            err = (r.json() or {}).get('error') or {}
            report['token_debug'] = {
                'http': r.status_code,
                'token_app_id': data.get('app_id'),
                'is_valid': data.get('is_valid'),
                'expires_at': data.get('expires_at'),
                'scopes': data.get('scopes'),
                'error': err.get('message'),
            }
            if err.get('code') == 100 or (
                data.get('app_id') and data.get('app_id') != app_id
            ):
                report['problems'].append(
                    f'App mismatch: the Page token was issued by app '
                    f'{data.get("app_id") or token_app_ids} but META_APP_ID is '
                    f'{app_id}. Webhook signature verification will reject every '
                    f'event, and the dashboard you configure is not the app that '
                    f'delivers them.'
                )
        except requests.RequestException as e:
            report['token_debug'] = {'error': str(e)}
    else:
        report['problems'].append('META_APP_ID / META_APP_SECRET not configured')

    # 3. Is the IG account we filter against the one actually on the Page?
    linked, _ = _proxy(f"{GRAPH}/{page_id}", {
        'fields': 'instagram_business_account{id,username}',
    })
    linked_ig = (linked.get('instagram_business_account') or {})
    env_ig = os.getenv('IG_BUSINESS_ACCOUNT_ID')
    report['instagram'] = {
        'linked_to_page': linked_ig,
        'IG_BUSINESS_ACCOUNT_ID': env_ig,
    }
    if linked_ig.get('id') and env_ig and linked_ig['id'] != env_ig:
        report['problems'].append(
            f'IG_BUSINESS_ACCOUNT_ID ({env_ig}) is not the account linked to '
            f'this Page ({linked_ig.get("id")} / @{linked_ig.get("username")}). '
            f'Outbound-echo filtering will not match.'
        )

    report['healthy'] = not report['problems']
    return jsonify(report), 200


@meta_test_bp.route('/api/meta-test/subscribe-webhooks', methods=['POST'])
@jwt_required()
def subscribe_webhooks():
    """Subscribe this app to the configured Page's webhooks."""
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403
    fields = (request.get_json(silent=True) or {}).get('fields')
    ok, body = subscribe_page_webhooks(fields=fields)
    log_event('info' if ok else 'error', 'meta_test.subscribe', str(body))
    return jsonify({'success': ok, 'response': body}), (200 if ok else 502)