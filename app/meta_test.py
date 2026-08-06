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


def _username_error(igsid: str) -> str:
    """
    The raw reason a username lookup failed, for the backfill's report.

    Deliberately a second call rather than plumbing errors through
    fetch_instagram_username: that function is on the hot inbound path where a
    failed lookup must stay cheap and silent, and only this diagnostic wants the
    detail. It runs at most once per unresolved user, on demand.
    """
    from app.integrations.meta import _ig_login_credentials, ig_login_request
    _id, token = _ig_login_credentials()
    if not token:
        return 'No active Instagram connection'
    try:
        r, body = ig_login_request('GET', str(igsid),
                                   params={'fields': 'username', 'access_token': token},
                                   timeout=10)
    except Exception as e:
        return f'Request failed: {str(e)[:120]}'
    if r.ok:
        return 'Returned no username field'
    err = (body.get('error') or {})
    return (f"{err.get('message') or 'HTTP %s' % r.status_code}"
            f"{' (code %s)' % err['code'] if err.get('code') else ''}")[:200]


@meta_test_bp.route('/api/meta-test/backfill-usernames', methods=['POST'])
@jwt_required()
def backfill_usernames():
    """
    Resolve Instagram handles for customers still showing as a bare numeric id.

    Every agent sees these on every shift — "2532642840503747" instead of a
    person — and each one is a Graph call we simply never made or that failed
    once and was never retried.

    DRY RUN BY DEFAULT. POST {"apply": true} to write. A job that reaches an
    external API and rewrites customer records should make you say so twice.

    Bounded by `limit` (default 50) because this is one Graph call per user and
    Meta rate-limits: 3,000 users in a single request would be throttled
    part-way through, leaving nobody able to say which half was done.
    """
    if not _require_admin():
        return jsonify({'error': 'Admin access required'}), 403

    from app import db
    from app.models import User
    from app.integrations.meta import fetch_instagram_username
    from sqlalchemy import or_

    body = request.get_json(silent=True) or {}
    apply_changes = bool(body.get('apply'))
    limit = min(max(int(body.get('limit') or 50), 1), 500)

    # Only real IGSIDs. Test rows and seeded handles are not resolvable and
    # would burn the whole rate-limit budget failing.
    candidates = (User.query
                  .filter(User.channel.like('instagram%'))
                  .filter(or_(User.name.is_(None), User.name == ''))
                  .filter(User.external_id.op('~')(r'^[0-9]{15,}$'))
                  .limit(limit)
                  .all())

    resolved, failed = [], []
    for u in candidates:
        profile = fetch_instagram_username(u.external_id)
        username = (profile or {}).get('username') or (profile or {}).get('name')
        if username:
            resolved.append({'external_id': u.external_id, 'username': username})
            if apply_changes:
                u.name = username
        else:
            # Report WHAT Instagram said, not just that it said no.
            #
            # The first version of this listed unresolved ids and nothing else,
            # which is the exact failure this whole audit keeps finding: a
            # diagnostic that can only say "it didn't work". "Object does not
            # exist" and "missing permission" and "token expired" need three
            # completely different responses, and the id alone distinguishes
            # none of them.
            failed.append({'external_id': u.external_id,
                           'error': _username_error(u.external_id)})

    if apply_changes and resolved:
        db.session.commit()

    log_event('info', 'meta_test.backfill_usernames',
              f"{'Applied' if apply_changes else 'Dry run'}: "
              f"{len(resolved)} resolved, {len(failed)} unresolved")

    return jsonify({
        'applied': apply_changes,
        'checked': len(candidates),
        'resolved_count': len(resolved),
        'unresolved_count': len(failed),
        'resolved': resolved[:100],
        'unresolved': failed[:100],
        'hint': ('Dry run — nothing was saved. POST {"apply": true} to write.'
                 if not apply_changes else 'Names saved.'),
    }), 200


