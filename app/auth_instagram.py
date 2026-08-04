"""
app/auth_instagram.py
Instagram API with Instagram Login — connect flow + connection management.

Why this exists alongside auth_meta.py (Facebook Login):

  Facebook Login gives a PAGE token against graph.facebook.com. That token
  cannot message a customer who holds no role on the app until App Review
  grants Advanced Access, so every reply to a real customer fails with:
      (#200) App does not have Advanced Access to instagram_manage_messages
             permission and recipient user does not have role on app

  Instagram Login gives an IG USER token against graph.instagram.com, which
  can. Verified end to end: an inbound DM from a member of the public arrived,
  verified, and processed, on an app with no review and no testers.

Both surfaces stay available — Facebook Login is still what serves Messenger
and Page feed. Each connected account is one MetaConnection row, so several
run side by side and replies go out from whichever account was messaged.

Endpoints:
  GET  /api/auth/instagram/start        → OAuth URL for the frontend to open
  GET  /api/auth/instagram/callback     → Meta redirects here; upserts the row
  GET  /api/auth/instagram/connections  → list, with token health
  POST /api/auth/instagram/<id>/refresh → refresh one token now
  POST /api/auth/instagram/<id>/disconnect → deactivate (keeps history)
"""

import os
import json
import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, request, jsonify, redirect
from flask_jwt_extended import jwt_required

from app import db
from app.models import AuthUser, MetaConnection
from app.auth import current_user_id, log_audit
from app.utils.logger import log_event
from app.integrations.meta import (
    IG_LOGIN_GRAPH, IG_LOGIN_API_VERSION, refresh_ig_login_tokens,
)

auth_ig_bp = Blueprint('auth_instagram', __name__, url_prefix='/api/auth/instagram')

IG_OAUTH_AUTHORIZE = "https://www.instagram.com/oauth/authorize"
IG_OAUTH_TOKEN = "https://api.instagram.com/oauth/access_token"

# instagram_business_basic is mandatory; the other two are what the inbox needs.
IG_SCOPES = [
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
]

# Fields we subscribe each connected account to, on graph.instagram.com.
IG_SUBSCRIBED_FIELDS = "messages,comments"


def _app_creds():
    """The Instagram app id/secret — distinct from the Facebook app's pair."""
    return (os.getenv("IG_LOGIN_APP_ID") or os.getenv("IG_APP_ID"),
            os.getenv("IG_LOGIN_APP_SECRET") or os.getenv("IG_APP_SECRET"))


def _redirect_uri():
    """
    Must match a URI registered under Instagram → API setup with Instagram
    login → Business login settings, character for character.
    """
    base = (os.getenv("PUBLIC_BASE_URL") or request.url_root).rstrip("/")
    return f"{base}/api/auth/instagram/callback"


def _frontend(path="/channels", **params):
    base = (os.getenv("FRONTEND_BASE_URL") or "").rstrip("/")
    q = f"?{urlencode(params)}" if params else ""
    return f"{base}{path}{q}" if base else f"{path}{q}"


@auth_ig_bp.route('/start', methods=['GET'])
@jwt_required()
def start():
    """Return the Instagram authorize URL for the frontend to open."""
    app_id, secret = _app_creds()
    if not app_id or not secret:
        return jsonify({'error': 'IG_LOGIN_APP_ID / IG_LOGIN_APP_SECRET not configured'}), 500

    state_payload = {'u': current_user_id(), 'r': request.args.get('return_to') or '/channels'}
    state = base64.urlsafe_b64encode(json.dumps(state_payload).encode()).decode().rstrip('=')

    url = f"{IG_OAUTH_AUTHORIZE}?" + urlencode({
        'client_id': app_id,
        'redirect_uri': _redirect_uri(),
        'response_type': 'code',
        'scope': ','.join(IG_SCOPES),
        'state': state,
    })
    return jsonify({'oauth_url': url}), 200


