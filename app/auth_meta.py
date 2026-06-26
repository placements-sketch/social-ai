"""
app/auth_meta.py
Facebook Login for Business OAuth flow — implements the spec from:
https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/business-login-for-instagram/

Flow:
  1. Frontend calls GET /api/auth/facebook/start
     → Backend returns the Facebook OAuth URL
  2. Frontend redirects user to that URL (or opens popup)
  3. User approves permissions on Facebook
  4. Facebook redirects to /api/auth/facebook/callback?#access_token=...&long_lived_token=...
     (note: token is in URL FRAGMENT, not query string — so we need a small JS helper)
  5. Backend receives the token via a POST from that JS helper page
  6. Backend calls GET /me/accounts to discover the user's Pages and IG accounts
  7. Backend persists a MetaConnection row per Page

Endpoints:
  GET  /api/auth/facebook/start          → returns OAuth URL for frontend to redirect to
  GET  /api/auth/facebook/callback       → HTML page that captures the fragment and POSTs to /finish
  POST /api/auth/facebook/finish         → receives token, fetches Pages, stores connections
  POST /api/auth/facebook/data-deletion  → Meta-mandated data deletion request callback
  POST /api/auth/facebook/deauthorize    → fired when a user revokes access
  GET  /api/auth/facebook/connections    → list connections owned by the current user
"""

import os
import hmac
import hashlib
import json
import base64
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
from flask import Blueprint, request, jsonify, redirect, current_app, Response
from flask_jwt_extended import jwt_required

from app import db
from app.models import AuthUser, MetaConnection
from app.auth import current_user_id, log_audit
from app.utils.logger import log_event

auth_meta_bp = Blueprint('auth_meta', __name__, url_prefix='/api/auth/facebook')

# Scopes we request during OAuth. Keep tight — only what's actually used.
# Each one will need a corresponding "use case" in App Review.
META_SCOPES = [
    'instagram_basic',
    'instagram_manage_messages',
    'instagram_manage_comments',
    'pages_show_list',
    'pages_read_engagement',
    'pages_messaging',
    'business_management',
]


def _redirect_uri():
    """Build the absolute callback URL from request context."""
    # Prefer explicit env var (correct in production behind proxy), fall back to request.url_root
    base = os.getenv('PUBLIC_BASE_URL') or request.url_root.rstrip('/')
    return f"{base}/api/auth/facebook/callback"


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Frontend asks "where do I send the user?"
# ─────────────────────────────────────────────────────────────────────────────

