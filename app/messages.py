"""
app/messages.py
Messages / Inbox routes — list conversations, read a thread, send manual replies.

Data source: real DB queries against models (User, Conversation, Message).
Reply scope for this pass: persist outbound message to DB only.
Actually pushing the reply to the social platform is a later TODO (handled
by the integrations layer), so the reply endpoint does NOT call any external
API yet.

Contract: see ARCHITECTURE.md §4.2 (canonical).
  - Pagination: page / per_page  (response echoes total, page, per_page)
  - Channel filter param: `channel`  (mirrors the DB column)
  - List response:  { conversations, total, page, per_page }
  - Single conv:    { conversation: { ..., messages: [...] } }   (wrapped)
  - Send reply:     POST /conversations/<id>/messages  { content, sender }
                    -> { message, conversation }
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import AuthUser, Conversation, Message, User
from app.auth import log_audit

messages_bp = Blueprint('messages', __name__, url_prefix='/api')


VALID_STATUSES = {'active', 'resolved', 'human_override', 'pending'}
VALID_SENDERS = {'human', 'ai', 'system'}

# Pagination guard rails
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def _current_user():
    """Resolve the AuthUser making this request, or None.
    JWT identity is stored as a string; cast back to int for the PK lookup."""
    identity = get_jwt_identity()
    try:
        return AuthUser.query.get(int(identity))
    except (TypeError, ValueError):
        return None


@messages_bp.route('/conversations', methods=['GET'])
@jwt_required()
def list_conversations():
    """
    List conversations for the inbox.

    Query parameters:
    - page:     1-based page number (default 1)
    - per_page: page size (default 20, max 100)
    - channel:  filter by channel (e.g. instagram_dm). 'all' or omitted = no filter.
    - status:   filter by conversation status. 'all' or omitted = no filter.
    - search:   case-insensitive match against the customer handle / last message.

    Response:
    {
        "conversations": [ { ...conversation, no messages... } ],
        "total": 12,
        "page": 1,
        "per_page": 20
    }
    """
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=DEFAULT_PER_PAGE, type=int)
    channel = request.args.get('channel', type=str)
    status = request.args.get('status', type=str)
    search = request.args.get('search', type=str)

    # Clamp pagination inputs to sane bounds.
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE

    query = Conversation.query

    if channel and channel != 'all':
        query = query.filter(Conversation.channel == channel)

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
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    return jsonify({
        'conversations': [c.to_dict(include_messages=False) for c in conversations],
        'total': total,
        'page': page,
        'per_page': per_page,
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


@messages_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
@jwt_required()
def send_reply(conversation_id):
    """
    Send a manual reply (canonical reply endpoint).

    Scope for this pass: persist the outbound message to the DB and update the
    conversation's last_message fields. Does NOT push to the social platform —
    that is wired in later by the integrations layer.

    Request body:
    {
        "content": "Hi! Yes, that's in stock.",
        "sender": "human"   # optional; one of human | ai | system. Default: human.
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
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'Message content is required'}), 400

    sender = (data.get('sender') or 'human').lower()
    if sender not in VALID_SENDERS:
        return jsonify({'error': f'Invalid sender. Must be one of: {", ".join(sorted(VALID_SENDERS))}'}), 400

    now = datetime.utcnow()

    reply = Message(
        conversation_id=conv.id,
        user_id=conv.user_id,
        channel=conv.channel,
        direction='outbound',
        sender=sender,
        content=content,
        created_at=now,
    )
    db.session.add(reply)

    # Update conversation envelope. A human reply implies an override; an AI
    # reply leaves the conversation active.
    conv.last_message = content
    conv.last_message_at = now
    if sender == 'human':
        conv.status = 'human_override'
    conv.unread_count = 0
    conv.updated_at = now

    db.session.commit()

    log_audit(
        current_user.id,
        'send_reply',
        resource_type='conversation',
        resource_id=str(conv.id),
        changes={'sender': sender, 'content_preview': content[:120]},
    )

    return jsonify({
        'message': reply.to_dict(),
        'conversation': conv.to_dict(include_messages=False),
    }), 201


@messages_bp.route('/conversations/<int:conversation_id>', methods=['PATCH'])
@jwt_required()
def update_conversation(conversation_id):
    """
    Update mutable fields on a conversation. Currently supports `status`.

    Request body:
    {
        "status": "resolved"   # one of active | resolved | human_override | pending
    }

    Response:
    {
        "conversation": { ... }
    }
    """
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    data = request.get_json(silent=True) or {}
    changes = {}

    if 'status' in data:
        new_status = (data['status'] or '').lower()
        if new_status not in VALID_STATUSES:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(sorted(VALID_STATUSES))}'}), 400
        conv.status = new_status
        changes['status'] = new_status

    if not changes:
        return jsonify({'error': 'No updatable fields provided'}), 400

    conv.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        current_user.id,
        'update_conversation',
        resource_type='conversation',
        resource_id=str(conv.id),
        changes=changes,
    )

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200


@messages_bp.route('/conversations/<int:conversation_id>/ai', methods=['PATCH'])
@jwt_required()
def toggle_ai(conversation_id):
    """
    Enable or disable AI auto-reply for a single conversation.

    Request body:
    {
        "ai_enabled": false
    }

    Response:
    {
        "conversation": { ... }
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
    """
    Mark a conversation as read (zero out unread_count).

    Response:
    {
        "conversation": { ... }
    }
    """
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    conv.unread_count = 0
    conv.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200
