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

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models import AuthUser, Conversation, Message, User
from app.utils.logger import log_event
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

def _unread_counts_for_user(user_id, conversations):
    """
    Per-user unread: for each conversation, how many INBOUND messages exist
    after this user's last-read position. Returns {conversation_id: count}.
    One query, counted DB-side.
    """
    if not conversations:
        return {}
    from sqlalchemy import func
    from app.models import Message, ConversationRead

    conv_ids = [c.id for c in conversations]
    reads_sq = (db.session.query(
                    ConversationRead.conversation_id.label('cid'),
                    ConversationRead.last_read_message_id.label('lr'))
                .filter(ConversationRead.user_id == user_id)
                .subquery())

    rows = (db.session.query(Message.conversation_id, func.count(Message.id))
            .outerjoin(reads_sq, reads_sq.c.cid == Message.conversation_id)
            .filter(Message.conversation_id.in_(conv_ids),
                    Message.direction == 'inbound',
                    Message.id > func.coalesce(reads_sq.c.lr, 0))
            .group_by(Message.conversation_id)
            .all())
    return dict(rows)


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


# The four inbox filter chips, expressed once as SQL.
#
# These are compound conditions — a bucket depends on status AND assigned_to
# AND ai_enabled together — so they cannot be expressed with the plain ?status=
# parameter the list endpoint already had. Without a server-side equivalent the
# frontend filtered the page it happened to have loaded, while the chip counted
# the whole inbox, and the two disagreed the moment the inbox exceeded one page:
# "Resolved 27" over a list showing 11, "Unclaimed 2" over an empty list.
#
# Defined here and used by BOTH the counts endpoint and the list endpoint, so
# the number on a chip and the rows behind it are answers to the same question.
def _match_snippet(text: str, term: str, width: int = 90) -> str:
    """
    A window of `text` centred on the first occurrence of `term`.

    Searching message bodies is only half the feature. Without this, a search
    for "refund" surfaces a row whose visible line is the LAST message —
    "ok thanks!" — with nothing on screen explaining why it matched. The agent
    then has to open every result to find out which one they wanted.
    """
    if not text:
        return ''
    body = text.strip()
    pos = body.lower().find(term.lower())
    if pos == -1:
        return body[:width] + ('…' if len(body) > width else '')

    pad = max(0, (width - len(term)) // 2)
    start = max(0, pos - pad)
    end = min(len(body), start + width)
    out = body[start:end]
    return ('…' if start > 0 else '') + out + ('…' if end < len(body) else '')


def _ai_globally_enabled() -> bool:
    """The master switch, read defensively — an unreadable setting must not be
    reported as 'the AI is fine'."""
    try:
        from app.settings import get_section
        return bool(get_section("ai").get("enabled", True))
    except Exception:
        return True


INBOX_BUCKETS = ('unclaimed', 'human', 'ai', 'resolved')


def _channel_availability() -> dict:
    """
    {platform: enabled} folded from the channels table — instagram is on when
    either of its two surfaces is.

    Read defensively: an unreadable channels table must not blank the inbox
    filters, so every platform falls back to "enabled" and the UI simply stops
    offering its setup hint.
    """
    try:
        from app.models import Channel
        out = {}
        for c in Channel.query.all():
            platform = (c.channel or '').split('_')[0]
            if not platform:
                continue
            out[platform] = out.get(platform, False) or bool(c.enabled)
        return out
    except Exception as e:
        log_event('warning', 'messages.channel_availability_failed', str(e)[:160])
        return {}


def _apply_inbox_filters(query, current_user, skip=()):
    """
    Narrow `query` by the inbox filters on the current request.

    ONE definition, used by both the list and the counts, because they were two:
    the list filtered on platform/surface/search and the counts did not, so
    selecting Instagram narrowed the list to 46 while every chip above it went
    on describing all 69. A count that doesn't answer the same question as the
    list it sits above is worse than no count.

    `skip` names facets to leave out. Facet counts are computed with every
    OTHER filter applied but not their own — otherwise selecting Instagram
    would zero the Facebook chip and you could never click your way back out.
    """
    channel = request.args.get('channel', type=str)
    platform = request.args.get('platform', type=str)     # instagram | facebook | …
    surface = request.args.get('surface', type=str)       # dm | comment
    status = request.args.get('status', type=str)
    bucket = request.args.get('bucket', type=str)
    assigned_to = request.args.get('assigned_to', type=str)
    search = request.args.get('search', type=str)

    # `channel` is a compound column — instagram_dm, instagram_comment — so
    # filtering on it forced platform and surface together: you could ask for
    # "Instagram DMs" but never "everything from Instagram" or "every comment,
    # wherever it came from". Those are the two things you actually want when
    # triaging. `channel` still works untouched for anything already passing it.
    if 'channel' not in skip and channel and channel != 'all':
        query = query.filter(Conversation.channel == channel)

    if 'platform' not in skip and platform and platform != 'all':
        # instagram -> instagram_dm, instagram_comment
        query = query.filter(Conversation.channel.like(f'{platform}\\_%', escape='\\'))

    if 'surface' not in skip and surface and surface != 'all':
        # dm -> instagram_dm, facebook_dm
        query = query.filter(Conversation.channel.like(f'%\\_{surface}', escape='\\'))

    if 'status' not in skip and status and status != 'all':
        query = query.filter(Conversation.status == status)

    # Inbox filter chips. Applied in SQL so the list matches the chip's count
    # rather than showing whichever members of the bucket happened to land in
    # the page already loaded.
    if 'bucket' not in skip and bucket in INBOX_BUCKETS:
        query = _bucket_filter(query, bucket)

    # Optional filters for supervisor/admin dashboards
    if 'assigned_to' not in skip:
        if assigned_to == 'me' and current_user:
            query = query.filter(Conversation.assigned_to == current_user.id)
        elif assigned_to == 'unassigned':
            query = query.filter(Conversation.assigned_to.is_(None))
        elif assigned_to and assigned_to.isdigit():
            query = query.filter(Conversation.assigned_to == int(assigned_to))

    term = (search or '').strip()
    if 'search' not in skip and term:
        like = f"%{term}%"
        # A correlated EXISTS over messages, so a conversation matches on
        # anything ever said in it — not just whichever line happens to be
        # sitting in Conversation.last_message. Searching "refund" used to
        # return nothing unless "refund" was the most recent message, which
        # made the box feel broken on the one page where search matters most.
        # EXISTS rather than a join: a join would emit one row per matching
        # message and silently multiply the conversation across the results.
        said_in_thread = (
            Message.query
            .filter(Message.conversation_id == Conversation.id,
                    Message.content.ilike(like))
            .exists()
        )
        query = query.join(User, Conversation.user_id == User.id).filter(
            db.or_(
                Conversation.last_message.ilike(like),
                User.name.ilike(like),
                User.external_id.ilike(like),
                said_in_thread,
            )
        )

    return query


def _bucket_filter(query, bucket):
    """Narrow `query` to one inbox bucket. Unknown bucket → unchanged query."""
    if bucket == 'unclaimed':
        return query.filter(Conversation.status != 'resolved',
                            Conversation.assigned_to.is_(None),
                            Conversation.ai_enabled.is_(False))
    if bucket == 'human':
        return query.filter(Conversation.status != 'resolved',
                            Conversation.assigned_to.isnot(None),
                            Conversation.ai_enabled.is_(False))
    if bucket == 'ai':
        return query.filter(Conversation.status != 'resolved',
                            Conversation.ai_enabled.is_(True))
    if bucket == 'resolved':
        return query.filter(Conversation.status == 'resolved')
    return query


@messages_bp.route('/conversations/counts', methods=['GET'])
@jwt_required()
def conversation_counts():
    """
    Counts for the sidebar badge. Same role scoping as the inbox list.

    Exists because the badge was fetching 100 full conversation records every
    15 seconds — ~24 KB per poll for an admin — purely to call .filter().length
    on them. Worse, it silently capped: MAX_PER_PAGE is 100, so past 100
    conversations the badge would quietly under-report forever. A COUNT in the
    database has neither problem.
    """
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

    # Two different questions, deliberately. An agent's badge means "waiting on
    # a person" — the AI handles everything else and they needn't see it. An
    # admin's means "unread". Resolved threads are excluded from both: a closed
    # conversation with an unread message is not outstanding work.
    open_q = query.filter(Conversation.status != 'resolved')
    open_convs = open_q.all()

    # Unread is PER USER, from each person's own read position — the same
    # source the inbox list uses. Reading Conversation.unread_count instead
    # would be a different number entirely: that column is a shared counter
    # that mark_read never touches, so the badge would keep claiming unread
    # mail the list had already shown as read.
    unread_map = _unread_counts_for_user(current_user.id, open_convs) if current_user else {}

    # Everything above this line is the SIDEBAR badge: deliberately unfiltered,
    # because "you have work waiting" must not change when someone clicks a chip
    # inside the inbox. Everything below is the inbox's own facet counts, which
    # must track the filters exactly. Two different questions off one endpoint.
    #
    # Each facet is counted with every other active filter applied but its own
    # excluded — so with Instagram selected the status chips describe the 46
    # Instagram threads, while the platform chips still show what's on Facebook
    # so you can click over to it.
    status_scope = _apply_inbox_filters(query, current_user, skip=('bucket',))
    platform_scope = _apply_inbox_filters(query, current_user, skip=('platform', 'channel'))
    surface_scope = _apply_inbox_filters(query, current_user, skip=('surface', 'channel'))

    def _by_channel(scope):
        return dict(
            scope.with_entities(Conversation.channel, db.func.count(Conversation.id))
                 .group_by(Conversation.channel).all()
        )

    # Status buckets for the inbox filter chips. Computed server-side over the
    # WHOLE scoped set: the chips used to count whatever the list had loaded,
    # which is one page of 20, so with 46 conversations "Resolved" read 11 when
    # the real answer was 27. A count that depends on how far you've scrolled
    # is worse than no count.
    return jsonify({
        'needs_human': sum(1 for c in open_convs if not c.ai_enabled),
        'unread':      sum(1 for c in open_convs if unread_map.get(c.id, 0) > 0),
        'unassigned':  sum(1 for c in open_convs
                           if c.assigned_to is None and c.status == 'human_override'),
        # Counted with the same _bucket_filter the list endpoint applies, so a
        # chip's number and the rows it reveals can never disagree. They used
        # to be two separate implementations — Python sums here, no filter at
        # all there — which is precisely how they drifted.
        'by_status': {k: _bucket_filter(status_scope, k).count() for k in INBOX_BUCKETS},
        # Per-channel totals for the platform and surface chips, each from ONE
        # grouped query rather than a round trip per chip. The client folds
        # instagram_dm + instagram_comment into "Instagram" and the two _dm
        # values into "DMs".
        #
        # Two scopes, not one, because they are two questions: the platform row
        # must respect the chosen surface (Comments selected → Instagram shows
        # its 8 comments) and the surface row must respect the chosen platform
        # (Instagram selected → 38 DMs / 8 comments, not 50 / 19). A single
        # shared dict cannot answer both once either filter is live.
        'by_channel': _by_channel(platform_scope),
        'by_surface_channel': _by_channel(surface_scope),
        # Which channels exist and which are switched on. The inbox needs this
        # to tell "connected, nothing yet" apart from "not connected" — two
        # states that both show an empty list and want opposite responses
        # (wait vs go and set it up). Included here rather than read from
        # /api/channels because that endpoint is admin+supervisor only, and an
        # agent looking at an empty inbox deserves the same explanation.
        'channels': _channel_availability(),

        # The global kill switch is a settings flag checked at reply time — it
        # never touches conversations.ai_enabled. So while it is off, every
        # conversation in the 'ai' bucket still claims the AI is handling it,
        # and nothing is. They are not in 'unclaimed' either (that requires
        # ai_enabled = false), so no agent is shown them. The bucket cannot be
        # redefined without making the counts depend on a setting, so the flag
        # travels with the counts and the label changes instead.
        'ai_globally_off': not _ai_globally_enabled(),
        'ai_auto_paused': (query
                           .filter(Conversation.status != 'resolved',
                                   Conversation.ai_auto_paused_at.isnot(None))
                           .count()),
    }), 200


@messages_bp.route('/conversations', methods=['GET'])
@jwt_required()
def list_conversations():
    """List conversations for the inbox."""
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=DEFAULT_PER_PAGE, type=int)

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

    # Platform, surface, status, bucket, assignee and search — see
    # _apply_inbox_filters, which the counts endpoint calls with the same
    # request so the chips above the list can never describe a different set
    # from the list itself.
    query = _apply_inbox_filters(query, current_user)

    total = query.count()

    conversations = (
        query.order_by(Conversation.last_message_at.desc().nullslast())
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    # Per-user unread: override the shared counter with THIS user's own count,
    # so an admin opening a chat doesn't clear an agent's unread and vice versa.
    unread_map = _unread_counts_for_user(current_user.id, conversations) if current_user else {}

    # When the match came from inside the thread, hand back the line it matched
    # on so the row can show it. DISTINCT ON gives exactly one message per
    # conversation — the most recent match — in a single query for the page,
    # rather than one query per row.
    snippet_map = {}
    term = (request.args.get('search', type=str) or '').strip()
    if term and conversations:
        like = f"%{term}%"
        ids = [c.id for c in conversations]
        rows = (
            db.session.query(Message.conversation_id, Message.content, Message.direction)
            .filter(Message.conversation_id.in_(ids), Message.content.ilike(like))
            .distinct(Message.conversation_id)
            .order_by(Message.conversation_id, Message.created_at.desc())
            .all()
        )
        snippet_map = {r[0]: (r[1], r[2]) for r in rows}

    conv_dicts = []
    for c in conversations:
        d = c.to_dict(include_messages=False)
        d['unread_count'] = unread_map.get(c.id, 0)
        hit = snippet_map.get(c.id)
        # Only worth showing when the visible line doesn't already contain the
        # term — otherwise the row would say the same thing twice.
        if hit and term.lower() not in (c.last_message or '').lower():
            d['match_snippet'] = _match_snippet(hit[0], term)
            d['match_from'] = 'customer' if hit[1] == 'inbound' else 'us'
        conv_dicts.append(d)

    return jsonify({
        'conversations': conv_dicts,
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

    # Everything else this customer has talked to us about, so a returning
    # customer never reads as a stranger. Conversations fork once a thread has
    # been resolved and enough time has passed, which is correct — but without
    # this the agent has no way to see the relationship behind the fork.
    payload = conv.to_dict(include_messages=True)
    try:
        earlier = (Conversation.query
                   .filter(Conversation.user_id == conv.user_id,
                           Conversation.id != conv.id)
                   .order_by(Conversation.last_message_at.desc().nullslast())
                   .limit(10).all())
        payload['earlier_conversations'] = [{
            'id': c.id,
            'channel': c.channel,
            'status': c.status,
            'last_message_at': c.last_message_at.isoformat() if c.last_message_at else None,
            'last_message': (c.last_message or '')[:80],
            'message_count': Message.query.filter_by(conversation_id=c.id).count(),
        } for c in earlier if _agent_can_access_conversation(current_user, c)]
    except Exception as e:
        log_event("warn", "messages.earlier_conversations_failed", str(e))
        payload['earlier_conversations'] = []

    return jsonify({'conversation': payload}), 200


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
        .filter((Message.sender != 'ai_pending') | (Message.sender.is_(None)))
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
    # Which inbound message this is a reply to, when the agent picked one.
    reply_to_message_id = data.get('reply_to_message_id')
    if not content:
        return jsonify({'error': 'Message content is required'}), 400

    sender = (data.get('sender') or 'human').lower()
    if sender not in VALID_SENDERS:
        return jsonify({'error': f'Invalid sender. Must be one of: {", ".join(sorted(VALID_SENDERS))}'}), 400

    now = datetime.utcnow()

    # Idempotency: an identical outbound on this conversation within the last
    # few seconds is a duplicate submit, not a genuine repeat. Return the
    # existing row instead of creating a second one.
    recent_dupe = (Message.query
        .filter_by(conversation_id=conv.id, direction='outbound', content=content)
        .filter(Message.created_at >= now - timedelta(seconds=10))
        .first())
    if recent_dupe:
        return jsonify({
            'message': recent_dupe.to_dict(),
            'conversation': conv.to_dict(include_messages=False),
            'delivered': True,
            'deduped': True,
        }), 201

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
        was_resolved = conv.status == 'resolved'
        conv.status = 'human_override'
        # Replying re-opens a resolved conversation, so the resolution stamps
        # have to go with it. Leaving them set produced a conversation that was
        # 'human_override' but still carried resolved_at — and the per-agent
        # "resolved in window" metric counts that column, so a re-opened
        # conversation stayed on the books as resolved.
        if was_resolved:
            conv.resolved_at = None
            conv.resolved_by = None
        if conv.ai_enabled:                          # only stamp the transition
            conv.ai_disabled_at = now
        conv.ai_enabled = False                      # human takes over → pause Claude
        if conv.assigned_to is None:                 # and claim it, so it's not falsely "In queue"
            conv.assigned_to = current_user.id
            conv.assigned_at = now
            conv.assigned_by = current_user.id
    conv.unread_count = 0
    conv.updated_at = now

    db.session.commit()

    delivered = True   # flipped to False if the channel dispatch fails

    # Dispatch the reply to the customer via the channel API (IG/FB/WA).
    # Same path the AI uses. Failures are logged but don't roll back the DB —
    # the agent's reply is still recorded, and they can retry from the UI.
    try:
        from app.services import _dispatch_reply
        customer = conv.user
        if customer:
            # For comment replies, we need the comment_id of the LAST inbound
            # message in this conversation — that's the comment we're replying to.
            comment_ext_id = None
            if conv.channel.endswith("_comment"):
                # Thread under the comment the agent chose, when they chose
                # one. The UI has a "reply to" affordance that sets a specific
                # message, but its id was never sent to the server — only the
                # quoted text got prepended to the body. So picking the first
                # of three comments still posted the reply under the newest
                # one, and the quote was the only hint of what was meant.
                picked = None
                if reply_to_message_id:
                    picked = (Message.query
                              .filter_by(id=reply_to_message_id,
                                         conversation_id=conv.id,
                                         direction='inbound')
                              .first())
                if picked and picked.external_id:
                    comment_ext_id = picked.external_id
                else:
                    # id as tiebreaker: comments arriving in the same burst
                    # share a created_at to the microsecond, and ordering by
                    # timestamp alone then returns an arbitrary row — measured
                    # returning the OLDEST of three. A reply threading under a
                    # random comment is worse than one threading under the
                    # newest.
                    last_inbound = (Message.query
                        .filter_by(conversation_id=conv.id, direction='inbound')
                        .order_by(Message.created_at.desc(), Message.id.desc())
                        .first())
                    if last_inbound:
                        comment_ext_id = last_inbound.external_id

            new_ext_id = _dispatch_reply(
                channel=conv.channel,
                user_id=customer.external_id,
                reply=content,
                comment_external_id=comment_ext_id,
            )
            if new_ext_id:
                reply.external_id = new_ext_id
                db.session.commit()
            else:
                # _dispatch_reply returns None on failure without raising, so
                # the except below never fires. Without this the agent sees a
                # sent-looking message the customer never received.
                delivered = False
                log_event("error", "messages.send_reply.not_delivered",
                          f"Manual reply for conv {conv.id} was NOT delivered to the channel",
                          payload={"conversation_id": conv.id, "channel": conv.channel},
                          conversation_id=conv.id)
    except Exception as e:
        delivered = False
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
        'delivered': delivered,
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

    # If we just resolved this conversation, notify supervisors so they
    # can track team output. Re-opening or other status changes are noisy
    # — only notify on the active resolution.
    if changes.get('status') == 'resolved':
        try:
            from app.notifications import notify_supervisors
            handle = conv.user.external_id if conv.user else 'a customer'
            channel_label = conv.channel.replace('_', ' ')
            notify_supervisors(
                type_='conversation_resolved',
                title=f"Resolved: {handle}",
                body=f"{current_user.full_name} resolved this {channel_label} conversation",
                severity='info',
                resource_type='conversation',
                resource_id=conv.id,
                actor_id=current_user.id,
                coalesce=False,  # each resolution is a discrete event worth seeing
            )
        except Exception as e:
                log_event("error", "messages.notify_resolution_fail",
                      f"notify_supervisors failed: {e}",
                      payload={"conversation_id": conv.id, "error": str(e)},
                      conversation_id=conv.id)

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

    # Turning AI on for one conversation while the master switch is off used to
    # succeed and do real damage. services.py refuses to generate a reply while
    # the switch is off, but _bucket_filter files any ai_enabled conversation
    # under "AI" — so the chat left both human queues, no AI reply was ever
    # possible, and the customer sat waiting on nobody. Proven end to end:
    # bucket went from ['human'] to ['ai'] with the switch off.
    #
    # Refused for every role, not just agents. This is not a permission
    # question — the action cannot work for an admin either, and an admin who
    # wants AI back has a switch that actually does something.
    if bool(data['ai_enabled']) and not conv.ai_enabled and not _ai_globally_enabled():
        return jsonify({
            'error': 'Automated replies are switched off for the whole '
                     'organisation, so AI cannot take this conversation. '
                     'An admin can turn them back on in Settings.',
            'reason': 'ai_globally_off',
        }), 409

    # Someone has made a deliberate decision about this one conversation, so it
    # is no longer "whatever the global switch did to it". Clearing the mark
    # keeps a later global restore from overriding a person's explicit choice.
    conv.ai_auto_paused_at = None

    now = datetime.utcnow()
    was_enabled = conv.ai_enabled
    conv.ai_enabled = bool(data['ai_enabled'])
    if conv.ai_enabled:
        # AI taking back over → clear the stale handoff state so the
        # conversation returns to normal AI-handled, not half-escalated.
        conv.handoff_reason = None
        conv.escalated_at = None
        conv.ai_disabled_at = None
        if conv.status == 'human_override':
            conv.status = 'active'
    else:
        # Human taking over manually via the toggle → mark it handed over,
        # consistent with how a manual reply flips the conversation.
        if was_enabled:                 # only stamp the transition, not a re-save
            conv.ai_disabled_at = now
        if conv.status == 'active':
            conv.status = 'human_override'
    conv.updated_at = now
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

    # Record THIS user's read position instead of zeroing a shared counter —
    # so one person opening the chat doesn't clear everyone else's unread.
    from sqlalchemy import func
    from app.models import Message, ConversationRead
    latest_id = db.session.query(func.max(Message.id)).filter(
        Message.conversation_id == conv.id).scalar() or 0
    read = ConversationRead.query.filter_by(
        user_id=current_user.id, conversation_id=conv.id).first()
    if read is None:
        read = ConversationRead(user_id=current_user.id, conversation_id=conv.id)
        db.session.add(read)
    read.last_read_message_id = latest_id
    read.updated_at = datetime.utcnow()
    conv.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'conversation': conv.to_dict(include_messages=False)}), 200


@messages_bp.route('/messages/<int:message_id>', methods=['DELETE'])
@jwt_required()
def delete_message(message_id):
    """
    Delete a message: unsends from IG (if outbound and within 24h)
    and removes from our DB. Soft-fails the IG unsend — DB delete still goes through.
    """
    from app.integrations.meta import unsend_instagram_message, delete_instagram_comment

    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    msg = Message.query.get(message_id)
    if not msg:
        return jsonify({'error': 'Message not found'}), 404

    # Only allow deleting outbound messages (your own sent replies)
    if msg.direction != 'outbound':
        return jsonify({'error': 'Can only delete outbound messages'}), 403

    conv = Conversation.query.get(msg.conversation_id)

    # AUTHORISATION. This endpoint takes a message id, not a conversation id,
    # so it skipped the conversation-level check every other route in this file
    # performs — an agent could delete ANY outbound message in the system,
    # including in another agent's conversations, and it unsends from the
    # customer's Instagram on the way. Verified exploitable before this guard.
    if conv and not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

    # Try to unsend/delete from IG first if it's an IG message with an external_id
    ig_unsent = False
    if msg.external_id:
        if msg.channel == 'instagram_dm':
            ig_unsent = unsend_instagram_message(msg.external_id)
        elif msg.channel == 'instagram_comment':
            ig_unsent = delete_instagram_comment(msg.external_id)

    # Delete from our DB regardless of IG result
    db.session.delete(msg)

    # If this was the conv's last message, recalc
    if conv:
        latest = (Message.query
                  .filter_by(conversation_id=conv.id)
                  .order_by(Message.created_at.desc(), Message.id.desc())
                  .first())
        if latest and latest.id != msg.id:
            conv.last_message = latest.content[:200] if latest.content else ''
            conv.last_message_at = latest.created_at

    db.session.commit()

    log_audit(
        current_user.id,
        'delete_message',
        resource_type='message',
        resource_id=str(message_id),
        changes={'ig_unsent': ig_unsent, 'channel': msg.channel},
    )

    return jsonify({
        'deleted': True,
        'ig_unsent': ig_unsent,
        'conversation': conv.to_dict(include_messages=False) if conv else None,
    }), 200

@messages_bp.route('/messages/<int:message_id>', methods=['PATCH'])
@jwt_required()
def edit_message(message_id):
    """
    "Edit" an outbound message. Meta has no real edit API, so we:
      1. Unsend the original IG message (if within 24h)
      2. Save the new content as a separate outbound message
      3. Send the new content to IG
    """
    from app.integrations.meta import unsend_instagram_message, delete_instagram_comment
    from app.services import _dispatch_reply

    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    new_content = (data.get('content') or '').strip()
    reply_to_message_id = data.get('reply_to_message_id')
    if not new_content:
        return jsonify({'error': 'New content required'}), 400

    original = Message.query.get(message_id)
    if not original:
        return jsonify({'error': 'Message not found'}), 404

    if original.direction != 'outbound':
        return jsonify({'error': 'Can only edit outbound messages'}), 403

    conv = Conversation.query.get(original.conversation_id)

    # Same missing authorisation as DELETE above, and worse: this one deletes
    # the original, then SENDS new content to the customer. An agent could put
    # words in another agent's conversation. Verified exploitable — it returned
    # 200 on a conversation the agent had no access to.
    if conv and not _agent_can_access_conversation(current_user, conv):
        return jsonify({'error': 'Forbidden'}), 403

    customer = conv.user if conv else None

    # Step 1: Unsend the original from IG
    ig_unsent = False
    if original.external_id:
        if original.channel == 'instagram_dm':
            ig_unsent = unsend_instagram_message(original.external_id)
        elif original.channel == 'instagram_comment':
            ig_unsent = delete_instagram_comment(original.external_id)

    # Step 2: Delete the original from our DB
    db.session.delete(original)

    # Step 3: Create the new outbound message
    now = datetime.utcnow()
    new_msg = Message(
        conversation_id=conv.id,
        user_id=conv.user_id,
        channel=conv.channel,
        direction='outbound',
        sender=original.sender,  # preserve who originally sent ('ai' or 'human')
        sender_id=current_user.id,
        content=new_content,
        created_at=now,
    )
    db.session.add(new_msg)
    conv.last_message = new_content[:200]
    conv.last_message_at = now
    conv.updated_at = now

    db.session.commit()

    # Step 4: Send the new content to IG.
    #
    # Note the order this endpoint is forced into: the original is unsent from
    # Instagram and deleted from our database BEFORE the replacement goes out.
    # If the send then fails, the customer is left with nothing at all — the
    # original is gone from their thread and the new text never arrived. That
    # used to return 200 with the new message, so the agent saw a successful
    # edit and the customer saw a message disappear. `delivered` is what tells
    # the UI to say so.
    delivered = False
    if customer:
        try:
            # For comment replies, we need the comment_id of the latest INBOUND
            # message in this conversation — that's the comment we're replying to.
            comment_ext_id = None
            if conv.channel.endswith("_comment"):
                # Thread under the comment the agent chose, when they chose
                # one. The UI has a "reply to" affordance that sets a specific
                # message, but its id was never sent to the server — only the
                # quoted text got prepended to the body. So picking the first
                # of three comments still posted the reply under the newest
                # one, and the quote was the only hint of what was meant.
                picked = None
                if reply_to_message_id:
                    picked = (Message.query
                              .filter_by(id=reply_to_message_id,
                                         conversation_id=conv.id,
                                         direction='inbound')
                              .first())
                if picked and picked.external_id:
                    comment_ext_id = picked.external_id
                else:
                    # id as tiebreaker: comments arriving in the same burst
                    # share a created_at to the microsecond, and ordering by
                    # timestamp alone then returns an arbitrary row — measured
                    # returning the OLDEST of three. A reply threading under a
                    # random comment is worse than one threading under the
                    # newest.
                    last_inbound = (Message.query
                        .filter_by(conversation_id=conv.id, direction='inbound')
                        .order_by(Message.created_at.desc(), Message.id.desc())
                        .first())
                    if last_inbound:
                        comment_ext_id = last_inbound.external_id
            new_ext_id = _dispatch_reply(
                channel=conv.channel,
                user_id=customer.external_id,
                reply=new_content,
                comment_external_id=comment_ext_id,
            )
            if new_ext_id:
                new_msg.external_id = new_ext_id
                delivered = True
                db.session.commit()
        except Exception as e:
                log_event("error", "messages.edit_message.dispatch",
                      f"Edit dispatch failed: {e}",
                      payload={"message_id": message_id, "error": str(e)})

    log_audit(
        current_user.id,
        'edit_message',
        resource_type='message',
        resource_id=str(message_id),
        changes={'ig_unsent': ig_unsent, 'new_preview': new_content[:80]},
    )

    return jsonify({
        'message': new_msg.to_dict(),
        'ig_unsent': ig_unsent,
        'delivered': delivered,
        'conversation': conv.to_dict(include_messages=False),
    }), 200

@messages_bp.route('/instagram/media/<media_id>', methods=['GET'])
@jwt_required()
def get_instagram_media(media_id):
    """
    Fetch IG post info (caption, thumbnail, permalink) from Meta Graph API.
    Used by the Messages page to show post context on comment conversations.

    Scoped to media the caller can actually reach. Previously any logged-in user
    could pass any media_id and have the server fetch it with the business
    token. The data returned is public post metadata, so this was never a
    serious leak — but it made the endpoint an open proxy onto our Graph API
    quota, and an agent could pull posts belonging to conversations outside
    their own queue. Now the id has to appear on a message in a conversation
    the caller is allowed to open.
    """
    import os
    import requests

    current_user = _current_user()
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    # Several customers can comment on the same post, so one media_id can belong
    # to several conversations. Access is granted if the caller can open ANY of
    # them — taking just the first row would deny an agent the post context for
    # a conversation that is genuinely theirs, purely because someone else's
    # conversation on the same post happened to sort first.
    candidates = (Conversation.query
                  .join(Message, Message.conversation_id == Conversation.id)
                  .filter(Message.media_id == media_id)
                  .limit(25)
                  .all())
    if not candidates:
        return jsonify({'error': 'Unknown media'}), 404
    if not any(_agent_can_access_conversation(current_user, c) for c in candidates):
        return jsonify({'error': 'Forbidden'}), 403
    
    # Whichever account the conversation belongs to, so a two-account setup
    # asks the right one rather than whichever connected most recently.
    account_id = next((c.business_account_id for c in candidates
                       if c.business_account_id), None)

    from app.integrations.meta import fetch_instagram_media
    data, error = fetch_instagram_media(media_id, account_id)
    if error:
        # 200 with an error field, not a 4xx/5xx. The caller renders post
        # context beside a message that is itself fine — a failure here should
        # degrade that one card, and returning an error status made the
        # frontend's catch swallow it into a permanent loading skeleton.
        return jsonify({'error': error}), 200

    return jsonify({
        'id': data.get('id'),
        'caption': data.get('caption'),
        'media_url': data.get('media_url'),
        'thumbnail_url': data.get('thumbnail_url'),
        'permalink': data.get('permalink'),
        'media_type': data.get('media_type'),
        'timestamp': data.get('timestamp'),
    }), 200