@auth_meta_bp.route('/start', methods=['GET'])
@jwt_required()
def oauth_start():
    """
    Returns a Facebook Login for Business URL that the frontend will navigate to.
    Optionally accepts a `return_to` query param — we'll redirect the user back
    to that page in our frontend after the OAuth flow completes.
    """
    app_id = os.getenv('META_APP_ID')
    if not app_id:
        return jsonify({'error': 'META_APP_ID not configured'}), 500

    # Include the auth user ID in state so we know who connected this when the
    # callback fires. The state param is echoed back by Facebook.
    auth_user_id = current_user_id()
    return_to = request.args.get('return_to') or '/channels'
    state_payload = {'u': auth_user_id, 'r': return_to}
    state = base64.urlsafe_b64encode(json.dumps(state_payload).encode()).decode().rstrip('=')

    params = {
        'client_id': app_id,
        'display': 'page',
        'extras': json.dumps({'setup': {'channel': 'IG_API_ONBOARDING'}}),
        'redirect_uri': _redirect_uri(),
        'response_type': 'token',
        'scope': ','.join(META_SCOPES),
        'state': state,
    }

    oauth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"
    log_event("info", "auth_meta.start", f"OAuth URL generated for user {auth_user_id}")
    return jsonify({'oauth_url': oauth_url}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Facebook redirects back here with token in URL fragment (#)
# Fragments are not sent to the server, so we serve an HTML page that runs JS
# to capture the fragment and POST it to /finish.
# ─────────────────────────────────────────────────────────────────────────────

@auth_meta_bp.route('/callback', methods=['GET'])
def oauth_callback():
    """
    Fragment-capture page. Facebook puts the access token in the URL fragment
    (after #), which the browser never sends to the server. So we return a
    tiny HTML page that reads the fragment client-side and POSTs it to /finish.
    """
    error = request.args.get('error')
    error_description = request.args.get('error_description', '')
    if error:
        log_event("warn", "auth_meta.callback.error", f"{error}: {error_description}")
        # User cancelled or something went wrong — show a simple error page
        html = f"""<!doctype html><html><body style="font-family:sans-serif;padding:40px;text-align:center">
<h2>Connection cancelled</h2>
<p>{error_description or 'You declined permission or the flow was interrupted.'}</p>
<p><a href="/">Return to app</a></p>
</body></html>"""
        return Response(html, mimetype='text/html')

    # Happy path: the fragment contains access_token + long_lived_token + state
    # We serve a page that reads them and POSTs to /finish
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Connecting...</title>
  <style>
    body { font-family: -apple-system, sans-serif; padding: 40px; text-align: center; background: #fafafa; }
    .spinner { border: 3px solid #eee; border-top: 3px solid #ff5900; border-radius: 50%; width: 32px; height: 32px; animation: spin 1s linear infinite; margin: 20px auto; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .err { color: #b00; margin-top: 16px; font-size: 14px; }
  </style>
</head>
<body>
  <h2>Finalizing connection...</h2>
  <div class="spinner"></div>
  <p id="status">Just a moment.</p>
  <p id="err" class="err"></p>
  <script>
    (async function() {
      const frag = window.location.hash.substring(1);
      const params = new URLSearchParams(frag);
      const access_token   = params.get('access_token');
      const long_lived     = params.get('long_lived_token');
      const expires_in     = params.get('expires_in');
      const data_access_exp = params.get('data_access_expiration_time');
      const state          = new URLSearchParams(window.location.search).get('state');

      if (!access_token && !long_lived) {
        document.getElementById('err').textContent = 'No token in callback — check redirect URI matches exactly.';
        return;
      }

      try {
        const res = await fetch('/api/auth/facebook/finish', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            access_token, long_lived_token: long_lived,
            expires_in, data_access_expiration_time: data_access_exp,
            state,
          })
        });
        const data = await res.json();
        if (!res.ok) {
          document.getElementById('err').textContent = data.error || 'Connection failed.';
          return;
        }
        // Redirect to the return_to URL in the state payload, or default to /channels
        const returnTo = data.return_to || '/channels';
        window.location.href = returnTo + '?connected=1';
      } catch (e) {
        document.getElementById('err').textContent = 'Network error: ' + e.message;
      }
    })();
  </script>
</body>
</html>"""
    return Response(html, mimetype='text/html')


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Receive the token, fetch Pages, store MetaConnection rows
# ─────────────────────────────────────────────────────────────────────────────

@auth_meta_bp.route('/finish', methods=['POST'])
def oauth_finish():
    """
    Called by the callback page's JS with the captured token.
    Looks up the user's Pages, picks the IG-connected ones, persists MetaConnection rows.
    """
    payload = request.get_json(silent=True) or {}
    user_token = payload.get('long_lived_token') or payload.get('access_token')
    expires_in = payload.get('expires_in')
    state_b64 = payload.get('state')

    if not user_token:
        return jsonify({'error': 'No access_token provided'}), 400

    # Decode state to find which auth user initiated this
    auth_user_id = None
    return_to = '/channels'
    if state_b64:
        try:
            # Re-pad base64
            padded = state_b64 + '=' * (-len(state_b64) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
            auth_user_id = decoded.get('u')
            return_to = decoded.get('r') or '/channels'
        except Exception:
            log_event("warn", "auth_meta.finish.bad_state", state_b64)

    # Compute token expiry
    token_expires_at = None
    if expires_in:
        try:
            token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        except ValueError:
            pass

    # Fetch the user's Pages + IG accounts
    try:
        resp = requests.get(
            'https://graph.facebook.com/v21.0/me/accounts',
            params={
                'fields': 'id,name,access_token,instagram_business_account{id,username}',
                'access_token': user_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        pages_data = resp.json().get('data', [])
    except requests.RequestException as e:
        log_event("error", "auth_meta.finish.pages_fetch_failed", str(e))
        return jsonify({'error': f'Failed to fetch Pages: {str(e)}'}), 502

    if not pages_data:
        return jsonify({'error': 'No Pages found on this Facebook account. Connect an Instagram Business Account to a Facebook Page first.'}), 400

    # Upsert each Page that has an IG Business Account connected
    now = datetime.utcnow()
    connections_made = []

    for page in pages_data:
        page_id = page.get('id')
        page_name = page.get('name')
        page_token = page.get('access_token')
        ig_block = page.get('instagram_business_account') or {}
        ig_id = ig_block.get('id')
        ig_username = ig_block.get('username')

        if not page_id or not page_token:
            continue

        existing = MetaConnection.query.filter_by(page_id=page_id).first()
        if existing:
            existing.page_name = page_name
            existing.page_access_token = page_token
            existing.ig_business_account_id = ig_id
            existing.ig_username = ig_username
            existing.user_access_token = user_token
            existing.token_expires_at = token_expires_at
            existing.scopes = META_SCOPES
            existing.last_verified_at = now
            existing.is_active = True
            if auth_user_id and not existing.auth_user_id:
                existing.auth_user_id = auth_user_id
        else:
            db.session.add(MetaConnection(
                auth_user_id=auth_user_id,
                page_id=page_id,
                page_name=page_name,
                page_access_token=page_token,
                ig_business_account_id=ig_id,
                ig_username=ig_username,
                user_access_token=user_token,
                token_expires_at=token_expires_at,
                scopes=META_SCOPES,
                connected_at=now,
                last_verified_at=now,
                is_active=True,
            ))

        connections_made.append({
            'page_id': page_id,
            'page_name': page_name,
            'ig_username': ig_username,
        })

    db.session.commit()

    if auth_user_id:
        log_audit(
            auth_user_id, 'connect_meta',
            resource_type='meta_connection', resource_id=None,
            changes={'pages_connected': len(connections_made), 'pages': connections_made},
        )

    log_event("info", "auth_meta.finish.success", f"Connected {len(connections_made)} Page(s)")
    # Build absolute return URL using the configured frontend origin.
    frontend_base = os.getenv('FRONTEND_BASE_URL', '').rstrip('/')
    absolute_return = return_to
    if frontend_base and return_to.startswith('/'):
        absolute_return = f"{frontend_base}{return_to}"

    return jsonify({
        'success': True,
        'connections': connections_made,
        'return_to': absolute_return,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: List existing connections (for the Channels page UI)
# ─────────────────────────────────────────────────────────────────────────────

@auth_meta_bp.route('/connections', methods=['GET'])
@jwt_required()
def list_connections():
    """List MetaConnection rows. Admins see all; others see their own."""
    user = AuthUser.query.get(current_user_id())
    if user is None:
        return jsonify({'error': 'User not found'}), 404

    query = MetaConnection.query.filter_by(is_active=True)
    if user.role != 'admin':
        query = query.filter_by(auth_user_id=user.id)

    rows = query.order_by(MetaConnection.connected_at.desc()).all()
    return jsonify({'connections': [r.to_dict() for r in rows]}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Meta-mandated callbacks
# ─────────────────────────────────────────────────────────────────────────────

def _verify_signed_request(signed_request):
    """
    Decode and verify a Facebook signed_request payload.
    Returns the decoded JSON dict, or None if invalid.
    """
    try:
        sig_b64, payload_b64 = signed_request.split('.', 1)

        # Re-pad base64
        def b64decode(s):
            return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))

        expected_sig = hmac.new(
            os.getenv('META_APP_SECRET', '').encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).digest()
        actual_sig = b64decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        return json.loads(b64decode(payload_b64).decode())
    except Exception as e:
        log_event("warn", "auth_meta.signed_request.decode_failed", str(e))
        return None


@auth_meta_bp.route('/deauthorize', methods=['POST'])
def deauthorize():
    """
    Fired by Facebook when a user removes our app from their account.
    We mark their MetaConnection rows as inactive.
    """
    signed_request = request.form.get('signed_request')
    if not signed_request:
        return jsonify({'error': 'Missing signed_request'}), 400

    payload = _verify_signed_request(signed_request)
    if not payload:
        return jsonify({'error': 'Invalid signature'}), 401

    fb_user_id = payload.get('user_id')
    if not fb_user_id:
        return jsonify({'error': 'No user_id in payload'}), 400

    # Mark all that user's connections inactive
    # NOTE: this matches on the Facebook user; future improvement is to store fb_user_id
    # on MetaConnection. For now we'll log and let admins clean up.
    log_event("info", "auth_meta.deauthorize", f"User {fb_user_id} deauthorized the app")
    return jsonify({'success': True}), 200


@auth_meta_bp.route('/data-deletion', methods=['POST'])
def data_deletion():
    """
    Fired by Facebook when a user requests their data be deleted from our app.
    We must delete their data and return a confirmation URL.
    """
    signed_request = request.form.get('signed_request')
    if not signed_request:
        return jsonify({'error': 'Missing signed_request'}), 400

    payload = _verify_signed_request(signed_request)
    if not payload:
        return jsonify({'error': 'Invalid signature'}), 401

    fb_user_id = payload.get('user_id')
    log_event("info", "auth_meta.data_deletion", f"Data deletion requested for FB user {fb_user_id}")

    # For now, log and respond. Real deletion happens manually until we
    # store fb_user_id on conversations/messages.
    confirmation_code = f"del_{fb_user_id}_{int(datetime.utcnow().timestamp())}"
    status_url = f"{os.getenv('PUBLIC_BASE_URL') or request.url_root.rstrip('/')}/api/auth/facebook/data-deletion/status/{confirmation_code}"

    return jsonify({
        'url': status_url,
        'confirmation_code': confirmation_code,
    }), 200


@auth_meta_bp.route('/data-deletion/status/<code>', methods=['GET'])
def data_deletion_status(code):
    """Public-facing status page for users to see their deletion is in progress."""
    html = f"""<!doctype html><html><body style="font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto">
<h2>Data Deletion Request Received</h2>
<p>Reference code: <code>{code}</code></p>
<p>We've received your data deletion request. Any data we hold about your Instagram or Facebook account
linked to our app will be removed within 30 days.</p>
<p>For questions, email <a href="mailto:[email protected]">[email protected]</a>.</p>
</body></html>"""
    return Response(html, mimetype='text/html')