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

    # Drop agents we cannot actually reach.
    #
    # An escalation assigned to agent@company.com looks handled: the
    # conversation leaves the unassigned queue, the badge clears, and the
    # notification email goes to a domain Shop Zetu does not own. The customer
    # is then waiting on someone who will never be told.
    #
    # Unassigned is a worse-looking state and a better one — the queue shows it
    # and a supervisor can act. So a reachable agent always beats an
    # unreachable one, and if NONE are reachable the conversation stays in the
    # queue and says why, rather than being quietly parked on a dead mailbox.
    from app.utils.email import unreachable_reason
    from app.utils.logger import log_event
    reachable = [a for a in agents if not unreachable_reason(getattr(a, 'email', None))]
    if len(reachable) < len(agents):
        skipped = [a.email for a in agents if unreachable_reason(getattr(a, 'email', None))]
        log_event("warn", "assignment.unreachable_agents",
                  f"{len(skipped)} active agent(s) skipped for auto-assignment - "
                  f"their addresses cannot receive mail: {', '.join(skipped)}")
    if reachable:
        agents = reachable
    elif agents:
        log_event("error", "assignment.no_reachable_agent",
                  f"All {len(agents)} active agents have unreachable email addresses "
                  f"({', '.join(a.email for a in agents)}). Escalations will stay "
                  f"unassigned until a real address is set.")
        return None

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

    if current_user.role == 'agent':
        if agent_id != current_user.id:
            return jsonify({'error': 'Agents can only self-claim conversations'}), 403
        # Self-claim means taking from the QUEUE, not taking from a colleague.
        # This checked who could be assigned but never which conversation, so
        # an agent could POST any conversation id and reassign it to
        # themselves — verified: agent 7 took conversation 11 off agent 5.
        # Reassigning someone else's work stays a supervisor decision.
        if conv.assigned_to is not None and conv.assigned_to != current_user.id:
            return jsonify({
                'error': 'That conversation is already assigned to someone else. '
                         'Ask a supervisor to reassign it.'
            }), 403

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
    # Taking a conversation is an act of ownership, so it stops being "whatever
    # the global switch did to it".
    #
    # Only the per-conversation AI toggle used to clear this stamp, which meant
    # an agent could claim an auto-paused chat out of Unclaimed, work it for
    # days, and have a global "turn AI back on" take it away mid-thread —
    # because they had never happened to touch that one toggle. Claiming it is
    # the clearer signal and the one people actually perform.
    conv.ai_auto_paused_at = None

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
                  "handle": (conv.user.handle if conv.user else None),
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
                  "handle": (conv.user.handle if conv.user else None),
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

# ─────────────────────────────────────────────
# Unclaimed queue watchdog
# ─────────────────────────────────────────────

def queued_since(conv):
    """
    When this conversation started waiting for a human.

    escalated_at is the precise signal, but a conversation can also reach the
    queue by a supervisor unassigning it, which stamps neither — so fall back
    through the next-best timestamps rather than skipping those rows.
    """
    return (conv.escalated_at
            or conv.ai_disabled_at
            or conv.last_message_at
            or conv.created_at)


