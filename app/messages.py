"""
app/messages.py
Messages / Inbox routes — list conversations, read a thread, send manual replies.

Data source: real DB queries against models (User, Conversation, Message).
Reply scope for this pass: persist outbound message to DB only.
Actually pushing the reply to the social platform is a later TODO (handled
by the integrations layer), so send_reply does NOT call any external API yet.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import AuthUser, Conversation, Message, User
from app.auth import log_audit

messages_bp = Blueprint('messages', __name__, url_prefix='/api')


VALID_STATUSES = {'active', 'resolved', 'human_override', 'pending'}


def _current_user():
    """Resolve the AuthUser making this request, or None."""
    return AuthUser.query.get(get_jwt_identity())


@messages_bp.route('/conversations', methods=['GET'])
@jwt_required()
def list_conversations():
    """
    List conversations for the inbox.

    Query parameters:
    - platform: filter by channel (e.g. instagram_dm). 'all' or omitted = no filter.
    - status:   filter by conversation status.
    - search:   case-insensitive match against the customer handle / last message.
    - limit:    default 50
    - offset:   default 0

    Response:
    {
        "conversations": [ { ...conversation, no messages... } ],
        "total": 12,
        "limit": 50,
        "offset": 0
    }
    """
    platform = request.args.get('platform', type=str)
    status = request.args.get('status', type=str)
    search = request.args.get('search', type=str)
    limit = request.args.get('limit', default=50, type=int)
    offset = request.args.get('offset', default=0, type=int)

    query = Conversation.query

    if platform and platform != 'all':
        query = query.filter(Conversation.channel == platform)

    if status and status != 'all':
        query = query.filter(Conversation.status == status)

    if search:
        like = f"%{search.strip()}%"
        # Join users so we can search the customer handle as well as last_message.
        query = query.join(User, Conversation.user_id == User.id).filter(
            db.or_(
                Conversation.last_message.ilike(like),
                User.name.ilike(like),
                User.external_id.ilike(like),
            )
        )

    total = query.count()

    conversations = (
        query.order_by(Conversation.last_message_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return jsonify({
        'conversations': [c.to_dict(include_messages=False) for c in conversations],
        'total': total,
        'limit': limit,
        'offset': offset,
    }), 200


@messages_bp.route('/conversations/<int:conversation_id>', methods=['GET'])
@jwt_required()
def get_conversation(conversation_id):
    """
    Get a single conversation with its full message thread.

    Response:
    {
        "conversation": { ...conversation, "messages": [ ... ] }
    }
    """
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    return jsonify({
        'conversation': conv.to_dict(include_messages=True)
    }), 200


@messages_bp.route('/conversations/<int:conversation_id>/messages', methods=['GET'])
@jwt_required()
def list_messages(conversation_id):
    """
    List just the messages for a conversation (thread refresh without re-fetching
    the conversation envelope).

    Response:
    {
        "messages": [ ... ]
    }
    """
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    msgs = (
        Message.query.filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return jsonify({'messages': [m.to_dict() for m in msgs]}), 200


@messages_bp.route('/conversations/<int:conversation_id>/reply', methods=['POST'])
@jwt_required()
def send_reply(conversation_id):
    """
    Send a manual (human agent) reply.

    Scope for this pass: persist the outbound message to the DB and update the
    conversation's last_message fields. Does NOT push to the social platform —
    that is wired in later by the integrations layer.

    Request body:
    {
        "text": "Hi! Yes, that's in stock."
    }

    Response:
    {
        "message": { ...the created Message... },
        "conversation": { ...updated conversation envelope... }
    }
    """
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Reply text is required'}), 400

    now = datetime.utcnow()

    reply = Message(
        conversation_id=conv.id,
        user_id=conv.user_id,
        channel=conv.channel,
        direction='outbound',
        sender='human',
        content=text,
        created_at=now,
    )
    db.session.add(reply)

    # Update conversation envelope. A human reply implies an override.
    conv.last_message = text
    conv.last_message_at = now
    conv.status = 'human_override'
    conv.unread_count = 0
    conv.updated_at = now

    db.session.commit()

    log_audit(
        current_user.id,
        'send_reply',
        resource_type='conversation',
        resource_id=str(conv.id),
        changes={'text_preview': text[:120]},
    )

    return jsonify({
        'message': reply.to_dict(),
        'conversation': conv.to_dict(include_messages=False),
    }), 201


@messages_bp.route('/conversations/<int:conversation_id>/ai', methods=['PATCH'])
@jwt_required()
def toggle_ai(conversation_id):
    """
    Enable or disable AI auto-reply for a single conversation.

    Request body:
    {
        "ai_enabled": false
    }
    """
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    data = request.get_json(silent=True) or {}
    if 'ai_enabled' not in data:
        return jsonify({'error': 'ai_enabled (boolean) is required'}), 400

    conv.ai_enabled = bool(data['ai_enabled'])
    conv.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        current_user.id,
        'toggle_ai',
        resource_type='conversation',
        resource_id=str(conv.id),
        changes={'ai_enabled': conv.ai_enabled},
    )

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200


@messages_bp.route('/conversations/<int:conversation_id>/read', methods=['PATCH'])
@jwt_required()
def mark_read(conversation_id):
    """Mark a conversation as read (zero out unread_count)."""
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    conv.unread_count = 0
    conv.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200
