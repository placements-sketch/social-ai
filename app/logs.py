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
from app.auth import current_user_id, log_audit
# alerts() calls this from three except blocks and it was never imported, so a
# failure in any of them raised NameError from inside the handler — replacing
# the real error with a misleading one at the exact moment someone is debugging.
from app.utils.logger import log_event

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
        # Same treatment as the feed: the System Logs tab renders `message`
        # verbatim, and those strings have raw IGSIDs written into them.
        'logs': _with_customer_handles(rows),
        'total': total,
        'page': page,
        'per_page': per_page,
    }), 200


# Sources the Live Activity feed shows. Keep this in step with the formatter
# in frontend/src/pages/Dashboard.jsx — an entry here with no case there
# renders as a raw internal log line, which is what this list exists to stop.
def accessible_conversation_ids(user):
    """
    Conversations an agent may see: assigned to them, or sitting unassigned in
    the human_override queue where anyone can claim them. Matches the Messages
    access model. Shared by the activity feed and the alerts panel so the two
    can't drift apart.
    """
    from sqlalchemy import or_, and_
    from app.models import Conversation
    return Conversation.query.with_entities(Conversation.id).filter(
        or_(
            Conversation.assigned_to == user.id,
            and_(
                Conversation.assigned_to.is_(None),
                Conversation.status == 'human_override',
            ),
        )
    )


ACTIVITY_SOURCES = (
    # A customer said something, or we answered (or didn't)
    'services.inbound',
    'services.ai_reply',
    'services.template_reply',
    'services.no_reply_sent',
    # Handed to a person
    'handoff.triggered',
    'handoff.auto_assigned',
    'assignment.assigned',
    'assignment.unassigned',
    # Faults that happened TO A CUSTOMER. Infrastructure faults with no
    # conversation attached (sync_jobs.failed and friends) belong in System
    # Alerts, not here — seven stale sync failures were crowding out every
    # customer event. Everything in this list is conversation-linked, which
    # also means every row in the feed can be clicked through to.
    'ai.generator.failure',
    'services.pipeline_exception',
)


# ─────────────────────────────────────────────
# GET /api/logs/feed  — Dashboard live activity feed
# Returns pipeline events from the `logs` table (not audit_logs).
# Role-scoped (matches Messages / Analytics):
#   - admin, supervisor : full system-wide activity
#   - agent             : only activity for conversations they can access
# ─────────────────────────────────────────────

@logs_bp.route('/logs/feed', methods=['GET'])
@jwt_required()
def feed_logs():
    user, err = _require_user()
    if err:
        return err

    page, per_page = _paginate_params()
    exclude_pollers = request.args.get('exclude_pollers', '').lower() in ('1', 'true', 'yes')
    # ?raw=true opts out of the allowlist, for debugging — ADMIN ONLY.
    #
    # Without that restriction this was a way around the admin-only rule on
    # /logs/system. A supervisor is refused there with a 403, but the same rows
    # came straight back through here: 50 of them, including
    # integrations.shopify.token and integrations.meta.legacy_credentials_used.
    # The allowlist is the entire reason non-admins can be shown this feed, so
    # opting out of it has to carry the same bar as the page it mirrors.
    #
    # Ignored rather than rejected for non-admins: the feed is the Activity
    # page's main content, and a stray query param shouldn't blank it.
    raw = (request.args.get('raw', '').lower() in ('1', 'true', 'yes')
           and user.role == 'admin')

    query = Log.query

    if not raw:
        # ALLOWLIST, not a poller blocklist. Excluding '%_poller%' still left
        # the feed 84% internal engineering chatter for an admin — classifier
        # traces, analytics warnings, cache lookups — none of which anyone can
        # act on, and most of which rendered as raw log text because the
        # formatter had no case for them. This is the set of events that
        # describe something happening to a CUSTOMER, plus the faults worth
        # interrupting someone for.
        query = query.filter(Log.source.in_(ACTIVITY_SOURCES))
    elif exclude_pollers:
        query = query.filter(~Log.source.ilike('%_poller%'))

    # Role-scoped visibility. Agents only see activity for conversations
    # assigned to them (or unassigned in the human_override queue) — matching
    # the Messages access model. Conversation-less system/sync events are
    # hidden from agents. Admins/supervisors see everything.
    if user.role == 'agent':
        query = query.filter(Log.conversation_id.in_(accessible_conversation_ids(user)))

    rows = (query.order_by(Log.created_at.desc())
                 .limit(per_page).offset((page - 1) * per_page).all())

    return jsonify({
        'logs': _with_customer_handles(rows),
        'page': page,
        'per_page': per_page,
    }), 200


