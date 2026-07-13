"""
app/notifications.py
In-app notifications for staff. Created by assignment events and other
system actions, surfaced through the bell icon in the top bar.

Endpoints (JWT-protected, /api prefix):
  GET   /api/notifications          list current user's notifications
  PATCH /api/notifications/<id>/read    mark one as read
  PATCH /api/notifications/read-all     mark all as read
"""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db
from app.models import AuthUser, Notification, Conversation
from app.auth import current_user_id
import os

def _notify_role(roles, type_, title, body=None, severity='info',
                 resource_type=None, resource_id=None, actor_id=None,
                 coalesce=False):
    """
    Create one notification per user matching the given role(s).
    Skips the actor (they don't need to be notified of their own action).
    """
    if isinstance(roles, str):
        roles = [roles]

    targets_q = AuthUser.query.filter(AuthUser.role.in_(roles),
                                      AuthUser.status == 'active')
    if actor_id is not None:
        targets_q = targets_q.filter(AuthUser.id != actor_id)

    for target in targets_q.all():
        create_notification(
            user_id=target.id,
            type_=type_,
            title=title,
            body=body,
            severity=severity,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            coalesce=coalesce,
        )


def notify_admins(type_, title, body=None, severity='info',
                  resource_type=None, resource_id=None, actor_id=None,
                  coalesce=False):
    """Shortcut: notify all admins."""
    _notify_role('admin', type_, title, body, severity,
                 resource_type, resource_id, actor_id, coalesce)


def notify_supervisors(type_, title, body=None, severity='info',
                       resource_type=None, resource_id=None, actor_id=None,
                       coalesce=False):
    """Shortcut: notify all admins + supervisors."""
    _notify_role(['admin', 'supervisor'], type_, title, body, severity,
                 resource_type, resource_id, actor_id, coalesce)

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api')


from datetime import datetime, timedelta

VALID_SEVERITIES = {'info', 'warning', 'urgent'}

# How recent an existing notification must be to coalesce a new one into it.
COALESCE_WINDOW_MINUTES = 5

from app.utils.email import send_email
from app.utils.logger import log_event


def _email_urgent_notification(user_id, title, body):
    """Send an urgent notification to the recipient's email via Brevo."""
    user = AuthUser.query.get(user_id)
    if not user or not user.email or user.status != 'active':
        return
    send_email(
        user.email,
        f"[Urgent] {title}",
        _urgent_email_html(user.full_name, title, body),
        _urgent_email_text(user.full_name, title, body),
    )


def _urgent_email_html(name, title, body):
    return (
        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px">'
        '<div style="background:#fff4ed;border-left:4px solid #ff5900;padding:12px 16px;border-radius:6px;margin-bottom:16px">'
        '<span style="color:#ff5900;font-size:12px;font-weight:bold;text-transform:uppercase;letter-spacing:.05em">Urgent</span>'
        '</div>'
        f'<h2 style="color:#1a1a2e;margin:0 0 8px;font-size:18px">{title}</h2>'
        + (f'<p style="color:#555;font-size:14px;line-height:1.6">{body}</p>' if body else '') +
        '<p style="margin:24px 0"><a href="' + (os.getenv('FRONTEND_URL', '').rstrip('/') or '#') +
        '" style="background:#ff5900;color:#fff;text-decoration:none;font-weight:bold;font-size:14px;'
        'padding:12px 22px;border-radius:8px;display:inline-block">Open dashboard</a></p>'
        f'<p style="color:#bbb;font-size:11px;margin-top:24px">Hi {name or "there"} — you\'re getting this because '
        'it needs prompt attention. Shop Zetu · Social AI Assistant</p></div>'
    )


def _urgent_email_text(name, title, body):
    lines = [f"[URGENT] {title}"]
    if body:
        lines.append("")
        lines.append(body)
    lines.append("")
    lines.append("Open your dashboard to respond.")
    lines.append("— Shop Zetu · Social AI Assistant")
    return "\n".join(lines)


