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

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api')


def create_notification(user_id, type_, title, body=None, resource_type=None, resource_id=None):
    """
    Internal helper to create a notification. Called from assignment.py,
    handoff.py, or anywhere else that needs to alert a user.
    """
    notif = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
    )
    db.session.add(notif)
    # No commit — caller commits as part of their transaction
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