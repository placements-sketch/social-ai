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
# Ordering, so a coalesced notification can only ever get louder, never quieter.
SEVERITY_RANK = {'info': 0, 'warning': 1, 'urgent': 2}

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


# ── Urgent emails are sent AFTER the transaction commits ─────────────────────
# create_notification() documents that "the caller is responsible for the
# commit", but the email was being sent inside it — before that commit. If the
# caller's transaction then rolled back, the notification never existed and the
# recipient had already been emailed about it. Verified: 1 email sent, 0 rows
# saved.
#
# Emails are now queued on the session and flushed once the commit succeeds,
# and dropped on rollback. Nobody gets paged about something that didn't happen.
_PENDING_EMAILS_KEY = '_pending_urgent_emails'
_commit_hook_installed = False


def _install_commit_hook():
    global _commit_hook_installed
    if _commit_hook_installed:
        return
    from sqlalchemy import event

    @event.listens_for(db.session, 'after_commit')
    def _flush_pending_urgent_emails(session):
        # No database access in here. after_commit runs with the session in
        # 'committed' state, where SQLAlchemy refuses to emit further SQL —
        # looking the recipient up here failed with "this session is in
        # 'committed' state". Worse, it failed *silently*: the exception was
        # caught and logged as a warning, so urgent emails would simply stop.
        # Everything the send needs is resolved before the commit instead.
        for msg in session.info.pop(_PENDING_EMAILS_KEY, []):
            try:
                send_email(msg['to'], msg['subject'], msg['html'], msg['text'])
            except Exception as e:
                # The in-app notification is the source of truth and it is
                # already committed; a mail failure must not undo it.
                log_event('warning', 'notifications.email_failed', str(e))

    @event.listens_for(db.session, 'after_rollback')
    def _drop_pending_urgent_emails(session):
        session.info.pop(_PENDING_EMAILS_KEY, None)

    _commit_hook_installed = True


def _queue_urgent_email(user_id, title, body):
    """
    Render the email now — while the session can still be queried — and hold it
    until the caller's commit succeeds.
    """
    user = AuthUser.query.get(user_id)
    if not user or not user.email or user.status != 'active':
        return

    # Resolve platform ids to handles before rendering.
    #
    # Titles are composed from User.handle, which falls back to external_id when
    # the username isn't known yet — so an urgent email could read "New message
    # from 1049159518028579". The in-app views already substitute these on the
    # way out; the email is rendered here and was missing it, which is the one
    # place it matters most: you read it away from the app with no way to look
    # the number up.
    try:
        from app.identity import candidate_ids, handles_for_external_ids, humanise
        id_map = handles_for_external_ids(candidate_ids(title, body))
        title = humanise(title, id_map)
        body = humanise(body, id_map)
    except Exception as e:
        # A lookup failure must not cost the alert — a numeric id in the
        # subject line still beats no email at all.
        log_event('warning', 'notifications.handle_resolve_failed', str(e)[:160])

    _install_commit_hook()
    db.session.info.setdefault(_PENDING_EMAILS_KEY, []).append({
        'to': user.email,
        'subject': f"[Urgent] {title}",
        'html': _urgent_email_html(user.full_name, title, body),
        'text': _urgent_email_text(user.full_name, title, body),
    })


def _dashboard_url() -> str:
    """
    Where the urgent email's button should point.

    FRONTEND_URL is not set in this environment, and the old code fell back to
    href="#" — so the one action in an urgent email did nothing when clicked.
    PUBLIC_BASE_URL is already used for webhook URLs and points at the same
    deployment, so it is a sound second choice; if neither is set we drop the
    button entirely rather than render a dead one.
    """
    # FRONTEND_BASE_URL is the name this deployment actually uses — checking
    # only FRONTEND_URL is why this fell through to the API host.
    for var in ('FRONTEND_URL', 'FRONTEND_BASE_URL', 'APP_BASE_URL', 'PUBLIC_BASE_URL'):
        val = (os.getenv(var) or '').strip().rstrip('/')
        if val:
            return val
    return ''