def create_notification(
    user_id,
    type_,
    title,
    body=None,
    severity='info',
    resource_type=None,
    resource_id=None,
    actor_id=None,
    coalesce=False,
):
    """
    Internal helper to create a notification.

    Args:
        user_id: who receives this
        type_: notification type, e.g. 'conversation_escalated', 'automation_rule_changed'
        title: short summary shown in the bell + page
        body: optional fuller description
        severity: 'info' (default), 'warning', or 'urgent'. Urgent drives the toast.
        resource_type / resource_id: link target, e.g. 'conversation' + 123
        actor_id: who triggered this action; used to suppress self-notifications upstream
        coalesce: if True, merge into an existing unread notif of the same type
                  for the same (user, resource) within the last COALESCE_WINDOW_MINUTES.
                  Use for high-frequency events like automation toggles.

    Returns the Notification row (existing if coalesced, new otherwise).
    Caller is responsible for the commit.
    """
    sev = severity if severity in VALID_SEVERITIES else 'info'

    # Don't notify the user about their own action.
    if actor_id is not None and actor_id == user_id:
        return None

    if coalesce:
        cutoff = datetime.utcnow() - timedelta(minutes=COALESCE_WINDOW_MINUTES)
        existing = (Notification.query
                    .filter(Notification.user_id == user_id)
                    .filter(Notification.type == type_)
                    .filter(Notification.resource_type == resource_type)
                    .filter(Notification.resource_id == (str(resource_id) if resource_id is not None else None))
                    .filter(Notification.read_at.is_(None))
                    .filter(Notification.created_at >= cutoff)
                    .order_by(Notification.created_at.desc())
                    .first())
        if existing:
            existing.title = title
            if body is not None:
                existing.body = body
            existing.created_at = datetime.utcnow()  # bump so it sorts to top
            return existing

    notif = Notification(
        user_id=user_id,
        type=type_,
        severity=sev,
        title=title,
        body=body,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        actor_id=actor_id,
    )
    db.session.add(notif)

    # Urgent notifications also go out by email (best-effort — a mail failure
    # must never break the in-app notification, which is the source of truth).
    if sev == 'urgent':
        try:
            _email_urgent_notification(user_id, title, body)
        except Exception as e:
            log_event('warning', 'notifications.email_failed', str(e))

    return notif


@notifications_bp.route('/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    """
    Returns current user's notifications.

    Query params:
      ?unread_only=true   only unread
      ?limit=20           default 20, max 100
      ?days=7             only notifications from the last N days (default 7)
    """
    uid = current_user_id()
    if not uid:
        return jsonify({'error': 'User not found'}), 404

    unread_only = request.args.get('unread_only', '').lower() in ('1', 'true', 'yes')
    limit = min(100, max(1, request.args.get('limit', default=20, type=int)))
    days = max(1, request.args.get('days', default=7, type=int))

    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (Notification.query
             .filter(Notification.user_id == uid)
             .filter(Notification.created_at >= cutoff))

    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    rows = query.order_by(Notification.created_at.desc()).limit(limit).all()

    unread_count = (Notification.query
                    .filter(Notification.user_id == uid)
                    .filter(Notification.read_at.is_(None))
                    .count())

    return jsonify({
        'notifications': [n.to_dict() for n in rows],
        'unread_count': unread_count,
        'total': len(rows),
    }), 200


@notifications_bp.route('/notifications/<int:notif_id>/read', methods=['PATCH'])
@jwt_required()
def mark_read(notif_id):
    uid = current_user_id()
    notif = Notification.query.filter_by(id=notif_id, user_id=uid).first()
    if not notif:
        return jsonify({'error': 'Notification not found'}), 404

    if notif.read_at is None:
        notif.read_at = datetime.utcnow()
        db.session.commit()

    return jsonify({'notification': notif.to_dict()}), 200


@notifications_bp.route('/notifications/read-all', methods=['PATCH'])
@jwt_required()
def mark_all_read():
    uid = current_user_id()
    now = datetime.utcnow()

    updated = (Notification.query
               .filter_by(user_id=uid)
               .filter(Notification.read_at.is_(None))
               .update({'read_at': now}, synchronize_session=False))
    db.session.commit()

    return jsonify({'marked_read': updated}), 200