@auth_ig_bp.route('/callback', methods=['GET'])
def callback():
    """
    Instagram redirects the BROWSER here, so this cannot require a JWT — the
    initiating user is carried in `state` instead.

    Exchanges the code for a long-lived token, subscribes the account to
    webhooks, and upserts its MetaConnection row.
    """
    err = request.args.get('error_description') or request.args.get('error')
    if err:
        log_event("warn", "auth_ig.callback.declined", str(err)[:200])
        return redirect(_frontend(connected='0', error=str(err)[:120]))

    code = (request.args.get('code') or '').split('#')[0]
    if not code:
        return redirect(_frontend(connected='0', error='No code returned'))

    app_id, secret = _app_creds()
    auth_user_id, return_to = None, '/channels'
    if request.args.get('state'):
        try:
            raw = request.args['state']
            decoded = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode())
            auth_user_id, return_to = decoded.get('u'), decoded.get('r') or '/channels'
        except Exception:
            pass

    # 1. Code → short-lived token
    try:
        r = requests.post(IG_OAUTH_TOKEN, data={
            'client_id': app_id,
            'client_secret': secret,
            'grant_type': 'authorization_code',
            'redirect_uri': _redirect_uri(),
            'code': code,
        }, timeout=20)
        body = r.json() if r.content else {}
    except requests.RequestException as e:
        log_event("error", "auth_ig.callback.exchange_failed", str(e))
        return redirect(_frontend(return_to, connected='0', error='Token exchange failed'))

    short_token = body.get('access_token')
    if not short_token:
        raw = str(body.get('error_message') or '')

        # An expired or already-used authorisation code is the single most
        # common way this fails, and it is not a fault — Instagram codes are
        # one-shot and short-lived, so a refreshed callback, a back-button, or
        # a browser prefetch burns the code before we get here. Meta's own
        # wording ("This authorization code has expired") reads like something
        # broke, which sends people looking for a bug that isn't there. Say
        # what to do instead.
        expired = 'expired' in raw.lower() or 'authorization code' in raw.lower()

        log_event(
            "warn" if expired else "error",
            "auth_ig.callback.exchange_failed",
            ("Authorisation code was already used or had expired — the user "
             "needs to start the connection again" if expired else str(body)[:300]),
            payload={"expired_code": expired, "response": str(body)[:200]},
        )
        return redirect(_frontend(
            return_to, connected='0',
            error=('That connection link had already been used — it is only valid once '
                   'and for a few minutes. Click Connect again to start fresh.'
                   if expired else (raw or 'Token exchange failed')[:120])))
    ig_user_id = str(body.get('user_id') or '')

    # What Meta actually GRANTED, which is not necessarily what we asked for.
    # The exchange response carries `permissions`; we were storing IG_SCOPES —
    # our own request — as though it were the grant, so the connection card
    # would claim messaging access even if the user had unticked it or the app
    # was not approved for it. Logged verbatim because a token that authorises
    # nothing looks identical to a healthy one until an API call fails.
    granted = body.get('permissions')
    if isinstance(granted, list):
        granted = ','.join(str(g) for g in granted)
    log_event("info", "auth_ig.callback.granted",
              f"Instagram granted: {granted or '(none reported)'} for {ig_user_id}",
              payload={'user_id': ig_user_id, 'granted': granted,
                       'requested': ','.join(IG_SCOPES),
                       'response_keys': sorted(body.keys())})

    # 2. Short-lived → long-lived (60 days)
    # If this exchange fails we keep the SHORT-LIVED token, which lasts ONE
    # HOUR. That is not a degraded mode — it is a connection that works for
    # sixty minutes and then dies with "Session has expired", and because
    # expires_at stays None the refresh job cannot help either: it renews
    # tokens *nearing expiry*, and a token with no recorded expiry never
    # qualifies. The card then reports "No expiry recorded" and a green badge.
    #
    # It failed silently before: a 400 does not raise, so the except below
    # never fired and nothing was logged. That is exactly what happened when
    # shopzetu was connected before it held a role on the app — the exchange
    # was refused, the one-hour token was stored, and everything looked fine
    # until it abruptly didn't.
    long_token, expires_at = short_token, None
    exchange_ok = False
    try:
        r2 = requests.get(f"{IG_LOGIN_GRAPH}/access_token", params={
            'grant_type': 'ig_exchange_token',
            'client_secret': secret,
            'access_token': short_token,
        }, timeout=20)
        b2 = r2.json() if r2.content else {}
        if b2.get('access_token'):
            long_token = b2['access_token']
            exchange_ok = True
            if b2.get('expires_in'):
                expires_at = datetime.utcnow() + timedelta(seconds=int(b2['expires_in']))
        else:
            log_event("error", "auth_ig.callback.long_lived_failed",
                      f"Long-lived exchange refused ({r2.status_code}) — storing the "
                      f"SHORT-LIVED token, which expires in about an hour: "
                      f"{str(b2)[:220]}",
                      payload={'status': r2.status_code, 'user_id': ig_user_id})
    except requests.RequestException as e:
        log_event("error", "auth_ig.callback.long_lived_failed",
                  f"Long-lived exchange failed, storing the short-lived token: {e}",
                  payload={'user_id': ig_user_id})

    if not exchange_ok:
        # Refuse the connection rather than store an hour-long token that will
        # look healthy and then strand the account. Reconnecting is cheap;
        # discovering this an hour later is not.
        return redirect(_frontend(
            return_to, connected='0',
            error=("Instagram issued only a short-lived token and refused to "
                   "upgrade it, so the connection would stop working within the "
                   "hour. This usually means the account does not yet hold a "
                   "role on the Meta app — add it under Roles → Instagram "
                   "Testers, accept the invite from that account, then connect "
                   "again.")))

    # 3. Who did we just connect?
    #
    # This is where ig_username comes from, and it has been failing silently:
    # the versioned URL isn't routable on graph.instagram.com, Meta answered
    # "Unsupported request", and a 400 is not a RequestException — so the except
    # below never fired, username stayed None, and the account has been showing
    # as a bare numeric id ever since. Routed through ig_login_request(), which
    # retries unversioned, and the failure is now logged instead of swallowed.
    # The token exchange above already gave us the numeric account id, so we
    # address that rather than `me`, which does not resolve on this host.
    username, account_type, ig_business_id = None, None, None
    try:
        from app.integrations.meta import verify_ig_login_token
        ident = verify_ig_login_token(long_token, ig_user_id)
        if ident['ok']:
            username = ident.get('username')
            ig_user_id = ident.get('user_id') or ig_user_id
            ig_business_id = ident.get('business_id')
        else:
            log_event("error", "auth_ig.identity_lookup_failed",
                      f"Could not read the username for {ig_user_id}: {ident.get('error')}")
    except Exception as e:
        log_event("error", "auth_ig.identity_lookup_failed", str(e))

    # 4. Subscribe THIS account to webhooks. Without it Meta delivers nothing,
    #    exactly like the Page-level subscription on the Facebook Login side.
    #    Addressed by numeric account id. This used to POST to `/me/...`, which
    #    Instagram rejects with "Unsupported request - method type: post" — so
    #    the subscription never happened and the account received nothing,
    #    despite holding a valid token.
    subscribed = False
    try:
        from app.integrations.meta import subscribe_ig_login_webhooks
        subscribed, body = subscribe_ig_login_webhooks(ig_user_id, long_token)
        log_event("info" if subscribed else "error", "auth_ig.subscribe",
                  f"{username or ig_user_id}: subscribed={subscribed} {str(body)[:150]}")
    except Exception as e:
        log_event("error", "auth_ig.subscribe_failed", str(e))

    # 5. Upsert. Match on the IG login id so re-connecting refreshes in place
    #    rather than creating duplicates.
    conn = MetaConnection.query.filter_by(ig_login_user_id=ig_user_id).first()
    if conn is None and username:
        conn = MetaConnection.query.filter_by(ig_username=username).first()

    # ONE ACTIVE ACCOUNT AT A TIME.
    #
    # The platform is deliberately limited to a single connected Instagram
    # account. Connecting a second one is refused rather than silently
    # replacing the first: a swap disconnects a live account mid-conversation,
    # and doing that as a side effect of clicking "Connect" is not something a
    # person can undo. Disconnect the current account first, then connect the
    # new one — two deliberate steps.
    #
    # Re-connecting the SAME account is always allowed; that is how an expired
    # token is refreshed.
    if conn is None:
        other = (MetaConnection.query
                 .filter(MetaConnection.is_active.is_(True))
                 .filter(MetaConnection.ig_login_user_id.isnot(None))
                 .first())
        if other is not None:
            log_event("warn", "auth_ig.callback.second_account_refused",
                      f"Refused to connect {username or ig_user_id} — "
                      f"{other.ig_username or other.ig_login_user_id} is already connected",
                      payload={"attempted": username or ig_user_id,
                               "existing": other.ig_username or other.ig_login_user_id})
            return redirect(_frontend(
                return_to, connected='0',
                error=(f"@{other.ig_username or 'another account'} is already connected. "
                       f"Disconnect it first — only one Instagram account can be "
                       f"connected at a time.")))

    if conn is None:
        conn = MetaConnection(connected_at=datetime.utcnow())
        db.session.add(conn)

    conn.ig_login_user_id = ig_user_id
    # Webhooks arrive keyed on this, not on the app-scoped id above.
    if ig_business_id:
        conn.ig_business_account_id = ig_business_id
    conn.ig_login_token = long_token
    conn.ig_login_expires_at = expires_at
    conn.ig_username = username or conn.ig_username
    # The grant, falling back to our request only if Meta reported nothing.
    conn.scopes = (granted.split(',') if granted else IG_SCOPES)
    # NOT stamped here. last_verified_at means "Instagram confirmed this token
    # works", and at this point nothing has confirmed anything — the identity
    # lookup above may well have failed. Setting it here made a connection look
    # verified purely because it had been created.
    conn.last_verified_at = None
    conn.is_active = True
    if auth_user_id and not conn.auth_user_id:
        conn.auth_user_id = auth_user_id
    db.session.commit()

    if auth_user_id:
        log_audit(auth_user_id, 'connect_instagram',
                  resource_type='meta_connection', resource_id=str(conn.id),
                  changes={'ig_username': username, 'subscribed': subscribed,
                           'account_type': account_type})

    log_event("info", "auth_ig.connected",
              f"Connected @{username} ({ig_user_id}), subscribed={subscribed}")
    return redirect(_frontend(return_to, connected='1',
                              account=username or ig_user_id,
                              subscribed='1' if subscribed else '0'))