def _urgent_email_html(name, title, body):
    # Escaped: titles and bodies carry customer-supplied text (usernames,
    # message excerpts). Interpolating those raw into HTML lets a customer's
    # message rewrite the email that goes to staff.
    from html import escape
    safe_title = escape(title or '')
    safe_body = escape(body or '')
    safe_name = escape(name or 'there')

    url = _dashboard_url()
    button = (
        f'<p style="margin:24px 0"><a href="{url}/activity"'
        ' style="background:#ff5900;color:#fff;text-decoration:none;font-weight:bold;font-size:14px;'
        'padding:12px 22px;border-radius:8px;display:inline-block">Open dashboard</a></p>'
    ) if url else ''

    return (
        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:24px">'
        '<div style="background:#fff4ed;border-left:4px solid #ff5900;padding:12px 16px;border-radius:6px;margin-bottom:16px">'
        '<span style="color:#ff5900;font-size:12px;font-weight:bold;text-transform:uppercase;letter-spacing:.05em">Urgent</span>'
        '</div>'
        f'<h2 style="color:#1a1a2e;margin:0 0 8px;font-size:18px">{safe_title}</h2>'
        + (f'<p style="color:#555;font-size:14px;line-height:1.6">{safe_body}</p>' if body else '')
        + button +
        f'<p style="color:#bbb;font-size:11px;margin-top:24px">Hi {safe_name} — you\'re getting this because '
        'it needs prompt attention. Shop Zetu · Social AI Assistant</p></div>'
    )


def _urgent_email_text(name, title, body):
    lines = [f"[URGENT] {title}"]
    if body:
        lines.append("")
        lines.append(body)
    lines.append("")
    url = _dashboard_url()
    lines.append(f"Open your dashboard to respond: {url}/activity" if url
                 else "Open your dashboard to respond.")
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

            # Coalescing keys on type + resource, NOT severity — so a situation
            # that started as 'info' and escalated to 'urgent' used to merge
            # into the info row, keep severity 'info', and send no email. The
            # event got quieter precisely as it got worse. Severity now only
            # ever ratchets up, and crossing into urgent sends the mail.
            if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(existing.severity, 0):
                existing.severity = sev
                if sev == 'urgent':
                    _queue_urgent_email(user_id, title, body)
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

    # Urgent notifications also go out by email — queued here, sent once the
    # caller's transaction actually commits.
    if sev == 'urgent':
        _queue_urgent_email(user_id, title, body)

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

    # Unread is a STATE, not a window. This count used to carry the same
    # created_at cutoff as the list, so the bell showed "unread in the last 7
    # days" while calling itself unread: on this database the admin's badge read
    # 7 while 17 were genuinely unread, and the oldest was an escalation 53 days
    # old that no longer appeared anywhere. Mark-all-read has never been
    # windowed — it clears every unread row — so the badge was also disagreeing
    # with the button meant to clear it.
    unread_total = (Notification.query
                    .filter(Notification.user_id == uid)
                    .filter(Notification.read_at.is_(None))
                    .count())
    unread_in_window = (Notification.query
                        .filter(Notification.user_id == uid)
                        .filter(Notification.read_at.is_(None))
                        .filter(Notification.created_at >= cutoff)
                        .count())

    # Notification titles are composed from User.handle, which falls back to
    # external_id when we don't yet know the username — so "New message from
    # 1049159518028579" got written into the row permanently. Usernames usually
    # arrive later (thread creation, a profile fetch), so the ID is swapped for
    # the name on the way out and old notifications start reading properly.
    # Only ids that really are customer external_ids are touched.
    from app.identity import resolve_notifications, humanise
    id_map = resolve_notifications(rows)

    serialised = []
    for n in rows:
        d = n.to_dict()
        d['title'] = humanise(d.get('title'), id_map)
        d['body'] = humanise(d.get('body'), id_map)
        serialised.append(d)

    return jsonify({
        'notifications': serialised,
        # The badge number. True unread, no time limit.
        'unread_count': unread_total,
        # How many of those the caller is actually looking at, so the page can
        # say "10 older ones aren't shown" instead of silently dropping them.
        'unread_in_window': unread_in_window,
        'unread_outside_window': max(0, unread_total - unread_in_window),
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