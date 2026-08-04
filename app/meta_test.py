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


@meta_test_bp.route('/api/meta-test/ig-login-probe', methods=['GET'])
@jwt_required()
def ig_login_probe():
    """
    Find the URL shape graph.instagram.com actually accepts for this token.

    Two fixes have now been shipped against "Unsupported request - method
    type: get" on guesses about what the API wants — first the version prefix,
    then addressing the numeric account id instead of `me`. Both were reasoning
    from indirect evidence and both were wrong. This stops guessing: it tries
    every plausible shape against the real stored token and reports exactly
    what Meta says to each, so the fix is chosen from data.

    Read-only — every probe is a GET, nothing is written and nothing is sent.
    """
    if not _require_admin():
        return jsonify({'error': 'Admin only'}), 403

    from app.models import MetaConnection
    from app.integrations.meta import IG_LOGIN_GRAPH, IG_LOGIN_API_VERSION

    conn = (MetaConnection.query
            .filter(MetaConnection.ig_login_token.isnot(None))
            .order_by(MetaConnection.is_active.desc(), MetaConnection.id.desc())
            .first())
    if conn is None:
        return jsonify({'error': 'No connection with an Instagram Login token'}), 404

    token = conn.ig_login_token
    acct = conn.ig_login_user_id or ''
    V = IG_LOGIN_API_VERSION

    # node, fields — `fields` matters: Instagram Login documents `user_id`,
    # while the Graph convention is `id`. A wrong field name and a wrong node
    # can produce similarly unhelpful errors, so both axes are varied.
    variants = [
        ('bare /me, no fields',            f'{IG_LOGIN_GRAPH}/me', {}),
        ('/me fields=id,username',         f'{IG_LOGIN_GRAPH}/me', {'fields': 'id,username'}),
        ('/me fields=user_id,username',    f'{IG_LOGIN_GRAPH}/me', {'fields': 'user_id,username'}),
        (f'/{V}/me fields=user_id,username', f'{IG_LOGIN_GRAPH}/{V}/me', {'fields': 'user_id,username'}),
        (f'/{V}/me fields=id,username',    f'{IG_LOGIN_GRAPH}/{V}/me', {'fields': 'id,username'}),
    ]
    if acct:
        variants += [
            ('bare /<id>, no fields',        f'{IG_LOGIN_GRAPH}/{acct}', {}),
            ('/<id> fields=id,username',     f'{IG_LOGIN_GRAPH}/{acct}', {'fields': 'id,username'}),
            ('/<id> fields=user_id,username', f'{IG_LOGIN_GRAPH}/{acct}', {'fields': 'user_id,username'}),
            (f'/{V}/<id> fields=username',   f'{IG_LOGIN_GRAPH}/{V}/{acct}', {'fields': 'username'}),
        ]
    # If the stored token is actually a Facebook token, graph.instagram.com can
    # never route it and this row is the one that will succeed.
    variants.append(('graph.facebook.com /me',
                     f'https://graph.facebook.com/{V}/me', {'fields': 'id,name'}))

    results = []
    for label, url, params in variants:
        try:
            r = requests.get(url, params={**params, 'access_token': token}, timeout=10)
            try:
                body = r.json()
            except ValueError:
                body = {'raw': (r.text or '')[:200]}
            err = (body.get('error') or {})
            results.append({
                'variant': label,
                'url': url,
                'status': r.status_code,
                'ok': r.ok,
                'error': err.get('message'),
                'code': err.get('code'),
                'type': err.get('type'),
                'data': {k: v for k, v in body.items() if k != 'error'} if r.ok else None,
            })
        except requests.RequestException as e:
            results.append({'variant': label, 'url': url, 'status': 0,
                            'ok': False, 'error': str(e)[:160]})

    # ── Who does Meta think we can talk to? ──────────────────────────────
    # Sends and username lookups both fail with the same 500 / code 1, and both
    # are keyed on the CUSTOMER's IGSID while every call about our own account
    # succeeds. So the question is whether the recipient id taken from the
    # webhook is one this token is actually allowed to address. Listing the
    # conversations Meta will admit to is read-only and answers that directly:
    # if a thread appears here, compare its participant id with the recipient
    # we are posting to; if NO threads appear at all, the token cannot see
    # messaging for this account, which is a permission/mode answer rather than
    # an id-mismatch one.
    convos = {'checked': [], 'threads': []}
    for label, path in (('conversations', f'{IG_LOGIN_GRAPH}/{V}/me/conversations'),
                        ('conversations (unversioned)', f'{IG_LOGIN_GRAPH}/me/conversations')):
        try:
            rc = requests.get(path, params={
                'fields': 'participants,updated_time',
                'access_token': token,
            }, timeout=10)
            cb = rc.json() if rc.text else {}
            entry = {'variant': label, 'url': path, 'status': rc.status_code,
                     'ok': rc.ok, 'error': (cb.get('error') or {}).get('message'),
                     'code': (cb.get('error') or {}).get('code')}
            convos['checked'].append(entry)
            if rc.ok:
                for th in (cb.get('data') or [])[:10]:
                    parts = ((th.get('participants') or {}).get('data') or [])
                    convos['threads'].append({
                        'thread_id': th.get('id'),
                        'updated': th.get('updated_time'),
                        'participants': [{'id': p.get('id'),
                                          'username': p.get('username')} for p in parts],
                    })
                break
        except requests.RequestException as e:
            convos['checked'].append({'variant': label, 'url': path,
                                      'ok': False, 'error': str(e)[:160]})

    # The recipient ids we would actually post to, straight from our own rows,
    # so they can be eyeballed against the participants above.
    from app import db
    from app.models import Conversation as _Conv, User as _U
    recent = []
    try:
        rows = (db.session.query(_Conv.id, _U.external_id, _U.name, _Conv.channel)
                .join(_U, _U.id == _Conv.user_id)
                .filter(_Conv.channel.like('instagram%'))
                .order_by(_Conv.id.desc()).limit(5).all())
        recent = [{'conversation_id': c, 'recipient_id': e,
                   'stored_username': n, 'channel': ch} for c, e, n, ch in rows]
    except Exception as e:
        recent = [{'error': str(e)[:160]}]

    working = [r for r in results if r['ok']]
    log_event('info' if working else 'error', 'meta_test.ig_login_probe',
              f"{len(working)}/{len(results)} URL shapes accepted for "
              f"connection {conn.id}",
              payload={'working': [r['variant'] for r in working]})

    return jsonify({
        'connection_id': conn.id,
        'is_active': conn.is_active,
        'ig_login_user_id': acct or None,
        'ig_username': conn.ig_username,
        'token_len': len(token or ''),
        'token_prefix': (token or '')[:4],
        'api_version_tried': V,
        'working': [r['variant'] for r in working],
        'results': results,
        # Compare `conversations.threads[].participants[].id` against
        # `recent_recipients[].recipient_id`. A mismatch means we are posting to
        # an id from a different scope; an empty thread list with an error means
        # this token cannot see messaging at all.
        'conversations': convos,
        'recent_recipients': recent,
    }), 200


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