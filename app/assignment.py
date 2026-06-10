"""
app/assignment.py
Conversation assignment — manual, self-claim, and auto-assign on handoff.

Endpoints (all JWT-protected, /api prefix):
  POST /api/conversations/<id>/assign   { agent_id }  — assign / reassign / self-claim
  POST /api/conversations/<id>/unassign                — supervisor+admin only

Permissions:
  - admin, supervisor: can assign to any agent
  - agent: can only assign to themselves (self-claim)
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app import db
from app.models import AuthUser, Conversation
from app.auth import log_audit, current_user_id
from app.notifications import create_notification

assignment_bp = Blueprint('assignment', __name__, url_prefix='/api')


def pick_next_agent():
    """
    Round-robin (stateless): pick the active agent with the fewest open
    assignments. Used by auto-assign on handoff. Returns AuthUser or None.
    """
    open_counts = dict(
        db.session.query(Conversation.assigned_to, func.count(Conversation.id))
        .filter(Conversation.assigned_to.isnot(None))
        .filter(Conversation.status != 'resolved')
        .group_by(Conversation.assigned_to)
        .all()
    )
    agents = (AuthUser.query
              .filter(AuthUser.role == 'agent', AuthUser.status == 'active')
              .all())
    if not agents:
        return None
    return min(agents, key=lambda a: open_counts.get(a.id, 0))


@assignment_bp.route('/conversations/<int:conversation_id>/assign', methods=['POST'])
@jwt_required()
def assign(conversation_id):
    """
    Assign / reassign / self-claim.
    Body: { "agent_id": <int> }
    """
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    data = request.get_json(silent=True) or {}
    agent_id = data.get('agent_id')
    if not isinstance(agent_id, int):
        return jsonify({'error': 'agent_id (integer) is required'}), 400

    # Agents can only assign to themselves
    if current_user.role == 'agent' and agent_id != current_user.id:
        return jsonify({'error': 'Agents can only self-claim conversations'}), 403

    target = AuthUser.query.get(agent_id)
    if not target:
        return jsonify({'error': 'Target agent not found'}), 404
    if target.status != 'active':
        return jsonify({'error': 'Target agent is not active'}), 400
    if target.role not in {'agent', 'supervisor', 'admin'}:
        return jsonify({'error': 'Target user cannot be assigned conversations'}), 400

    now = datetime.utcnow()
    previous_assignee = conv.assigned_to  # for reassignment notifications

    conv.assigned_to = target.id
    conv.assigned_at = now
    conv.assigned_by = current_user.id
    conv.updated_at = now

    # Notify the new assignee (unless they assigned to themselves)
    if target.id != current_user.id:
        is_reassign = previous_assignee is not None and previous_assignee != target.id
        create_notification(
            user_id=target.id,
            type_='reassigned' if is_reassign else 'assigned',
            title=f"Conversation assigned to you",
            body=f"From {conv.handle or 'a customer'} on {conv.channel.replace('_', ' ')}",
            resource_type='conversation',
            resource_id=conv.id,
        )

    # If this is a reassignment, notify the previous assignee that they're off the hook
    if previous_assignee is not None and previous_assignee != target.id:
        create_notification(
            user_id=previous_assignee,
            type_='unassigned',
            title=f"Conversation reassigned",
            body=f"{conv.handle or 'A conversation'} has been moved to {target.full_name}",
            resource_type='conversation',
            resource_id=conv.id,
        )

    db.session.commit()

    log_audit(
        current_user.id, 'assign_conversation',
        resource_type='conversation', resource_id=str(conv.id),
        changes={'assigned_to': target.id, 'assigned_to_email': target.email},
    )

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200


@assignment_bp.route('/conversations/<int:conversation_id>/unassign', methods=['POST'])
@jwt_required()
def unassign(conversation_id):
    """Clear assignment. Supervisor+admin only."""
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    if current_user.role not in {'admin', 'supervisor'}:
        return jsonify({'error': 'Only supervisors and admins can unassign'}), 403

    conv = Conversation.query.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    previous = conv.assigned_to
    conv.assigned_to = None
    conv.assigned_at = None
    conv.assigned_by = None
    conv.updated_at = datetime.utcnow()

    if previous is not None:
        create_notification(
            user_id=previous,
            type_='unassigned',
            title="Conversation unassigned",
            body=f"{conv.handle or 'A conversation'} is no longer assigned to you",
            resource_type='conversation',
            resource_id=conv.id,
        )

    db.session.commit()

    log_audit(
        current_user.id, 'unassign_conversation',
        resource_type='conversation', resource_id=str(conv.id),
        changes={'previous_assigned_to': previous},
    )

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200