def _with_customer_handles(rows):
    """
    Serialise log rows, adding the customer's username wherever we know it.

    Two separate leaks were showing raw platform IDs to people:

      1. Live Activity built its sentence from `payload.user_external_id`, which
         on Instagram is an IGSID — a 16-digit number identifying the customer
         to nobody. The username sits on users.name; nothing joined to it.
      2. The System Logs tab renders `message` verbatim, and those strings had
         the ID written into them at log time ("Inbound [instagram_dm] from
         1572623687906312"). Rewriting history is not an option, so the ID is
         substituted on the way out.

    Both go through app/identity.py so the rule has one definition. Batched —
    at most two queries regardless of page size.
    """
    from app.identity import resolve_rows, humanise

    dicts = [r.to_dict() for r in rows]
    handles, id_map = resolve_rows(rows, text_fields=('message',))

    for i, d in enumerate(dicts):
        handle = handles.get(i)
        if handle:
            # `handle` is what the UI prefers; user_external_id stays put so
            # nothing that relies on the raw ID breaks.
            d['payload'] = {**(d.get('payload') or {}), 'handle': handle}
        if d.get('message'):
            d['message'] = humanise(d['message'], id_map)

    return dicts

# ─────────────────────────────────────────────
# GET /api/alerts — what is broken right now
# ─────────────────────────────────────────────
# Distinct from /logs/system, which is a raw searchable log table. This is the
# Dashboard panel: faults only, grouped, newest first.
#
# The panel used to call /logs/system with no level filter and show the last 3
# rows of ANY severity, so "System Alerts" routinely displayed things like
# "Access token obtained" and "Cache search for [...]" while 356 error rows sat
# unseen behind them. Filtering to faults and grouping by source is the whole
# point: 378 fault rows in this database collapse to 13 distinct problems.

FAULT_LEVELS = ('error', 'warning', 'warn')   # 'warn' for rows written before normalisation
ALERT_WINDOW_HOURS = 24 * 7


# Fallback only — the live value is handoff.agent_waiting_minutes in settings,
# editable on the Settings page. An agent's conversation counts as neglected
# once the customer's last message has gone this long without a human reply.
AGENT_WAITING_MINUTES = 10


@logs_bp.route('/alerts/dismiss', methods=['POST'])
@jwt_required()
def dismiss_alerts():
    """
    Acknowledge fault alerts so they stop occupying the panel.

    Marks, never deletes. The rows stay in the log table and stay searchable on
    the Logs page — this only records "somebody has seen this", per source, as
    a timestamp. A later failure from the same source is newer than the
    watermark and reappears on its own.

    Only faults can be acknowledged. The other two alert kinds — conversations
    awaiting a reply, and the unclaimed queue — are live state, not history.
    Dismissing those would hide a customer who is still waiting, so they clear
    only by the work actually being done.

    Restricted to supervisors and admins: a fault is system-wide, so one person
    acknowledging it hides it for everyone.
    """
    user, err = _require_user()
    if err:
        return err
    if user.role not in {'admin', 'supervisor'}:
        return jsonify({'error': 'Only supervisors and admins can clear alerts'}), 403

    from app.settings import get_settings, _row
    from app.models import Log as _Log

    data = request.get_json(silent=True) or {}
    sources = data.get('sources')
    clear_all = bool(data.get('all'))

    if not clear_all and not sources:
        return jsonify({'error': "Pass 'sources': [...] or 'all': true"}), 400

    if clear_all:
        # Everything currently faulting inside the alert window.
        cutoff = datetime.utcnow() - timedelta(hours=ALERT_WINDOW_HOURS)
        sources = [r[0] for r in db.session.query(_Log.source)
                   .filter(_Log.level.in_(FAULT_LEVELS))
                   .filter(_Log.created_at >= cutoff)
                   .distinct().all()]

    now = datetime.utcnow().isoformat()
    row = _row()
    data_blob = dict(row.data or {})
    alerts_cfg = dict(data_blob.get('alerts') or {})
    acked = dict(alerts_cfg.get('acknowledged') or {})
    for src in sources:
        if src:
            acked[str(src)] = now
    alerts_cfg['acknowledged'] = acked
    data_blob['alerts'] = alerts_cfg
    row.data = data_blob
    row.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(user.id, 'dismiss_alerts', resource_type='alerts',
              changes={'sources': list(sources)[:20], 'count': len(sources)})

    return jsonify({'dismissed': len(sources), 'sources': list(sources)}), 200