def _connection_health(c: MetaConnection) -> dict:
    """Shape one connection for the UI, including token expiry state."""
    days_left = None
    if c.ig_login_expires_at:
        days_left = (c.ig_login_expires_at - datetime.utcnow()).days

    if c.ig_login_token:
        surface = 'instagram_login'
    elif c.page_access_token:
        surface = 'facebook_login'
    else:
        surface = 'unknown'

    # An unrecorded expiry used to fall through to 'ok', so a row we knew
    # nothing about displayed a green "Connected" badge. Instagram Login tokens
    # are issued with a 60-day life, so a null expiry does not mean "never
    # expires" — it means the exchange never recorded one, and we cannot say
    # whether this connection works. That is its own state, not a healthy one.
    #
    # Verifying (POST /<id>/verify) asks Instagram directly and stamps
    # last_verified_at, which is what moves a connection out of 'unverified'.
    verified_recently = False
    if c.last_verified_at:
        verified_recently = (datetime.utcnow() - c.last_verified_at).days <= 7

    if not c.is_active:
        status = 'disconnected'
    elif days_left is not None and days_left < 0:
        status = 'expired'
    elif days_left is not None and days_left <= 14:
        status = 'expiring'
    elif days_left is None and not verified_recently:
        status = 'unverified'
    else:
        status = 'ok'

    return {
        'id': c.id,
        'surface': surface,
        'ig_username': c.ig_username,
        'ig_login_user_id': c.ig_login_user_id,
        'ig_business_account_id': c.ig_business_account_id,
        'page_id': c.page_id,
        'page_name': c.page_name,
        'is_active': c.is_active,
        'status': status,
        'expires_at': c.ig_login_expires_at.isoformat() if c.ig_login_expires_at else None,
        'days_left': days_left,
        'connected_at': c.connected_at.isoformat() if c.connected_at else None,
        'last_verified_at': c.last_verified_at.isoformat() if c.last_verified_at else None,
        'scopes': c.scopes,
    }


