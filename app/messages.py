"""
app/messages.py
Messages / Inbox routes — list conversations, read a thread, send manual replies.

Contract: see ARCHITECTURE.md §4.2 (canonical).
  - Pagination: page / per_page  (response echoes total, page, per_page)
  - Channel filter param: `channel`  (mirrors the DB column)
  - List response:  { conversations, total, page, per_page }
  - Single conv:    { conversation: { ..., messages: [...] } }   (wrapped)
  - Send reply:     POST /conversations/<id>/messages  { content, sender }
                    -> { message, conversation }

Foundation fields stamped here:
  - Message.sender_id  ← authed staff id when sender=='human'
  - Conversation.resolved_at / resolved_by  ← stamped when status flips to 'resolved'
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

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def _current_user():
    """Resolve the AuthUser making this request, or None."""
    identity = get_jwt_identity()
    try:
        return AuthUser.query.get(int(identity))
    except (TypeError, ValueError):
        return None


def _agent_can_access_conversation(agent_user: AuthUser, conversation: Conversation) -> bool:
    """
    Check if an agent can access a conversation.
    
    Agents can access:
    - Conversations assigned to them
    - Unassigned conversations in 'human_override' status (available queue)
    
    Admins/supervisors can access all conversations.
    """
    if not agent_user or agent_user.role != 'agent':
        return True  # Non-agents (admin/supervisor) can see all
    
    # Agent can see if:
    # 1. Assigned to them, OR
    # 2. Unassigned AND in human_override status (available queue)
    return (
        conversation.assigned_to == agent_user.id
        or (
            conversation.assigned_to is None
            and conversation.status == 'human_override'
        )
    )


@messages_bp.route('/conversations', methods=['GET'])
@jwt_required()
def list_conversations():
    """List conversations for the inbox."""
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=DEFAULT_PER_PAGE, type=int)
    channel = request.args.get('channel', type=str)
    status = request.args.get('status', type=str)
    search = request.args.get('search', type=str)

    if page < 1:
        page = 1
    if per_page < 1:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE

    # Role-aware visibility:
    #   - admin, supervisor: see all conversations
    #   - agent: see conversations assigned to them, PLUS unassigned
    #            conversations in human_override (the available queue)
    current_user = _current_user()
    query = Conversation.query

    if current_user and current_user.role == 'agent':
        query = query.filter(
            db.or_(
                Conversation.assigned_to == current_user.id,
                db.and_(
                    Conversation.assigned_to.is_(None),
                    Conversation.status == 'human_override',
                ),
            )
        )

    if channel and channel != 'all':
        query = query.filter(Conversation.channel == channel)

    if status and status != 'all':
        query = query.filter(Conversation.status == status)

    # Optional filters for supervisor/admin dashboards
    assigned_to = request.args.get('assigned_to', type=str)
    if assigned_to == 'me' and current_user:
        query = query.filter(Conversation.assigned_to == current_user.id)
    elif assigned_to == 'unassigned':
        query = query.filter(Conversation.assigned_to.is_(None))
    elif assigned_to and assigned_to.isdigit():
        query = query.filter(Conversation.assigned_to == int(assigned_to))

    if search:
        like = f"%{search.strip()}%"
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
    """Get a single conversation with its full message thread."""
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check access control
    if not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

    return jsonify({'conversation': conv.to_dict(include_messages=True)}), 200


@messages_bp.route('/conversations/<int:conversation_id>/messages', methods=['GET'])
@jwt_required()
def list_messages(conversation_id):
    """List just the messages for a conversation."""
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check access control
    if not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

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
    Send a manual reply.

    Body:
      { "content": "...", "sender": "human" | "ai" | "system"   (default: human) }

    When sender == 'human' we stamp Message.sender_id with the authed user
    so audits can recover who replied.
    """
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check access control
    if not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

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
        sender_id=(current_user.id if sender == 'human' else None),
        content=content,
        created_at=now,
    )
    db.session.add(reply)

    conv.last_message = content
    conv.last_message_at = now
    if sender == 'human':
        conv.status = 'human_override'
    conv.unread_count = 0
    conv.updated_at = now

    db.session.commit()

    # Dispatch the reply to the customer via the channel API (IG/FB/WA).
    # Same path the AI uses. Failures are logged but don't roll back the DB —
    # the agent's reply is still recorded, and they can retry from the UI.
    try:
        from app.services import _dispatch_reply
        customer = conv.user
        if customer:
            _dispatch_reply(
                channel=conv.channel,
                user_id=customer.external_id,
                reply=content,
            )
    except Exception as e:
        from app.utils.logger import log_event
        log_event("error", "messages.send_reply.dispatch",
                  f"Failed to dispatch manual reply for conv {conv.id}: {e}",
                  payload={"conversation_id": conv.id, "error": str(e)},
                  conversation_id=conv.id)

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
    Update mutable fields on a conversation. Supports `status`.

    When status flips to 'resolved' we stamp resolved_at / resolved_by.
    Flipping it back to a non-resolved status clears those fields.
    """
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check access control
    if not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    changes = {}

    if 'status' in data:
        new_status = (data['status'] or '').lower()
        if new_status not in VALID_STATUSES:
            return jsonify({'error': f'Invalid status. Must be one of: {", ".join(sorted(VALID_STATUSES))}'}), 400
        previous = conv.status
        conv.status = new_status
        changes['status'] = new_status

        if new_status == 'resolved' and previous != 'resolved':
            conv.resolved_at = datetime.utcnow()
            conv.resolved_by = current_user.id
        elif new_status != 'resolved' and previous == 'resolved':
            # Re-opened — clear the resolution stamp.
            conv.resolved_at = None
            conv.resolved_by = None

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
    """Enable or disable AI auto-reply for a single conversation."""
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check access control
    if not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json(silent=True) or {}
    if 'ai_enabled' not in data:
        return jsonify({'error': 'ai_enabled (boolean) is required'}), 400

    conv.ai_enabled = bool(data['ai_enabled'])
    # Re-enabling AI clears the stale handoff reason
    if conv.ai_enabled:
        conv.handoff_reason = None
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
    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    
    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check access control
    if not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

    conv.unread_count = 0
    conv.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200