def find_unclaimed(threshold_minutes: int | None = None):
    """
    Conversations sitting in the human queue with nobody on them for longer
    than the alert threshold. Returns [(conversation, waited_minutes), ...],
    longest wait first.

    Escalations auto-assign (see pick_next_agent), and that only fails when
    there are NO active agents at all — so anything in here means either the
    roster is empty or someone unassigned it by hand. Both are worth saying
    out loud rather than letting a waiting customer go quiet.
    """
    from app.settings import get_section
    if threshold_minutes is None:
        threshold_minutes = int(get_section("handoff").get("unclaimed_alert_minutes", 15))

    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=threshold_minutes)

    rows = (Conversation.query
            .filter(Conversation.assigned_to.is_(None))
            .filter(Conversation.status == 'human_override')
            .all())

    out = []
    for conv in rows:
        since = queued_since(conv)
        if since is None or since > cutoff:
            continue
        out.append((conv, int((now - since).total_seconds() // 60)))
    out.sort(key=lambda pair: pair[1], reverse=True)
    return out


def alert_unclaimed(threshold_minutes: int | None = None) -> dict:
    """
    Log and notify for anything stuck in the queue. Alerts ONCE per waiting
    spell — re-alerting every cron tick would train people to ignore it — by
    skipping conversations that already have a handoff.unclaimed log recorded
    after they entered the queue.
    """
    from app.models import Log
    from app.utils.logger import log_event

    stuck = find_unclaimed(threshold_minutes)
    alerted, skipped = [], 0

    for conv, waited in stuck:
        since = queued_since(conv)
        already = (Log.query
                   .filter(Log.source == 'handoff.unclaimed')
                   .filter(Log.conversation_id == conv.id)
                   .filter(Log.created_at >= since)
                   .first())
        if already:
            skipped += 1
            continue

        handle = conv.user.handle if conv.user else f'conversation {conv.id}'
        log_event("error", "handoff.unclaimed",
                  f"{handle} has waited {waited} min in the queue with no agent assigned",
                  payload={"waited_minutes": waited, "channel": conv.channel,
                           "handle": handle},
                  conversation_id=conv.id)

        for boss in AuthUser.query.filter(
            AuthUser.role.in_(['admin', 'supervisor']),
            AuthUser.status == 'active',
        ).all():
            create_notification(
                user_id=boss.id,
                type_='unclaimed',
                title="Conversation waiting, unassigned",
                body=f"{handle} has waited {waited} min with nobody assigned",
                severity='warning',
                resource_type='conversation', resource_id=conv.id,
            )
        alerted.append({'conversation_id': conv.id, 'waited_minutes': waited})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_event("error", "assignment.unclaimed_alert_fail", str(e))

    return {'stuck': len(stuck), 'alerted': alerted, 'already_alerted': skipped}


# ─────────────────────────────────────────────
# Silent-conversation watchdog
# ─────────────────────────────────────────────
#
# find_unclaimed() only looks at status='human_override', which is the queue an
# escalation lands in. That misses the worst case entirely: a conversation left
# at status='active' with ai_enabled=true and nobody assigned. The AI is not
# answering it (master switch off, a failed generation, a gate that declined),
# it is in no agent's inbox, and it is not in Unclaimed either — so nothing
# anywhere reports it.
#
# That is not hypothetical. When this was written, 13 direct messages had been
# sitting in exactly that state for between 7 and 18 days on a live account.
# DMs reply to everything by design, so silence there is never intentional.
#
# This check ignores status and ai_enabled entirely and asks the only question
# that actually matters to a customer: did they speak last, and how long ago?

def find_silent_conversations(threshold_hours: int | None = None):
    """
    Conversations where the customer spoke last and nobody has answered.

    Returns [(conversation, hours_waiting), ...], longest wait first.

    Deliberately does NOT filter on status, ai_enabled or assignee. Every one
    of those filters is what let the 13 DMs hide — a conversation is either
    answered or it is not, and the customer does not care which internal
    bucket it sits in.

    Public comments are excluded: the assistant declines praise and non-questions
    on public posts on purpose, so "no reply" there is usually correct and
    alerting on it would bury the real ones.
    """
    from app.models import Message
    from app.settings import get_section

    if threshold_hours is None:
        threshold_hours = int(get_section("handoff").get("silent_alert_hours", 24))

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=threshold_hours)

    rows = (Conversation.query
            .filter(Conversation.status != 'resolved')
            .filter(~Conversation.channel.like('%_comment'))
            .all())

    out = []
    for conv in rows:
        last = (Message.query
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc())
                .first())
        if last is None or last.direction != 'inbound':
            continue
        if last.created_at > cutoff:
            continue
        out.append((conv, int((now - last.created_at).total_seconds() // 3600)))

    out.sort(key=lambda pair: pair[1], reverse=True)
    return out


def alert_silent(threshold_hours: int | None = None) -> dict:
    """
    Log and notify for conversations nobody has answered.

    Alerts once per silent spell, keyed on the last inbound message's time, so
    a conversation that stays unanswered does not re-alert on every tick.
    """
    from app.models import Log, Message
    from app.utils.logger import log_event

    silent = find_silent_conversations(threshold_hours)
    alerted, skipped = [], 0

    for conv, hours in silent:
        last = (Message.query
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc())
                .first())
        since = last.created_at if last else conv.created_at

        already = (Log.query
                   .filter(Log.source == 'handoff.silent')
                   .filter(Log.conversation_id == conv.id)
                   .filter(Log.created_at >= since)
                   .first())
        if already:
            skipped += 1
            continue

        handle = conv.user.handle if conv.user else f'conversation {conv.id}'
        log_event("error", "handoff.silent",
                  f"{handle} has waited {hours}h with no reply from anyone",
                  payload={"hours_waiting": hours, "channel": conv.channel,
                           "handle": handle, "status": conv.status,
                           "ai_enabled": bool(conv.ai_enabled),
                           "assigned": conv.assigned_to is not None},
                  conversation_id=conv.id)

        for boss in AuthUser.query.filter(
            AuthUser.role.in_(['admin', 'supervisor']),
            AuthUser.status == 'active',
        ).all():
            create_notification(
                user_id=boss.id,
                type_='unanswered',
                title="Customer waiting with no reply",
                body=f"{handle} has waited {hours}h and neither the AI nor an agent has answered",
                severity='warning',
                resource_type='conversation', resource_id=conv.id,
            )
        alerted.append({'conversation_id': conv.id, 'hours_waiting': hours})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_event("error", "assignment.silent_alert_fail", str(e))

    return {'silent': len(silent), 'alerted': alerted, 'already_alerted': skipped}


@assignment_bp.route('/conversations/unclaimed', methods=['GET'])
@jwt_required()
def unclaimed_queue():
    """
    What's waiting, and for how long. Supervisor/admin only — this is a
    roster-management view, not an agent one.
    """
    user = AuthUser.query.get(current_user_id())
    if not user or user.role not in {'admin', 'supervisor'}:
        return jsonify({'error': 'Forbidden'}), 403

    # ?threshold_minutes=0 lists the whole queue, not just the overdue part.
    threshold = request.args.get('threshold_minutes', type=int)
    rows = find_unclaimed(threshold)
    return jsonify({
        'unclaimed': [{
            'conversation_id': conv.id,
            'channel': conv.channel,
            'handle': conv.user.handle if conv.user else None,
            'waited_minutes': waited,
            'queued_since': queued_since(conv).isoformat() if queued_since(conv) else None,
        } for conv, waited in rows],
        'count': len(rows),
    }), 200
