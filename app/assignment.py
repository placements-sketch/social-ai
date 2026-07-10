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


import os
from datetime import datetime, timedelta

# Max open conversations before an agent is skipped for auto-assignment.
MAX_AGENT_LOAD = int(os.getenv('MAX_AGENT_LOAD', '10'))
# "Present" = seen within this many seconds (matches online + idle window).
PRESENCE_WINDOW_SECONDS = int(os.getenv('PRESENCE_WINDOW_SECONDS', '300'))


def pick_next_agent():
    """
    Choose the best agent for an auto-assignment:
      1. Any ACTIVE agent is eligible — we do NOT require them to be currently
         online. (A chat that escalates before anyone clocks in should still get
         an owner, waiting for them, rather than sitting unassigned.)
      2. Skip anyone at/over the max open-conversation load (no overloading).
      3. Fewest open conversations wins; ties broken by presence (someone online
         now is preferred), then by least-recently-assigned for fair rotation.
    Returns an AuthUser, or None only if there are NO active agents at all.
    """
    from app.settings import get_section
    _hs = get_section("handoff")
    max_load = int(_hs.get("max_agent_load", MAX_AGENT_LOAD))
    presence_window = int(_hs.get("presence_window_seconds", PRESENCE_WINDOW_SECONDS))
    present_cutoff = datetime.utcnow() - timedelta(seconds=presence_window)

    open_counts = dict(
        db.session.query(Conversation.assigned_to, func.count(Conversation.id))
        .filter(Conversation.assigned_to.isnot(None))
        .filter(Conversation.status != 'resolved')
        .group_by(Conversation.assigned_to)
        .all()
    )
    last_assigned = dict(
        db.session.query(Conversation.assigned_to, func.max(Conversation.assigned_at))
        .filter(Conversation.assigned_to.isnot(None))
        .group_by(Conversation.assigned_to)
        .all()
    )

    # Any active agent — presence is NOT a hard filter anymore.
    agents = (AuthUser.query
              .filter(AuthUser.role == 'agent', AuthUser.status == 'active')
              .all())

    # Respect the load cap so we still don't pile onto a saturated agent.
    eligible = [a for a in agents if open_counts.get(a.id, 0) < max_load]
    if not eligible:
        # Everyone's at capacity — fall back to ALL active agents rather than
        # queue it (an owned-but-busy chat beats an orphaned one).
        eligible = agents
    if not eligible:
        return None  # genuinely no active agents exist → queue it

    def _is_present(a):
        return bool(a.last_seen_at and a.last_seen_at >= present_cutoff)

    # Fewest open convs first; then prefer someone present right now;
    # then least-recently-assigned for fair rotation.
    def sort_key(a):
        return (
            open_counts.get(a.id, 0),
            0 if _is_present(a) else 1,          # online-now wins ties
            last_assigned.get(a.id) or datetime.min,
        )

    return min(eligible, key=sort_key)


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
    previous_assignee = conv.assigned_to
    prev_user = AuthUser.query.get(previous_assignee) if previous_assignee else None  # fetch once (#3)
    is_reassign = previous_assignee is not None and previous_assignee != target.id

    conv.assigned_to = target.id
    conv.assigned_at = now
    conv.assigned_by = current_user.id
    conv.updated_at = now

    # Commit the assignment FIRST — notifications must never roll it back (#1).
    db.session.commit()

    log_audit(
        current_user.id, 'assign_conversation',
        resource_type='conversation', resource_id=str(conv.id),
        changes={'assigned_to': target.id, 'assigned_to_email': target.email},
    )

    from app.utils.logger import log_event
    log_event("info", "assignment.assigned",
              f"Conversation {conv.id} {'reassigned' if is_reassign else 'assigned'} to {target.email}",
              payload={
                  "agent_id": target.id, "agent_email": target.email,
                  "agent_name": target.full_name,
                  "assigned_by_id": current_user.id, "assigned_by_email": current_user.email,
                  "is_reassign": is_reassign, "previous_assignee_id": previous_assignee,
                  "channel": conv.channel,
                  "handle": (conv.user.external_id if conv.user else None),
              },
              conversation_id=conv.id)

    # All notifications are best-effort — a failure here must not 500 the request (#1).
    try:
        handle = conv.user.handle if conv.user else 'a customer'

        if target.id != current_user.id:
            create_notification(
                user_id=target.id,
                type_='reassigned' if is_reassign else 'assigned',
                title="Conversation assigned to you",
                body=f"From {handle} on {conv.channel.replace('_', ' ')}",
                resource_type='conversation', resource_id=conv.id,
            )
            for admin in AuthUser.query.filter(
                AuthUser.role.in_(['admin', 'supervisor']), AuthUser.id != target.id
            ).all():
                create_notification(
                    user_id=admin.id,
                    type_='reassigned' if is_reassign else 'assigned',
                    title=f"Conversation assigned to {target.full_name}",
                    body=f"From {handle} on {conv.channel.replace('_', ' ')}",
                    resource_type='conversation', resource_id=conv.id,
                )

        if is_reassign:
            create_notification(
                user_id=previous_assignee,
                type_='unassigned',
                title="Conversation reassigned",
                body=f"{handle} has been moved to {target.full_name}",
                resource_type='conversation', resource_id=conv.id,
            )
            prev_name = prev_user.full_name if prev_user else 'someone'
            for admin in AuthUser.query.filter(
                AuthUser.role.in_(['admin', 'supervisor']), AuthUser.id != previous_assignee
            ).all():
                create_notification(
                    user_id=admin.id,
                    type_='unassigned',
                    title="Conversation reassigned",
                    body=f"{handle} moved from {prev_name} to {target.full_name}",
                    resource_type='conversation', resource_id=conv.id,
                )
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_event("error", "assignment.notify_fail",
                  f"Assignment notifications failed: {e}", conversation_id=conv.id)

    # Surface presence + current load so the UI can warn on offline/saturated (#2/#4).
    try:
        open_load = (Conversation.query
                     .filter(Conversation.assigned_to == target.id,
                             Conversation.status != 'resolved').count())
        conv_dict = conv.to_dict(include_messages=False)
        conv_dict['assignee_presence'] = target.presence_status()
        conv_dict['assignee_open_load'] = open_load
        return jsonify({'conversation': conv_dict}), 200
    except Exception as e:
        import traceback
        from flask import current_app
        current_app.logger.error(f"Error serializing conversation {conversation_id}: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': f'Error serializing conversation: {str(e)}'}), 500

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
    prev_user = AuthUser.query.get(previous) if previous else None

    conv.assigned_to = None
    conv.assigned_at = None
    conv.assigned_by = None
    conv.updated_at = datetime.utcnow()

    # Commit the unassignment FIRST — notifications must never roll it back.
    db.session.commit()

    log_audit(
        current_user.id, 'unassign_conversation',
        resource_type='conversation', resource_id=str(conv.id),
        changes={'previous_assigned_to': previous},
    )

    from app.utils.logger import log_event
    log_event("info", "assignment.unassigned",
              f"Conversation {conv.id} unassigned",
              payload={
                  "previous_assignee_id": previous,
                  "unassigned_by_id": current_user.id,
                  "unassigned_by_email": current_user.email,
                  "channel": conv.channel,
                  "handle": (conv.user.external_id if conv.user else None),
              },
              conversation_id=conv.id)

    # Best-effort notifications — a failure here must not 500 the request.
    if previous is not None:
        try:
            handle = conv.user.handle if conv.user else 'a customer'
            create_notification(
                user_id=previous,
                type_='unassigned',
                title="Conversation unassigned",
                body=f"{handle} is no longer assigned to you",
                resource_type='conversation', resource_id=conv.id,
            )
            for admin in AuthUser.query.filter(
                AuthUser.role.in_(['admin', 'supervisor']),
                AuthUser.id != previous,
            ).all():
                create_notification(
                    user_id=admin.id,
                    type_='unassigned',
                    title="Conversation unassigned",
                    body=f"{handle} is no longer assigned to anyone",
                    resource_type='conversation', resource_id=conv.id,
                )
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            log_event("error", "assignment.notify_fail",
                      f"Unassign notifications failed: {e}", conversation_id=conv.id)

    try:
        return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200
    except Exception as e:
        import traceback
        from flask import current_app
        current_app.logger.error(f"Error serializing conversation {conversation_id}: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': f'Error serializing conversation: {str(e)}'}), 500