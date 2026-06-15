"""
app/logs.py
Logs endpoints — role-aware access to audit_logs and pipeline logs.

Endpoints (all JWT-protected, /api prefix):
  GET  /api/logs/me      my own audit_logs   (any authenticated user)
  GET  /api/logs/audit   all audit_logs      (supervisor + admin)
  GET  /api/logs/system  pipeline logs       (admin only)

Common filters (all endpoints):
  ?page=1&per_page=50          pagination (max 200)
  ?from=ISO&to=ISO             date range (inclusive)
  ?days=N                      shortcut: last N days (overrides from/to if both given)
  ?search=text                 case-insensitive match on log content

/logs/audit additionally accepts:
  ?user_id=N                   drill into one agent's actions
  ?action=create_user,login    CSV of audit actions to include

/logs/system additionally accepts:
  ?level=info,error            CSV of levels to include
  ?source=services,handoff     CSV of sources to include
  ?conversation_id=N           only events on this conversation
"""

from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app import db
from app.models import AuthUser, AuditLog, Log
from app.auth import current_user_id

logs_bp = Blueprint('logs', __name__, url_prefix='/api')


DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def _require_user():
    user = AuthUser.query.get(current_user_id())
    if not user:
        return None, (jsonify({'error': 'User not found'}), 404)
    return user, None


def _require_role(allowed_roles):
    """Returns (user, None) on success or (None, error_response) on failure."""
    user, err = _require_user()
    if err:
        return None, err
    if user.role not in allowed_roles:
        return None, (jsonify({'error': 'Forbidden'}), 403)
    return user, None


def _paginate_params():
    page = max(1, request.args.get('page', default=1, type=int))
    per_page = request.args.get('per_page', default=DEFAULT_PER_PAGE, type=int)
    if per_page < 1:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE
    return page, per_page


def _parse_iso(s):
    """Parse an ISO date or datetime; return None if invalid/missing."""
    if not s:
        return None
    try:
        # Accepts 'YYYY-MM-DD' or full ISO datetime
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def _date_window():
    """
    Resolve the active date window.
      - ?days=N  -> last N days (overrides from/to)
      - ?from=ISO ?to=ISO  -> explicit range
      - otherwise None (no date filter)
    Returns (from_dt, to_dt) where either or both may be None.
    """
    days = request.args.get('days', type=int)
    if days and days > 0:
        return datetime.utcnow() - timedelta(days=days), None

    return _parse_iso(request.args.get('from')), _parse_iso(request.args.get('to'))


def _csv_list(arg_value):
    """'a,b ,c' -> ['a', 'b', 'c']  (or [] if empty/None)"""
    if not arg_value:
        return []
    return [s.strip() for s in arg_value.split(',') if s.strip()]


# ─────────────────────────────────────────────
# GET /api/logs/me  — any authenticated user's own audit_logs
# ─────────────────────────────────────────────

