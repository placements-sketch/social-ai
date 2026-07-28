"""
app/meta_test.py
Admin-only diagnostic endpoints that proxy raw Meta Graph API calls, so the
Meta Diagnostics panel can test connectivity without the Page token ever
touching the browser. The token is read server-side via _get_meta_credentials.
"""

import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from app.integrations.meta import _get_meta_credentials, GRAPH_API_VERSION
from app.utils.logger import log_event

meta_test_bp = Blueprint('meta_test', __name__)

GRAPH = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
IG_USER_ID = "17841412308701394"   # @shopzetu IG business account
PAGE_ID    = "115573226545299"     # Shop Zetu Page


def _require_admin():
    return (get_jwt() or {}).get('role') == 'admin'


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
    body, status = _proxy(f"{GRAPH}/{PAGE_ID}/subscribed_apps", {})
    return jsonify(body), status