@auth_ig_bp.route('/connections', methods=['GET'])
@jwt_required()
def connections():
    """Every connected account and its token health."""
    user = AuthUser.query.get(current_user_id())
    if user is None:
        return jsonify({'error': 'User not found'}), 404

    q = MetaConnection.query
    if user.role != 'admin':
        q = q.filter_by(auth_user_id=user.id)
    rows = q.order_by(MetaConnection.connected_at.desc().nullslast()).all()
    return jsonify({'connections': [_connection_health(c) for c in rows]}), 200


@auth_ig_bp.route('/<int:conn_id>/refresh', methods=['POST'])
@jwt_required()
def refresh_one(conn_id):
    """Force-refresh one connection's Instagram token."""
    user = AuthUser.query.get(current_user_id())
    if user is None or user.role != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    conn = MetaConnection.query.get(conn_id)
    if conn is None:
        return jsonify({'error': 'Not found'}), 404
    if not conn.ig_login_token:
        return jsonify({'error': 'This connection has no Instagram Login token'}), 400

    summary = refresh_ig_login_tokens(force=True)
    db.session.refresh(conn)
    return jsonify({'summary': summary, 'connection': _connection_health(conn)}), 200


@auth_ig_bp.route('/<int:conn_id>/verify', methods=['POST'])
@jwt_required()
def verify_one(conn_id):
    """
    Ask Instagram whether this connection's token still works.

    Everything else on the card is inferred from our own row. "Connected" meant
    `is_active` was true and no expiry was on file — an absence of information
    reading as good news. This is the only thing that actually checks.

    A success also backfills `ig_username`, which is why a connection can show
    as a bare numeric account id: we never had the name, only the id Instagram
    handed back at OAuth.
    """
    from app.integrations.meta import verify_ig_login_token

    user = AuthUser.query.get(current_user_id())
    if user is None or user.role != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    conn = MetaConnection.query.get(conn_id)
    if conn is None:
        return jsonify({'error': 'Not found'}), 404
    if not conn.ig_login_token:
        return jsonify({'error': 'This connection has no Instagram Login token'}), 400

    from app.integrations.meta import (
        get_ig_login_subscriptions, subscribe_ig_login_webhooks,
    )

    # The account id, not `me` — see verify_ig_login_token().
    result = verify_ig_login_token(conn.ig_login_token, conn.ig_login_user_id)

    if result['ok']:
        conn.last_verified_at = datetime.utcnow()
        if result.get('username'):
            conn.ig_username = result['username']
        if result.get('user_id') and not conn.ig_login_user_id:
            conn.ig_login_user_id = result['user_id']
        # The business account id is what webhooks report as the recipient, so
        # without it _connection_for() can never match a delivery to this row.
        # Backfilled here for connections made before it was captured.
        if result.get('business_id'):
            conn.ig_business_account_id = result['business_id']
        db.session.commit()

        # A valid token is only half of "connected". Without a webhook
        # subscription Meta delivers nothing, and the two states look identical
        # from here — which is exactly what happened: the OAuth callback's
        # subscribe call was failing, so accounts finished connecting with a
        # good token and no subscription, and simply never received anything.
        acct = conn.ig_login_user_id
        sub_ok, sub_body = get_ig_login_subscriptions(acct, conn.ig_login_token)
        subscribed = bool(sub_ok and (sub_body.get('data') or []))

        repaired = False
        if not subscribed:
            # Fix it here rather than making someone disconnect and reconnect.
            repaired, _ = subscribe_ig_login_webhooks(acct, conn.ig_login_token)
            subscribed = repaired

        result['webhooks_subscribed'] = subscribed
        result['webhooks_repaired'] = repaired

        log_event("info", "auth_ig.verify_ok",
                  f"Token verified for @{conn.ig_username or acct}; "
                  f"webhooks_subscribed={subscribed} repaired={repaired}",
                  payload={'connection_id': conn.id,
                           'webhooks_subscribed': subscribed,
                           'webhooks_repaired': repaired})
    else:
        # Deliberately NOT deactivating the row. A network blip is not proof the
        # connection is dead, and silently flipping is_active would stop
        # messaging on a transient error. The card reports the failure instead.
        log_event("warning", "auth_ig.verify_failed",
                  f"Token verification failed for connection {conn.id}: {result['error']}",
                  payload={'connection_id': conn.id})

    return jsonify({'result': result, 'connection': _connection_health(conn)}), 200


@auth_ig_bp.route('/<int:conn_id>/disconnect', methods=['POST'])
@jwt_required()
def disconnect(conn_id):
    """
    Deactivate a connection. Deliberately NOT a delete — conversations still
    reference the account, and history should survive retiring an account.
    """
    user = AuthUser.query.get(current_user_id())
    if user is None or user.role != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    conn = MetaConnection.query.get(conn_id)
    if conn is None:
        return jsonify({'error': 'Not found'}), 404

    conn.is_active = False
    db.session.commit()
    log_audit(user.id, 'disconnect_instagram',
              resource_type='meta_connection', resource_id=str(conn.id),
              changes={'ig_username': conn.ig_username})
    return jsonify({'success': True, 'connection': _connection_health(conn)}), 200