@logs_bp.route('/logs/me', methods=['GET'])
@jwt_required()
def my_logs():
    user, err = _require_user()
    if err:
        return err

    page, per_page = _paginate_params()
    dt_from, dt_to = _date_window()
    search = request.args.get('search', type=str)

    query = AuditLog.query.filter_by(user_id=user.id)

    if dt_from:
        query = query.filter(AuditLog.created_at >= dt_from)
    if dt_to:
        query = query.filter(AuditLog.created_at <= dt_to)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(db.or_(
            AuditLog.action.ilike(like),
            AuditLog.resource_type.ilike(like),
            AuditLog.resource_id.ilike(like),
        ))

    total = query.count()
    rows = (query.order_by(AuditLog.created_at.desc())
                 .limit(per_page).offset((page - 1) * per_page).all())

    return jsonify({
        'logs': [r.to_dict() for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
    }), 200


# ─────────────────────────────────────────────
# GET /api/logs/audit  — supervisor + admin
# ─────────────────────────────────────────────

@logs_bp.route('/logs/audit', methods=['GET'])
@jwt_required()
def audit_logs():
    user, err = _require_role({'admin', 'supervisor'})
    if err:
        return err

    page, per_page = _paginate_params()
    dt_from, dt_to = _date_window()
    search = request.args.get('search', type=str)
    user_id_filter = request.args.get('user_id', type=int)
    actions = _csv_list(request.args.get('action'))

    query = AuditLog.query

    if user_id_filter:
        query = query.filter(AuditLog.user_id == user_id_filter)
    if actions:
        query = query.filter(AuditLog.action.in_(actions))
    if dt_from:
        query = query.filter(AuditLog.created_at >= dt_from)
    if dt_to:
        query = query.filter(AuditLog.created_at <= dt_to)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(db.or_(
            AuditLog.action.ilike(like),
            AuditLog.resource_type.ilike(like),
            AuditLog.resource_id.ilike(like),
        ))

    total = query.count()
    rows = (query.order_by(AuditLog.created_at.desc())
                 .limit(per_page).offset((page - 1) * per_page).all())

    # Embed staff brief so supervisors can see who did what without a second query
    user_ids = {r.user_id for r in rows}
    users_by_id = {u.id: u.to_brief()
                   for u in AuthUser.query.filter(AuthUser.id.in_(user_ids)).all()} if user_ids else {}

    payload = []
    for r in rows:
        d = r.to_dict()
        d['user'] = users_by_id.get(r.user_id)
        payload.append(d)

    return jsonify({
        'logs': payload,
        'total': total,
        'page': page,
        'per_page': per_page,
    }), 200


# ─────────────────────────────────────────────
# GET /api/logs/system  — admin only
# ─────────────────────────────────────────────

@logs_bp.route('/logs/system', methods=['GET'])
@jwt_required()
def system_logs():
    user, err = _require_role({'admin'})
    if err:
        return err

    page, per_page = _paginate_params()
    dt_from, dt_to = _date_window()
    search = request.args.get('search', type=str)
    levels = _csv_list(request.args.get('level'))
    sources = _csv_list(request.args.get('source'))
    conversation_id = request.args.get('conversation_id', type=int)

    query = Log.query

    if levels:
        query = query.filter(Log.level.in_(levels))
    if sources:
        query = query.filter(Log.source.in_(sources))
    if conversation_id:
        query = query.filter(Log.conversation_id == conversation_id)
    if dt_from:
        query = query.filter(Log.created_at >= dt_from)
    if dt_to:
        query = query.filter(Log.created_at <= dt_to)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(Log.message.ilike(like))

    total = query.count()
    rows = (query.order_by(Log.created_at.desc())
                 .limit(per_page).offset((page - 1) * per_page).all())

    return jsonify({
        'logs': [r.to_dict() for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
    }), 200


# ─────────────────────────────────────────────
# GET /api/logs/feed  — Dashboard live activity feed
# Returns pipeline events from the `logs` table (not audit_logs),
# scoped to the user's role:
#   - admin/supervisor : all pipeline events
#   - agent            : only events touching their assigned conversations
# ─────────────────────────────────────────────

@logs_bp.route('/logs/feed', methods=['GET'])
@jwt_required()
def feed_logs():
    user, err = _require_user()
    if err:
        return err

    page, per_page = _paginate_params()

    query = Log.query

    # Agents see only their assigned conversations
    if user.role == 'agent':
        from app.models import Conversation
        assigned = db.session.query(Conversation.id).filter(
            Conversation.assigned_to == user.id
        ).subquery()
        query = query.filter(Log.conversation_id.in_(assigned))

    rows = (query.order_by(Log.created_at.desc())
                 .limit(per_page).offset((page - 1) * per_page).all())

    return jsonify({
        'logs': [r.to_dict() for r in rows],
        'page': page,
        'per_page': per_page,
    }), 200