@logs_bp.route('/alerts', methods=['GET'])
@jwt_required()
def alerts():
    """
    What needs attention, scoped to who's asking.

    Every role gets a panel — this used to be admin-only, so agents saw a
    permanently forbidden box taking up prime dashboard space. An agent can
    self-claim from the queue and owns their own conversations, so there is
    plenty they can act on; it's system-level faults that aren't theirs.
    """
    user, err = _require_user()
    if err:
        return err

    from datetime import timedelta
    from sqlalchemy import func
    hours = request.args.get('hours', default=ALERT_WINDOW_HOURS, type=int)
    limit = request.args.get('limit', default=6, type=int)
    cutoff = datetime.utcnow() - timedelta(hours=max(1, hours))
    is_agent = user.role == 'agent'

    out = []

    # ── Your conversations, waiting on a human reply ─────────────────────
    # Top of an agent's list: it's their own work, and the customer is waiting.
    if is_agent:
        try:
            from app.models import Conversation, Message
            from app.settings import get_section
            wait_mins = int(get_section("handoff").get(
                "agent_waiting_minutes", AGENT_WAITING_MINUTES))
            waiting_cutoff = datetime.utcnow() - timedelta(minutes=wait_mins)
            mine = (Conversation.query
                    .filter(Conversation.assigned_to == user.id)
                    .filter(Conversation.status != 'resolved')
                    .filter(Conversation.last_message_at < waiting_cutoff)
                    .order_by(Conversation.last_message_at.asc())
                    .limit(50).all())
            stale = []
            for conv in mine:
                last = (Message.query
                        .filter(Message.conversation_id == conv.id)
                        .order_by(Message.created_at.desc())
                        .first())
                # Newest message being inbound means the ball is in our court.
                if last is not None and last.direction == 'inbound':
                    stale.append(conv)
            if stale:
                oldest = stale[0]
                mins = int((datetime.utcnow() - oldest.last_message_at).total_seconds() // 60)
                out.append({
                    'kind': 'awaiting_reply',
                    'severity': 'error' if mins >= 60 else 'warning',
                    'title': f"{len(stale)} conversation{'s' if len(stale) != 1 else ''} awaiting your reply",
                    'detail': f"longest waiting {mins} min",
                    'count': len(stale),
                    'last_seen': None,
                    'href': '/messages?assigned_to=me',
                })
        except Exception as e:
            log_event("warn", "logs.alerts_awaiting_failed", str(e))

    # ── Conversations waiting with nobody on them ────────────────────────
    # Sits above log faults because it's the one with a customer attached.
    # Shown to agents too — they can self-claim, so it's arguably more
    # actionable for them than for a supervisor.
    try:
        from app.assignment import find_unclaimed
        waiting = find_unclaimed()
        if waiting:
            longest = waiting[0][1]
            out.append({
                'kind': 'queue',
                'severity': 'error' if longest >= 60 else 'warning',
                'title': (f"{len(waiting)} conversation{'s' if len(waiting) != 1 else ''} "
                          + ("waiting to be picked up" if is_agent else "waiting, unassigned")),
                'detail': f"longest has waited {longest} min",
                'count': len(waiting),
                'last_seen': None,
                'href': '/messages?assigned_to=unassigned',
            })
    except Exception as e:
        log_event("warn", "logs.alerts_queue_failed", str(e))

    # ── Faults from the log, grouped so 300 repeats are one line ─────────
    # Agents get only faults attached to a conversation they can access — a
    # failed Shopify sync isn't theirs to fix, but the AI failing to answer
    # their customer certainly is.
    try:
        def _fault_scope(q):
            if is_agent:
                return q.filter(Log.conversation_id.in_(accessible_conversation_ids(user)))
            return q

        groups = (_fault_scope(
                      db.session.query(
                          Log.source,
                          func.count(Log.id).label('n'),
                          func.max(Log.created_at).label('newest'),
                          func.max(Log.level).label('level'),
                      )
                      .filter(Log.level.in_(FAULT_LEVELS))
                      .filter(Log.created_at >= cutoff))
                  .group_by(Log.source)
                  .order_by(func.max(Log.created_at).desc())
                  .all())

        # Newest message per source, for the human-readable line.
        newest_msg = {}
        if groups:
            for row in (_fault_scope(
                            Log.query
                            .filter(Log.source.in_([g.source for g in groups]))
                            .filter(Log.level.in_(FAULT_LEVELS))
                            .filter(Log.created_at >= cutoff))
                        .order_by(Log.created_at.desc())
                        .all()):
                newest_msg.setdefault(row.source, row)

        # Acknowledged sources drop out until they fail again. Nothing is
        # deleted — the log rows are the audit trail, and a panel that clears
        # itself by destroying evidence is worse than a noisy panel.
        acked = {}
        try:
            from app.settings import get_section
            acked = get_section("alerts").get("acknowledged") or {}
        except Exception:
            pass

        for g in groups:
            ack_at = acked.get(g.source)
            if ack_at:
                try:
                    if g.newest <= datetime.fromisoformat(ack_at):
                        continue
                except (TypeError, ValueError):
                    pass
            row = newest_msg.get(g.source)
            level = 'error' if (g.level or '').lower() == 'error' else 'warning'
            out.append({
                'kind': 'fault',
                'severity': level,
                'source': g.source,
                'title': (row.message if row else g.source)[:160],
                'detail': None,
                'count': int(g.n),
                'last_seen': g.newest.isoformat() if g.newest else None,
                'conversation_id': row.conversation_id if row else None,
            })
    except Exception as e:
        log_event("warn", "logs.alerts_faults_failed", str(e))

    # Errors before warnings; within a severity, most recent first, with the
    # live queue alert (no last_seen) ahead of dated log faults. The old panel
    # ranked on recency alone, so a fresh warning outranked an active outage.
    # Two passes rather than one clever key — Python's sort is stable, so the
    # second ordering wins and the first survives as the tiebreak.
    out.sort(key=lambda a: a['last_seen'] or '', reverse=True)
    out.sort(key=lambda a: (0 if a['severity'] == 'error' else 1,
                            0 if a['last_seen'] is None else 1))

    return jsonify({
        'alerts': out[:limit],
        'total': len(out),
        'window_hours': hours,
    }), 200