@meta_test_bp.route('/api/meta-test/media-audit', methods=['GET'])
@jwt_required()
def media_audit():
    """
    Test the "post no longer loads" theory: are the failures ONLY on comments
    that arrived before the current Instagram connection?

    Media ids are scoped to the account and app that issued them, exactly like
    IGSIDs — so a comment received under the old Facebook-Login connection has
    an id the current Instagram-Login token can never resolve. If that is what
    is happening, every failure will predate the connection and every success
    will follow it, and the fix is an honest message rather than a retry.

    If failures appear on BOTH sides of that date, the theory is wrong and
    something else is broken. Reported either way — the point is to settle it
    with data rather than a third guess.
    """
    if not _require_admin():
        return jsonify({'error': 'Admin access required'}), 403

    from app.models import Message, MetaConnection
    from app.integrations.meta import fetch_instagram_media

    limit = min(max(request.args.get('limit', default=15, type=int), 1), 60)

    conn = (MetaConnection.query
            .filter_by(is_active=True)
            .order_by(MetaConnection.connected_at.desc())
            .first())
    connected_at = getattr(conn, 'connected_at', None)

    rows = (Message.query
            .filter(Message.media_id.isnot(None))
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all())

    seen, results = set(), []
    for m in rows:
        if m.media_id in seen:
            continue
        seen.add(m.media_id)
        data, error = fetch_instagram_media(m.media_id)
        before_connection = (
            bool(connected_at and m.created_at and m.created_at < connected_at)
        )
        # WHICH FIELDS came back, not just whether the call succeeded.
        #
        # "ok" was hiding the actual problem: a response can arrive with a
        # permalink and nothing else, which passes every success check while
        # leaving the card blank AND the AI with no idea what the post is —
        # producing "which product are you asking about?" on a comment sitting
        # directly under the product. A request that succeeds and returns
        # nothing useful is the failure mode worth naming.
        d = data or {}
        results.append({
            'media_id': m.media_id,
            'message_at': m.created_at.isoformat() if m.created_at else None,
            'predates_connection': before_connection,
            'ok': bool(data),
            'error': error,
            'media_type': d.get('media_type'),
            'has_caption': bool(d.get('caption')),
            'has_media_url': bool(d.get('media_url')),
            'has_thumbnail': bool(d.get('thumbnail_url')),
            'has_permalink': bool(d.get('permalink')),
            'fields_returned': sorted(k for k, v in d.items() if v),
        })

    older = [r for r in results if r['predates_connection']]
    newer = [r for r in results if not r['predates_connection']]

    def _fail_rate(group):
        return f"{sum(1 for r in group if not r['ok'])}/{len(group)}" if group else 'none tested'

    older_all_fail = bool(older) and all(not r['ok'] for r in older)
    newer_all_ok = bool(newer) and all(r['ok'] for r in newer)

    empty_ok = [r for r in results
                if r['ok'] and not (r['has_caption'] or r['has_media_url']
                                    or r['has_thumbnail'])]
    if empty_ok:
        return jsonify({
            'connection_connected_at': connected_at.isoformat() if connected_at else None,
            'ig_username': getattr(conn, 'ig_username', None),
            'tested': len(results),
            'verdict': (f'{len(empty_ok)} of {len(results)} posts returned SUCCESSFULLY but '
                        'with no caption, image or thumbnail — only a permalink. That is why '
                        'the card is blank and the AI has no idea what the post shows. This is '
                        'a FIELD problem, not an access problem: check fields_returned below.'),
            'results': results,
        }), 200

    if older_all_fail and newer_all_ok:
        verdict = ('CONFIRMED — every failure predates the current connection and '
                   'everything after it works. These ids belong to the previous '
                   'account and can never be resolved. Show an honest message '
                   'instead of retrying.')
    elif not older and not newer:
        verdict = 'No comment media found to test.'
    elif newer and not newer_all_ok:
        verdict = ('THEORY WRONG — posts from AFTER the current connection are '
                   'failing too, so this is not about old ids. Send me the '
                   'errors below.')
    else:
        verdict = ('INCONCLUSIVE — not a clean split. See the per-item results.')

    return jsonify({
        'connection_connected_at': connected_at.isoformat() if connected_at else None,
        'ig_username': getattr(conn, 'ig_username', None),
        'tested': len(results),
        'failures_before_connection': _fail_rate(older),
        'failures_after_connection': _fail_rate(newer),
        'verdict': verdict,
        'results': results,
    }), 200
