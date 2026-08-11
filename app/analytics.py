"""
app/analytics.py
Analytics endpoints — KPIs, charts data, per-agent breakdown.

Endpoints (JWT-protected, /api prefix):
  GET /api/analytics/summary    aggregated data for the Analytics page
  GET /api/analytics/agents     per-agent breakdown (supervisor + admin only)

Shared query params (precedence: start/end → period → days):
  ?start=&end=               explicit YYYY-MM-DD range, both ends inclusive
  ?period=today|week|month   calendar period in the business timezone
  ?days=N                    rolling N-day window (default 7, max 365)

Role-aware scoping (summary endpoint):
  - admin, supervisor : data for all conversations company-wide
  - agent             : data scoped to conversations assigned to them
"""

from collections import namedtuple
from datetime import datetime, time as dtime, timedelta, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func, case, text

from app import db
from app.models import AuthUser, Conversation, Log, Message
from app.auth import current_user_id
from app.utils.logger import log_event

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')


MAX_DAYS = 365
DEFAULT_DAYS = 7

# Platform families. Messages arrive on 'instagram_dm', 'instagram_comment'
# etc; everything reports at the platform level.
CHANNEL_FAMILIES = ('instagram', 'whatsapp', 'facebook', 'tiktok')

# How many never-answered conversations to list per channel. Enough to act on,
# bounded so a bad day can't push thousands of rows into the payload — the
# count beside the list stays exact either way.
NO_REPLY_SAMPLE = 10


def _channel_family(col):
    """SQL expression folding a channel column into its platform family."""
    return case(
        (col.like('instagram%'), 'instagram'),
        (col.like('facebook%'),  'facebook'),
        (col.like('tiktok%'),    'tiktok'),
        (col == 'whatsapp',      'whatsapp'),
        else_='other',
    )


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _require_user():
    user = AuthUser.query.get(current_user_id())
    if not user:
        return None, (jsonify({'error': 'User not found'}), 404)
    return user, None


# Two kinds of calendar period.
#
# OPEN periods run from their start to right now and are therefore usually
# partial — "this month" on the 1st is a few hours. Their comparison window is
# truncated to the same elapsed time so a part-period is never measured against
# a whole one.
#
# CLOSED periods are finished: yesterday, last week, last month. They have a
# fixed end, and their comparison IS a whole matching period, because both
# sides are complete.
#
# All of them resolve in the business timezone. That is why they live here and
# not in the browser — a dashboard opened from another country must still mean
# the shop's yesterday, not the viewer's.
OPEN_PERIODS = ('today', 'week', 'month')
CLOSED_PERIODS = ('yesterday', 'last_week', 'last_month')
CALENDAR_PERIODS = OPEN_PERIODS + CLOSED_PERIODS

# All fields are naive UTC, matching how every timestamp in the DB is written
# (datetime.utcnow()). `dates` is the list of LOCAL calendar dates the window
# covers, oldest first — the chart buckets against these.
_Window = namedtuple(
    '_Window',
    'days start end prev_start prev_end dates utc_offset period',
)


def _local_midnight(d, tz):
    """Naive-UTC instant of local midnight on date `d`."""
    return datetime.combine(d, dtime.min, tzinfo=tz) \
                   .astimezone(timezone.utc).replace(tzinfo=None)


def _parse_date_arg(name):
    """A YYYY-MM-DD query arg as a date, or None if absent. Raises on garbage."""
    raw = (request.args.get(name) or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{name} must be a date in YYYY-MM-DD format, got "{raw}".')


def _resolve_window():
    """
    Resolve the reporting window. Three modes, in precedence order:

      ?start=YYYY-MM-DD&end=YYYY-MM-DD
          An explicit range of LOCAL calendar days, both ends inclusive, so
          start == end is a single day. The previous window is the same number
          of days immediately before it.

      ?period=today|week|month
          CALENDAR periods in the business timezone — today runs from local
          midnight, week from the configured start-of-week, month from the
          1st. The previous window is the matching prior calendar period
          (yesterday / last week / last month), so "vs yesterday" compares
          two whole days rather than two overlapping 24h slices.

      ?days=N
          Rolling N×24h back from now, and a previous window of the same
          length immediately before it. This is the original behaviour, kept
          for the Analytics page whose labels ("7 days", "90 days") mean
          exactly that.

    The timezone matters: timestamps are stored as naive UTC, so a UTC-based
    "today" would start at 3am in Nairobi and bucket the whole evening into
    the following day.

    Raises ValueError on a malformed range; callers turn that into a 400.
    """
    from app.settings import business_timezone, week_starts_on_sunday

    tz = business_timezone()
    now_local = datetime.now(tz)
    today_local = now_local.date()
    end = datetime.utcnow()

    # ── Explicit range ───────────────────────────────────────────────────
    start_date, end_date = _parse_date_arg('start'), _parse_date_arg('end')
    if start_date or end_date:
        if not (start_date and end_date):
            raise ValueError('start and end must be given together.')
        if start_date > end_date:
            raise ValueError('start must be on or before end.')
        span = (end_date - start_date).days + 1
        if span > MAX_DAYS:
            raise ValueError(f'Range is {span} days; the maximum is {MAX_DAYS}.')

        # end_date is inclusive, so the window runs to midnight after it —
        # clamped to now, so picking a range ending today doesn't reach into
        # hours that haven't happened yet.
        win_start = _local_midnight(start_date, tz)
        win_end = min(_local_midnight(end_date + timedelta(days=1), tz), end)
        prev_start = _local_midnight(start_date - timedelta(days=span), tz)
        return _Window(
            days=span,
            start=win_start,
            end=win_end,
            prev_start=prev_start,
            # Same elapsed duration, so a range ending today (and therefore
            # part-way through its last day) isn't measured against a full one.
            prev_end=min(prev_start + (win_end - win_start), win_start),
            dates=[start_date + timedelta(days=i) for i in range(span)],
            utc_offset=now_local.utcoffset() or timedelta(0),
            period='custom',
        )

    period = (request.args.get('period') or '').strip().lower()
    if period in CALENDAR_PERIODS:
        # Start of the current week, needed by both week periods.
        week_offset = (now_local.weekday() + 1) % 7 if week_starts_on_sunday() \
                      else now_local.weekday()
        this_week_start = today_local - timedelta(days=week_offset)
        this_month_start = today_local.replace(day=1)

        # end_date is the EXCLUSIVE local day a closed period stops at; None
        # means the period is still running and stops at "now".
        end_date = None

        if period == 'today':
            start_date = today_local
            prev_start_date, prev_end_date = start_date - timedelta(days=1), start_date
        elif period == 'yesterday':
            start_date = today_local - timedelta(days=1)
            end_date = today_local
            prev_start_date, prev_end_date = start_date - timedelta(days=1), start_date
        elif period == 'week':
            start_date = this_week_start
            prev_start_date, prev_end_date = start_date - timedelta(days=7), start_date
        elif period == 'last_week':
            start_date = this_week_start - timedelta(days=7)
            end_date = this_week_start
            prev_start_date, prev_end_date = start_date - timedelta(days=7), start_date
        elif period == 'last_month':
            # First of last month, through to the first of this one.
            start_date = (this_month_start - timedelta(days=1)).replace(day=1)
            end_date = this_month_start
            prev_end_date = start_date
            prev_start_date = (start_date - timedelta(days=1)).replace(day=1)
        else:  # month
            start_date = this_month_start
            # Last day of the previous month, walked back to its 1st.
            prev_end_date = start_date
            prev_start_date = (start_date - timedelta(days=1)).replace(day=1)

        start = _local_midnight(start_date, tz)
        prev_start = _local_midnight(prev_start_date, tz)

        if end_date is not None:
            # Closed period: fixed end, and a whole matching window to compare
            # against — both sides are complete, so no truncation.
            end = _local_midnight(end_date, tz)
            days = (end_date - start_date).days
        else:
            days = (today_local - start_date).days + 1   # calendar days so far

        # LIKE-FOR-LIKE comparison. The current window is nearly always
        # partial — "this week" on a Wednesday is 3 days, "this month" on the
        # 1st is a few hours — so measuring it against a COMPLETE previous
        # period made every count card crash at the start of each period,
        # regardless of performance. On 1 June the old maths reported a red
        # ↓ (5 vs all 8 of May) where the honest comparison is a green ↑
        # (5 vs 0 on 1 May). So: truncate the previous window to the same
        # elapsed duration, clamped to its own end so a long month compared
        # against a short one can't bleed past it.
        if end_date is not None:
            prev_end = _local_midnight(prev_end_date, tz)
        else:
            elapsed = end - start
            prev_end = min(prev_start + elapsed, _local_midnight(prev_end_date, tz))

        return _Window(
            days=days,
            start=start,
            end=end,
            prev_start=prev_start,
            prev_end=prev_end,
            dates=[start_date + timedelta(days=i) for i in range(days)],
            utc_offset=now_local.utcoffset() or timedelta(0),
            period=period,
        )

    days = request.args.get('days', default=DEFAULT_DAYS, type=int) or DEFAULT_DAYS
    if days < 1:
        days = DEFAULT_DAYS
    if days > MAX_DAYS:
        days = MAX_DAYS
    start = end - timedelta(days=days)
    return _Window(
        days=days,
        start=start,
        end=end,
        prev_start=start - timedelta(days=days),
        prev_end=start,
        dates=[today_local - timedelta(days=i) for i in range(days - 1, -1, -1)],
        utc_offset=now_local.utcoffset() or timedelta(0),
        period=None,
    )


def _local_date(col, win):
    """
    SQL expression for a UTC timestamp column's LOCAL calendar date.

    Shifts by the window's UTC offset rather than using a DB-specific
    AT TIME ZONE, so the chart's day boundaries line up with the KPI window's.
    Exact for fixed-offset zones like Africa/Nairobi; in a DST zone the part
    of the window on the other side of a transition is off by an hour.
    """
    return func.date(col + win.utc_offset)


def _window():
    """Back-compat shim: (days, cutoff) for endpoints that only need the start."""
    win = _resolve_window()
    return win.days, win.start


def _ai_failure_clause():
    """
    What counts as an AI reply that failed. ONE definition.

    Two distinct things go wrong and both are failures from the customer's side:
    the generator never produced a reply, or a reply was written and the
    platform refused to deliver it. Counting only the first made the card
    contradict itself — a store whose Instagram sends were all being rejected
    showed "Failed 0" beside a success rate those very failures were dragging
    down.

    Shared with the reason breakdown, so the list underneath the number always
    adds up to the number. They were two separate expressions, and the
    breakdown was the narrower of the two.
    """
    return db.or_(
        Log.source == 'ai.generator.failure',
        db.and_(
            Log.source == 'services.no_reply_sent',
            text("logs.payload ->> 'reason' IN "
                 "('dispatch_failed', 'pipeline_exception')"),
        ),
    )


def _scope_filter(query, model, user):
    """
    Apply role-based scoping to a query on Conversation or Message.
    Agents only see data for conversations assigned to them.
    """
    if user.role != 'agent':
        return query
    # Limit to conversations assigned to this agent.
    # Works for both Conversation (filter by .id IN) and Message (join via conv).
    assigned_conv_ids = (
        db.session.query(Conversation.id)
        .filter(Conversation.assigned_to == user.id)
        .scalar_subquery()
    )
    if model is Conversation:
        return query.filter(Conversation.id.in_(assigned_conv_ids))
    if model is Message:
        return query.filter(Message.conversation_id.in_(assigned_conv_ids))
    if model is Log:
        # Logs with no conversation (system-level events) belong to nobody in
        # particular, so an agent shouldn't see them counted as theirs.
        return query.filter(Log.conversation_id.in_(assigned_conv_ids))
    return query


# ─────────────────────────────────────────────
# GET /api/analytics/summary
# ─────────────────────────────────────────────

@analytics_bp.route('/analytics/summary', methods=['GET'])
@jwt_required()
def summary():
    """
    Returns the data the Analytics page needs in one response:
      kpis           : avg_response_time_ms, ai_success_rate, override_rate,
                       messages_total, ai_replies_total, human_replies_total
      conversion     : real conversion attribution (recommended vs converted
                       conversations, rate, attributed orders + revenue)
      weekly         : last N days of (date, inbound, ai_replied)
      intent_breakdown : top intents with counts and percents
      channel_split  : per-channel message counts and percents
      top_products   : most-asked-about products by mention count
    """
    user, err = _require_user()
    if err:
        return err

    try:
        win = _resolve_window()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    days, cutoff = win.days, win.start

    # ── KPIs: current window + previous window ───────────────────────────
    # The Dashboard picks "today", "week" or "month" via ?period=; the
    # Analytics page picks a rolling span via ?days=N. Either way we return
    # both current and previous so the cards can show change.

    def _kpis_for_window(start_dt, end_dt):
        """Compute all KPIs for a single time window [start_dt, end_dt)."""
        msg_q = _scope_filter(
            Message.query.filter(Message.created_at >= start_dt)
                                 .filter(Message.created_at < end_dt),
            Message, user,
        )
        conv_q = _scope_filter(
            Conversation.query.filter(Conversation.last_message_at >= start_dt)
                                       .filter(Conversation.last_message_at < end_dt),
            Conversation, user,
        )

        total_msgs = msg_q.count()
        inbound   = msg_q.filter(Message.direction == 'inbound').count()
        ai_repl   = msg_q.filter(Message.direction == 'outbound',
                                 Message.sender == 'ai').count()
        human_repl = msg_q.filter(Message.direction == 'outbound',
                                  Message.sender == 'human').count()

        avg_ms = _scope_filter(
            db.session.query(func.avg(Message.ai_response_time_ms))
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.ai_response_time_ms.isnot(None)),
            Message, user,
        ).scalar()

        total_convs = conv_q.count()

        # ── Escalations and overrides: count the EVENT, in this window ────
        # These used to be conv_q filters, i.e. "conversations whose
        # last_message_at falls in the window AND which carry a
        # handoff_reason". Two things were wrong with that:
        #   - It counted state, not events. One June escalation recounted in
        #     July, August, and every window the thread stayed alive in.
        #   - handoff_reason is cleared when an agent switches the AI back on
        #     (app/messages.py), so re-enabling a conversation ERASED its
        #     escalation from the figures. Conversation 47 escalated three
        #     times in June and counted zero.
        # Sourcing from handoff.triggered logs fixes both: it's append-only,
        # timestamped, and survives the flag being cleared. Conversation
        # .escalated_at covers rows that predate handoff logging — union the
        # two and count distinct conversations, so a thread that ping-ponged
        # several times in one window still counts once.
        esc_from_logs = set(
            cid for (cid,) in _scope_filter(
                db.session.query(Log.conversation_id)
                  .filter(Log.source == 'handoff.triggered')
                  .filter(Log.conversation_id.isnot(None))
                  .filter(Log.created_at >= start_dt)
                  .filter(Log.created_at < end_dt),
                Log, user,
            ).distinct().all()
        )
        esc_from_col = set(
            cid for (cid,) in _scope_filter(
                db.session.query(Conversation.id)
                  .filter(Conversation.escalated_at >= start_dt)
                  .filter(Conversation.escalated_at < end_dt),
                Conversation, user,
            ).all()
        )
        escalated = len(esc_from_logs | esc_from_col)

        # Why, not just how many. "2 escalated" tells you the number and
        # nothing you can act on: two people asking for a human is the system
        # working, two ai_unavailable is an outage, two image_unconfirmed is a
        # matching problem worth fixing. Same figure, three different Mondays.
        #
        # Grouped on payload.detail rather than reason, because reason is the
        # mechanism that caught it ('ai_detected', 'intent') while detail is
        # what was actually wrong ('abuse', 'ready_to_order'). Falls back to
        # reason when detail is absent on older rows.
        # ONE reason per conversation, and the numbers must add up to
        # `escalated`.
        #
        # This grouped by reason and counted distinct conversations within each
        # group — so a thread escalated twice for different reasons landed in
        # both buckets. 3 escalations reported 6 reasons, and a breakdown that
        # cannot sum to its own total is worse than no breakdown: it invites
        # someone to add the chips up and act on a number that never existed.
        #
        # Reduced in Python rather than DISTINCT ON in SQL because _scope_filter
        # applies the per-agent visibility rules, and raw SQL would step around
        # them. Escalation volume is small enough that this is free.
        try:
            esc_log_rows = _scope_filter(
                db.session.query(
                    Log.conversation_id,
                    func.coalesce(
                        text("logs.payload ->> 'detail'"),
                        text("logs.payload ->> 'reason'"),
                    ).label('why'),
                    Log.created_at,
                ).filter(Log.source == 'handoff.triggered')
                 .filter(Log.conversation_id.isnot(None))
                 .filter(Log.created_at >= start_dt)
                 .filter(Log.created_at < end_dt),
                Log, user,
            ).all()

            # Latest escalation wins. A thread that was escalated for a
            # complaint and later because the AI fell over is, today, an
            # ai_unavailable — describing it by the older reason would point at
            # the wrong fix.
            latest = {}
            for conv_id, why, created in esc_log_rows:
                prev = latest.get(conv_id)
                if prev is None or created > prev[1]:
                    latest[conv_id] = (why, created)

            counts = {}
            for why, _created in latest.values():
                key = why or 'unrecorded'
                counts[key] = counts.get(key, 0) + 1

            # Conversations counted in `escalated` via Conversation.escalated_at
            # that have no handoff.triggered log — rows predating handoff
            # logging. Without this the chips silently under-report instead of
            # over-reporting, which is the same fault in the other direction.
            unlogged = max(0, escalated - len(latest))
            if unlogged:
                counts['unrecorded'] = counts.get('unrecorded', 0) + unlogged

            escalation_breakdown = sorted(
                [{'reason': k, 'count': v} for k, v in counts.items()],
                key=lambda r: r['count'], reverse=True,
            )
        except Exception as e:
            log_event("warn", "analytics.escalation_breakdown_failed", str(e))
            escalation_breakdown = []

        # A human switching the AI off by hand — no escalation involved.
        human_override = _scope_filter(
            Conversation.query
              .filter(Conversation.ai_disabled_at >= start_dt)
              .filter(Conversation.ai_disabled_at < end_dt)
              .filter(Conversation.handoff_reason.is_(None)),
            Conversation, user,
        ).count()

        # ── AI eligibility: inbound on convs where AI was supposed to reply ─
        # A message is "AI-eligible" iff, at the moment it arrived, all FOUR
        # gates were open — mirroring services._ai_should_respond exactly:
        #   1. the global AI master switch (settings → ai.enabled)
        #   2. its channel (enabled=True, or no Channel row — fail open)
        #   3. its conversation (ai_enabled=True)
        #   4. on *_comment channels only: the text looks like a question,
        #      because comments are public and the bot stays out of praise
        # Anything the AI was switched off for is admin/agent-suppressed and
        # can't be counted as an AI failure. Frozen snapshot, not a live join —
        # see Message.ai_eligible, written by services._save_message.
        eligible_msg_q = _scope_filter(
            Message.query
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'inbound')
              .filter(Message.ai_eligible.is_(True)),
            Message, user,
        )
        eligible_inbound = eligible_msg_q.count()

        # NOT filtered by eligibility — it's every AI reply in the window. The
        # old name (eligible_ai_replies) implied otherwise. Only used for the
        # message-level `unanswered` figure below, which nothing renders.
        ai_replies_in_window = _scope_filter(
            Message.query
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'outbound')
              .filter(Message.sender == 'ai'),
            Message, user,
        ).count()

        # Real AI failures. NOT (eligible_inbound - ai_replies), which counted
        # normal coalescing — 3 messages answered by 1 reply scored 2
        # "failures" — so the number climbed even when nothing was wrong.
        #
        # All THREE ways the AI can fail a customer, matching exactly the set
        # that disqualifies a conversation from the success rate:
        #   - the generator threw and fell back to a canned mock reply
        #   - a reply was written but the platform rejected the send
        #   - the pipeline raised and nothing was sent at all
        # Counting only generator failures made the card contradict itself: a
        # store whose Instagram sends were all being refused showed "Failed 0"
        # beside a success rate those very failures were suppressing.
        #
        # Scoped like every other KPI on this card: an agent was seeing
        # company-wide failure counts sitting next to their own numbers.
        failed = _scope_filter(
            db.session.query(func.count(Log.id))
              .filter(Log.created_at >= start_dt)
              .filter(Log.created_at < end_dt)
              .filter(_ai_failure_clause()),
            Log, user,
        ).scalar() or 0

        # The same failures counted as CONVERSATIONS.
        #
        # `failed` counts log rows: one conversation that failed three times
        # contributes three. Printed as "Failed 11" beside "8 conversations the
        # AI was on duty for", it read as more failures than there were
        # conversations — a number that cannot be true, so a reader either
        # distrusts the card or invents an explanation. Both figures are real;
        # they were just never labelled with their unit.
        failed_conversations = _scope_filter(
            db.session.query(func.count(func.distinct(Log.conversation_id)))
              .filter(Log.created_at >= start_dt)
              .filter(Log.created_at < end_dt)
              .filter(Log.conversation_id.isnot(None))
              .filter(_ai_failure_clause()),
            Log, user,
        ).scalar() or 0

        # Still worth tracking separately: inbound with no AI reply. Mostly
        # legitimate (coalesced bursts, skipped non-question comments), so it
        # is NOT a failure count.
        unanswered = max(0, eligible_inbound - ai_replies_in_window)
        # RESPONSE rate at CONVERSATION level. Message-level (ai_replies /
        # inbound) is structurally depressed by coalescing: 3 customer messages
        # answered by 1 reply scored 33%, even though the customer was fully
        # answered. What matters is whether the conversation got a reply.
        inbound_conv_ids = set(
            cid for (cid,) in eligible_msg_q
                .with_entities(Message.conversation_id).distinct().all()
        )
        answered_conv_ids = set(
            cid for (cid,) in _scope_filter(
                db.session.query(Message.conversation_id)
                  .filter(Message.created_at >= start_dt)
                  .filter(Message.created_at < end_dt)
                  .filter(Message.direction == 'outbound')
                  .filter(Message.sender == 'ai')
                  .filter(Message.conversation_id.in_(inbound_conv_ids)),
                Message, user,
            ).distinct().all()
        )
        response_rate = (
            len(inbound_conv_ids & answered_conv_ids) / len(inbound_conv_ids)
        ) if inbound_conv_ids else 0.0

        # ── SUCCESS rate ──────────────────────────────────────────────────
        # Only judge the AI on conversations it was actually ON DUTY for: at
        # least one inbound message arrived in this window while every gate
        # said "answer this" — the global master switch, the channel toggle
        # and the per-conversation toggle. That set is `inbound_conv_ids`,
        # built from the frozen Message.ai_eligible snapshot, so a mid-window
        # toggle splits cleanly at the message that flipped it.
        #
        # The old denominator was "conversations active in the window that
        # never escalated", which was wrong at both ends:
        #   - It swept in conversations with the AI switched off — by an agent
        #     on a single chat, or by an admin globally. Those carry no
        #     handoff_reason, so they landed in the denominator and, never
        #     having been allowed to reply, scored as failures. Silencing the
        #     AI dragged down the AI's own score.
        #   - It dropped escalated conversations entirely, so punting to a
        #     human was free. A punt is the AI declining a conversation it was
        #     on duty for, so it belongs in the denominator as a miss.
        #
        #   denominator = AI was on and expected to respond
        #   numerator   = customer engaged (>=2 inbound msgs OR an attributed
        #                 order) AND the AI never punted to a human.
        from app.models import ConversionAttribution

        handled_conv_ids = list(inbound_conv_ids)
        handled_total = len(handled_conv_ids)

        engaged_total = 0
        handled_breakdown = []
        if handled_conv_ids:
            # Multi-turn: conversations with >=2 inbound messages.
            multiturn_ids = set(
                cid for (cid,) in db.session.query(Message.conversation_id)
                    .filter(Message.conversation_id.in_(handled_conv_ids))
                    .filter(Message.direction == 'inbound')
                    .group_by(Message.conversation_id)
                    .having(func.count(Message.id) >= 2)
                    .all()
            )
            # Ordered: conversations with an attributed order.
            ordered_ids = set(
                cid for (cid,) in db.session.query(ConversionAttribution.conversation_id)
                    .filter(ConversionAttribution.conversation_id.in_(handled_conv_ids))
                    .distinct()
                    .all()
            )
            # Punted: handed off to a human. handoff_reason is only ever set by
            # the escalation path — a plain manual takeover leaves it NULL —
            # so this is the AI's own decision to stop, not an agent's.
            # Uses the SAME event-based definition as the Escalated KPI —
            # `esc_from_logs | esc_from_col` above — narrowed to the handled
            # set. Reading Conversation.handoff_reason instead meant reading
            # current STATE: an agent re-enabling the AI clears that flag, so a
            # conversation that punted three times in the window stopped
            # counting as a punt. That made the card contradict itself, showing
            # "Escalated 8" beside a success rate that only excluded 7.
            punted_ids = (esc_from_logs | esc_from_col) & set(handled_conv_ids)
            # FAILED: the AI was on duty and something broke. Three ways:
            #   - the generator threw and fell back to a canned mock reply
            #   - the pipeline raised and nothing was sent
            #   - a reply was written but never reached the platform
            # All three leave the customer without a real answer, so none can
            # count as a success. This was the missing half of the rule the
            # rate is built on — "failed to respond OR punted" — punts were
            # excluded from the numerator but failures sailed through, so a
            # conversation where Claude errored still scored as a win if the
            # customer happened to send a second message.
            failed_ids = set(
                cid for (cid,) in db.session.query(Log.conversation_id)
                    .filter(Log.conversation_id.in_(handled_conv_ids))
                    .filter(Log.created_at >= start_dt)
                    .filter(Log.created_at < end_dt)
                    .filter(db.or_(
                        Log.source == 'ai.generator.failure',
                        db.and_(
                            Log.source == 'services.no_reply_sent',
                            text("logs.payload ->> 'reason' IN "
                                 "('dispatch_failed', 'pipeline_exception')"),
                        ),
                    ))
                    .distinct().all()
            )
            # A success REQUIRES the AI to have actually replied. Without this,
            # "engaged" only meant the customer sent two messages — so someone
            # who wrote twice and was ignored scored as a win, because being
            # ignored and repeating yourself looks identical to a multi-turn
            # conversation if you only count inbound. The same guard stops an
            # order the AI played no part in being credited to it.
            engaged_total = len(
                (multiturn_ids | ordered_ids)
                & answered_conv_ids
                - punted_ids - failed_ids
            )

            # Where the OTHER conversations went.
            #
            # The card said "of the 8 the AI was on duty for, 4 handled
            # successfully" and stopped — leaving half unaccounted for on the
            # one card that is supposed to say how the assistant is doing. It
            # also sat beside Channel Performance reporting "8 answered by AI"
            # for the same window, which reads as a contradiction: one counts
            # replies sent, the other counts conversations that went well.
            #
            # These four are mutually exclusive, evaluated in this order, and
            # together with engaged_total they sum to handled_total exactly.
            handled_set = set(handled_conv_ids)
            _succeeded = (multiturn_ids | ordered_ids) & answered_conv_ids - punted_ids - failed_ids
            _failed    = handled_set & failed_ids - _succeeded
            _punted    = handled_set & punted_ids - _succeeded - _failed
            _silent    = handled_set - answered_conv_ids - _succeeded - _failed - _punted
            _brief     = handled_set - _succeeded - _failed - _punted - _silent
            handled_breakdown = [
                {'key': 'succeeded', 'count': len(_succeeded)},
                {'key': 'failed',    'count': len(_failed)},
                {'key': 'escalated', 'count': len(_punted)},
                {'key': 'unanswered','count': len(_silent)},
                {'key': 'brief',     'count': len(_brief)},
            ]

        success_rate = (engaged_total / handled_total) if handled_total else 0.0

        # Override rate, on the SAME population as the success rate: of the
        # conversations the AI was on duty for, how many did a human take over?
        # The Dashboard used to divide human_override_total (events timed by
        # ai_disabled_at) by conversations_total (conversations merely active in
        # the window) — two different populations, so the figure could exceed
        # 100% and meant nothing precise at any value. Nested sets can't.
        overridden_in_handled = 0
        if handled_conv_ids:
            overridden_in_handled = (
                db.session.query(func.count(Conversation.id))
                .filter(Conversation.id.in_(handled_conv_ids))
                .filter(Conversation.ai_disabled_at >= start_dt)
                .filter(Conversation.ai_disabled_at < end_dt)
                .filter(Conversation.handoff_reason.is_(None))
                .scalar() or 0
            )
        override_rate = (overridden_in_handled / handled_total) if handled_total else 0.0

        return {
            'messages_total':      total_msgs,
            'inbound_total':       inbound,
            'ai_replies_total':    ai_repl,
            'human_replies_total': human_repl,
            'failed_responses':    failed,                  # LOG ROWS, not conversations
            'failed_conversations': failed_conversations,   # distinct conversations affected
            'unanswered_inbound':  unanswered,
            # round(), not int(). int() truncates toward zero, so every reported
            # average response time was up to 1ms below the true value —
            # a small but systematic downward bias on a headline metric.
            'avg_response_time_ms': int(round(avg_ms)) if avg_ms is not None else None,
            'ai_response_rate':    round(response_rate, 4),   # renamed from ai_success_rate
            'ai_success_rate':     round(success_rate, 4),    # NEW — real success
            'ai_handled_total':    handled_total,             # denominator, for context
            'ai_engaged_total':    engaged_total,             # numerator, for context
            # Every on-duty conversation, accounted for. Sums to ai_handled_total.
            'ai_handled_breakdown': handled_breakdown,
            'human_override_total': human_override,
            'override_rate':       round(override_rate, 4),   # of AI-on-duty convos
            'overridden_in_handled': overridden_in_handled,   # numerator, for context
            'escalated_total':     escalated,
            'escalation_breakdown': escalation_breakdown,
            'conversations_total': total_convs,
        }

    current  = _kpis_for_window(win.start, win.end)
    previous = _kpis_for_window(win.prev_start, win.prev_end)

    # Flat kpis dict for backward compatibility with the Analytics page.
    # Adds a `previous` nested object that the Dashboard uses for change arrows.
    kpis = {**current, 'previous': previous}

    # ── Conversion attribution (real, from conversion_attributions) ──────
    # Denominator B: conversations where the AI recommended a product (sent a
    # message carrying a utm_token) in the window. Numerator: distinct
    # conversations that produced an attributed order. Global (not agent-scoped)
    # since it's a business KPI. Wrapped so a query issue can never 500 the
    # whole dashboard — it just degrades the tile to zeros.
    try:
        from app.models import ConversionAttribution
        # COHORT basis: everything below is anchored on the SAME set of
        # conversations — those that received a tracked link in this window.
        # Previously the numerator counted orders dated in the window while the
        # denominator counted recommendations in the window, so an order today
        # against last month's recommendation landed in one and not the other,
        # letting the rate exceed 100%.
        # A RECOMMENDATION is a reply that actually pointed at a product, i.e.
        # carries product_url. It is NOT "has a utm_token": generator.py stamps
        # a token on EVERY successful AI reply, so keying off it counted plain
        # answers like "what are your hours?" as product recommendations. That
        # inflated the denominator with conversations where nothing was ever
        # recommended, making the conversion rate structurally too low.
        # Scoped like every other figure on the Dashboard. It used to be
        # global "since it's a business KPI", which meant an agent saw
        # company-wide revenue sitting beside their own personal counts —
        # the one number on their screen that wasn't theirs.
        recommended_rows = _scope_filter(
            db.session.query(Message.id, Message.conversation_id)
              .filter(Message.direction == 'outbound')
              .filter(Message.sender == 'ai')
              .filter(Message.product_url.isnot(None))
              .filter(Message.created_at >= cutoff)
              .filter(Message.created_at < win.end),
            Message, user,
        ).all()
        recommended_msg_ids = {mid for mid, _ in recommended_rows}
        recommended_conv_ids = {cid for _, cid in recommended_rows if cid is not None}
        recommended_convos = len(recommended_conv_ids)

        converted_convos = 0
        attributed_orders = 0
        attributed_revenue_raw = 0
        if recommended_msg_ids:
            # Matched on the MESSAGE, not the conversation. Matching by
            # conversation credited this window's recommendation with orders
            # driven by an earlier one in the same thread — including orders
            # placed before the recommendation existed. The utm token ties an
            # order to the exact message that earned it, so use that.
            conv_rows = (
                db.session.query(ConversionAttribution)
                  .filter(ConversionAttribution.message_id.in_(recommended_msg_ids))
                  .all()
            )
            converted_convos = len({r.conversation_id for r in conv_rows
                                    if r.conversation_id is not None})
            attributed_orders = len(conv_rows)

        # ── Revenue, net of tax, in ONE currency ─────────────────────────
        # Two problems this replaces:
        #   1. Every total was divided by a flat 1.16 VAT divisor whether or
        #      not tax was charged. Shopify reports total_tax per order, so
        #      net = total - tax exactly. Rows predating order_tax keep the old
        #      divisor rather than silently changing what historical figures
        #      mean.
        #   2. Totals were summed across currencies and labelled KES, so one
        #      USD order would quietly corrupt the number. There is no FX rate
        #      available here and inventing one would be worse than declining,
        #      so we report the majority currency and say how much was left out.
        from app.customers import ex_vat
        by_currency = {}
        for r in conv_rows if recommended_msg_ids else []:
            gross = float(r.order_total or 0)
            net = (gross - float(r.order_tax)) if r.order_tax is not None else ex_vat(gross)
            cur = (r.order_currency or 'KES').upper()
            slot = by_currency.setdefault(cur, {'net': 0.0, 'orders': 0})
            slot['net'] += net
            slot['orders'] += 1

        main_currency, main = ('KES', {'net': 0.0, 'orders': 0})
        if by_currency:
            main_currency, main = max(by_currency.items(), key=lambda kv: kv[1]['orders'])
        excluded_orders = sum(v['orders'] for k, v in by_currency.items() if k != main_currency)

        conversion = {
            'recommended_conversations': recommended_convos,
            'converted_conversations':   converted_convos,
            'conversion_rate':           round((converted_convos / recommended_convos) if recommended_convos else 0.0, 4),
            'attributed_orders':         attributed_orders,
            'attributed_revenue':        round(main['net'], 2),
            'revenue_currency':          main_currency,
            # >0 means orders in other currencies exist and are NOT in the
            # figure above. Silently dropping them is the thing to avoid.
            'revenue_excluded_orders':   excluded_orders,
        }
    except Exception as e:
        log_event("warn", "analytics.conversion_failed", str(e))
        conversion = {
            'recommended_conversations': 0,
            'converted_conversations':   0,
            'conversion_rate':           0.0,
            'attributed_orders':         0,
            'attributed_revenue':        0.0,
            'revenue_currency':          'KES',
            'revenue_excluded_orders':   0,
        }

    # ── AI failure breakdown (why replies failed) ────────────────────────
    # Groups ai.generator.failure logs in the window by their structured
    # `reason`. Wrapped so a query issue can't 500 the dashboard.
    try:
        reason_expr = text("payload ->> 'reason'")
        # Scoped, like the failed_responses COUNT it breaks down. Without this
        # an agent saw their own failure count beside a company-wide list of
        # reasons, so the parts didn't add up to the whole.
        #
        # And it used the SAME predicate as that count, via _ai_failure_clause.
        # It used to filter on ai.generator.failure alone while the count also
        # included sends the platform rejected — so on a day when every failure
        # was Instagram refusing to deliver, the card read "Failed 17" above an
        # empty list. "Something is wrong and we won't say what" is the worst
        # thing a diagnostic can do.
        rows = (_scope_filter(
                    db.session.query(reason_expr, func.count(Log.id))
                      .filter(_ai_failure_clause())
                      .filter(Log.created_at >= cutoff)
                      .filter(Log.created_at < win.end),
                    Log, user,
                )
                .group_by(reason_expr)
                .all())
        failure_breakdown = [
            {'reason': (r or 'unknown'), 'count': int(c)}
            for r, c in sorted(rows, key=lambda x: x[1], reverse=True)
        ]
    except Exception as e:
        log_event("warn", "analytics.failure_breakdown_failed", str(e))
        failure_breakdown = []

    # Keep these in scope for the chart/intent/etc. blocks below
    inbound_total = current['inbound_total']
    ai_replies    = current['ai_replies_total']

    # ── Weekly chart data ─────────────────────────────────────────────────
    # One row per day in the window with both totals and per-channel inbound
    # counts (used for the multi-line graph on the Dashboard). Days are LOCAL
    # calendar days, so the bars line up with the KPI window above them —
    # bucketing on raw UTC put the last three hours of each Nairobi evening
    # into the next day's bar.
    local_day = _local_date(Message.created_at, win)
    weekly_q = _scope_filter(
        db.session.query(
            local_day.label('day'),
            func.count(case((Message.direction == 'inbound', 1))).label('inbound'),
            func.count(case((db.and_(Message.direction == 'outbound',
                                     Message.sender == 'ai'), 1))).label('ai_replied'),
        ).filter(Message.created_at >= cutoff)
         .group_by(local_day),
        Message, user,
    )
    weekly_rows = {row.day: (row.inbound, row.ai_replied) for row in weekly_q.all()}

    # Per-channel-per-day counts for the Dashboard channel graph.
    # We group all instagram_* into 'instagram', facebook_* into 'facebook', etc.
    # Three counts per (day, channel): inbound, ai_replied, human_replied
    channel_group = _channel_family(Message.channel)
    per_channel_q = _scope_filter(
        db.session.query(
            local_day.label('day'),
            channel_group.label('channel'),
            func.count(case((Message.direction == 'inbound', 1))).label('inbound'),
            func.count(case((db.and_(Message.direction == 'outbound',
                                     Message.sender == 'ai'), 1))).label('ai_replied'),
            func.count(case((db.and_(Message.direction == 'outbound',
                                     Message.sender == 'human'), 1))).label('human_replied'),
        ).filter(Message.created_at >= cutoff)
         .group_by(local_day, channel_group),
        Message, user,
    )
    per_channel = {}
    for row in per_channel_q.all():
        per_channel.setdefault(row.day, {})[row.channel] = {
            'inbound': int(row.inbound),
            'ai_replied': int(row.ai_replied),
            'human_replied': int(row.human_replied),
        }

    # Fill missing days with zeros so the chart always has one point per day
    # the window covers (win.dates, oldest first, in local time).
    weekly = []
    for d in win.dates:
        inb, ai_r = weekly_rows.get(d, (0, 0))
        day_channels = per_channel.get(d, {})

        def _ch(name, key):
            entry = day_channels.get(name)
            return entry.get(key, 0) if entry else 0

        weekly.append({
            'date': d.isoformat(),
            'day': d.strftime('%a'),
            'inbound': int(inb),
            'ai_replied': int(ai_r),
            'instagram':       _ch('instagram', 'inbound'),
            'instagram_ai':    _ch('instagram', 'ai_replied'),
            'instagram_human': _ch('instagram', 'human_replied'),
            'whatsapp':        _ch('whatsapp',  'inbound'),
            'whatsapp_ai':     _ch('whatsapp',  'ai_replied'),
            'whatsapp_human':  _ch('whatsapp',  'human_replied'),
            'facebook':        _ch('facebook',  'inbound'),
            'facebook_ai':     _ch('facebook',  'ai_replied'),
            'facebook_human':  _ch('facebook',  'human_replied'),
            'tiktok':          _ch('tiktok',    'inbound'),
            'tiktok_ai':       _ch('tiktok',    'ai_replied'),
            'tiktok_human':    _ch('tiktok',    'human_replied'),
        })

    # ── Intent breakdown ──────────────────────────────────────────────────
    intent_q = _scope_filter(
        db.session.query(Message.intent, func.count(Message.id))
        .filter(Message.created_at >= cutoff)
        .filter(Message.direction == 'inbound')
        .filter(Message.intent.isnot(None)),
        Message, user,
    ).group_by(Message.intent)
    intent_rows = intent_q.all()

    # Intents stored as "intent1|intent2|..." (pipe-joined). Expand and tally.
    intent_counts = {}
    for label, count in intent_rows:
        for piece in (label or '').split('|'):
            piece = piece.strip()
            if piece:
                intent_counts[piece] = intent_counts.get(piece, 0) + count
    # Percent = share of intent-LABELLED MESSAGES carrying this intent. The old
    # denominator was total intent *mentions*, so a 3-intent message counted 3
    # times while the UI called them messages. These sum to >100% when messages
    # carry multiple intents — that's correct for multi-label data.
    total_labelled_msgs = sum(c for _, c in intent_rows) or 1
    intent_breakdown = sorted(
        [{'name': k, 'count': v, 'percent': round(100 * v / total_labelled_msgs, 1)}
         for k, v in intent_counts.items()],
        key=lambda x: x['count'], reverse=True,
    )[:6]  # top 6 fits the donut chart legend nicely

    # ── Channel split ─────────────────────────────────────────────────────
    # INBOUND only — this is a customer-traffic view. Counting outbound made a
    # chatty channel look busier than one customers actually use.
    channel_q = _scope_filter(
        db.session.query(Message.channel, func.count(Message.id))
        .filter(Message.created_at >= cutoff)
        .filter(Message.direction == 'inbound')
        .group_by(Message.channel),
        Message, user,
    )
    channel_rows = channel_q.all()
    total_chan = sum(c for _, c in channel_rows) or 1
    channel_split = sorted(
        [{'name': ch, 'count': int(c), 'percent': round(100 * c / total_chan, 1)}
         for ch, c in channel_rows],
        key=lambda x: x['count'], reverse=True,
    )

    # ── Channel performance ───────────────────────────────────────────────
    # Per-platform health, for the "which channel needs attention?" sheet.
    # It answers three questions the raw counts can't: is the AI keeping up
    # here, how fast is it, and how often does this channel end up with a
    # human. The sheet used to derive its numbers by re-summing the chart
    # series, which silently dropped the 'other' bucket and could disagree
    # with the KPI cards above it.
    def _channel_perf(start_dt, end_dt):
        fam = _channel_family(Message.channel)
        counts = {
            r.channel: r for r in _scope_filter(
                db.session.query(
                    fam.label('channel'),
                    func.count(case((Message.direction == 'inbound', 1))).label('inbound'),
                    func.count(case((db.and_(Message.direction == 'outbound',
                                             Message.sender == 'ai'), 1))).label('ai'),
                    func.count(case((db.and_(Message.direction == 'outbound',
                                             Message.sender == 'human'), 1))).label('human'),
                    func.avg(Message.ai_response_time_ms).label('avg_ms'),
                ).filter(Message.created_at >= start_dt)
                 .filter(Message.created_at < end_dt)
                 .group_by(fam),
                Message, user,
            ).all()
        }

        # Conversation-level response rate, per channel — same basis as the
        # top-level one: only conversations the AI was on duty for, and a
        # conversation counts as answered if it got any AI reply.
        eligible = {}
        for ch, cid in _scope_filter(
            db.session.query(fam.label('channel'), Message.conversation_id)
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'inbound')
              .filter(Message.ai_eligible.is_(True))
              .distinct(),
            Message, user,
        ).all():
            eligible.setdefault(ch, set()).add(cid)

        answered = {}
        for ch, cid in _scope_filter(
            db.session.query(fam.label('channel'), Message.conversation_id)
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'outbound')
              .filter(Message.sender == 'ai')
              .distinct(),
            Message, user,
        ).all():
            answered.setdefault(ch, set()).add(cid)

        # Conversations a human replied to. Needed to say what became of the
        # ones the AI didn't answer — "75% unanswered" is useless on its own
        # when most of that 75% was picked up by a person.
        human_answered = {}
        for ch, cid in _scope_filter(
            db.session.query(fam.label('channel'), Message.conversation_id)
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'outbound')
              .filter(Message.sender == 'human')
              .distinct(),
            Message, user,
        ).all():
            human_answered.setdefault(ch, set()).add(cid)

        # Escalations, from the same two sources as the KPI card.
        conv_fam = _channel_family(Conversation.channel)
        escalated = {}
        for ch, cid in _scope_filter(
            db.session.query(conv_fam.label('channel'), Conversation.id)
              .filter(Conversation.escalated_at >= start_dt)
              .filter(Conversation.escalated_at < end_dt),
            Conversation, user,
        ).all():
            escalated.setdefault(ch, set()).add(cid)
        for ch, cid in _scope_filter(
            db.session.query(conv_fam.label('channel'), Conversation.id)
              .join(Log, Log.conversation_id == Conversation.id)
              .filter(Log.source == 'handoff.triggered')
              .filter(Log.created_at >= start_dt)
              .filter(Log.created_at < end_dt),
            Conversation, user,
        ).all():
            escalated.setdefault(ch, set()).add(cid)

        # Why the AI didn't reply, straight from services.no_reply_sent. This
        # is what turns "3 never answered" from a dead end into something the
        # system can explain on its own.
        # Log.payload is declared as generic JSON but is jsonb in Postgres, so
        # `->>` via text() is the accessor that works — same approach as the
        # failure_breakdown query below.
        reason_col = text("logs.payload ->> 'reason'")
        no_reply_reasons = {}
        for ch, cid, reason in _scope_filter(
            db.session.query(conv_fam.label('channel'), Conversation.id, reason_col)
              .join(Log, Log.conversation_id == Conversation.id)
              .filter(Log.source == 'services.no_reply_sent')
              .filter(Log.created_at >= start_dt)
              .filter(Log.created_at < end_dt),
            Conversation, user,
        ).all():
            no_reply_reasons.setdefault(ch, {}).setdefault(reason or 'unknown', set()).add(cid)

        return counts, eligible, answered, escalated, human_answered, no_reply_reasons

    try:
        cur_counts, cur_elig, cur_ans, cur_esc, cur_hum, cur_reasons = \
            _channel_perf(win.start, win.end)
        prev_counts, *_ = _channel_perf(win.prev_start, win.prev_end)

        total_inbound_all = sum(int(r.inbound) for r in cur_counts.values()) or 1
        channel_performance = []
        # Include every family that saw traffic in either window, plus 'other'
        # only when it actually has some — an empty "other" row is noise.
        seen = set(cur_counts) | set(prev_counts)
        for ch in list(CHANNEL_FAMILIES) + ['other']:
            row = cur_counts.get(ch)
            prev = prev_counts.get(ch)
            inbound = int(row.inbound) if row else 0
            prev_inbound = int(prev.inbound) if prev else 0
            if ch == 'other' and inbound == 0 and prev_inbound == 0:
                continue
            if ch not in seen and inbound == 0:
                # Keep the four known platforms visible even at zero, so a
                # channel that has gone silent is conspicuous rather than absent.
                pass
            elig = cur_elig.get(ch, set())
            ans = cur_ans.get(ch, set())
            # Where every AI-on-duty conversation ended up. The three outcomes
            # are mutually exclusive and sum to handled_convos, so the UI can
            # account for all of it instead of leaving "75% unanswered"
            # hanging with no explanation.
            unanswered = elig - ans
            picked_up = unanswered & cur_hum.get(ch, set())
            # Reasons, restricted to the conversations actually counted as
            # never-answered — a suppression logged on a conversation the AI
            # went on to answer is not an explanation for anything.
            silent = unanswered - picked_up
            reasons = {}
            for reason, cids in cur_reasons.get(ch, {}).items():
                hits = len(cids & silent)
                if hits:
                    reasons[reason] = hits
            explained = sum(reasons.values())
            if len(silent) > explained:
                # No log covers these. Naming the gap is the point — silence
                # here is what sent us digging through the database by hand.
                reasons['no_reason_recorded'] = len(silent) - explained

            # WHICH conversations, not just how many. A count of dropped
            # customers you can't open is a statistic; the list is a worklist.
            # Capped, with the total alongside, so a bad day can't return
            # thousands of rows into a dashboard payload.
            silent_rows = []
            if silent:
                from app.models import User as CustomerUser
                for conv, handle in (
                    db.session.query(Conversation, CustomerUser.external_id)
                      .outerjoin(CustomerUser, CustomerUser.id == Conversation.user_id)
                      .filter(Conversation.id.in_(list(silent)))
                      .order_by(Conversation.last_message_at.desc().nullslast())
                      .limit(NO_REPLY_SAMPLE)
                      .all()
                ):
                    # Per-conversation reason where one was logged, so each row
                    # explains itself rather than sharing the channel's tally.
                    row_reason = next(
                        (r for r, cids in cur_reasons.get(ch, {}).items()
                         if conv.id in cids),
                        'no_reason_recorded',
                    )
                    silent_rows.append({
                        'conversation_id': conv.id,
                        'handle': handle,
                        'channel': conv.channel,
                        'status': conv.status,
                        'last_message_at': (conv.last_message_at.isoformat()
                                            if conv.last_message_at else None),
                        'reason': row_reason,
                    })
            channel_performance.append({
                'channel':        ch,
                'inbound':        inbound,
                'prev_inbound':   prev_inbound,
                'ai_replies':     int(row.ai) if row else 0,
                'human_replies':  int(row.human) if row else 0,
                'share':          round(100 * inbound / total_inbound_all, 1),
                'response_rate':  round(len(elig & ans) / len(elig), 4) if elig else None,
                'handled_convos': len(elig),
                'answered_convos':  len(elig & ans),
                'human_convos':     len(picked_up),
                'no_reply_convos':  len(silent),
                'no_reply_reasons': reasons,
                'no_reply_sample':  silent_rows,   # capped at NO_REPLY_SAMPLE
                'escalated':      len(cur_esc.get(ch, set())),
                'avg_response_time_ms': (
                    int(row.avg_ms) if (row and row.avg_ms is not None) else None
                ),
            })
        channel_performance.sort(key=lambda c: c['inbound'], reverse=True)
    except Exception as e:
        log_event("warn", "analytics.channel_performance_failed", str(e))
        channel_performance = []

    # ── Human queue: how fast waiting conversations get picked up ─────────
    # The counterweight to letting agents self-claim. Self-claim is faster
    # than routing everything through a supervisor, but it can be cherry-
    # picked, so measure it rather than gating it.
    #
    # Auto-assigned conversations are excluded from the timing: handoff.py
    # assigns them in the same transaction as the escalation, so their
    # time-to-claim is ~0 and would drown out the ones that actually queued.
    # They're reported as a separate count instead.
    try:
        queued_since = func.coalesce(Conversation.escalated_at,
                                     Conversation.ai_disabled_at,
                                     Conversation.last_message_at)
        claimed_q = _scope_filter(
            db.session.query(
                Conversation.assigned_by,
                func.extract('epoch', Conversation.assigned_at - queued_since),
            ).filter(Conversation.assigned_at >= win.start)
             .filter(Conversation.assigned_at < win.end)
             .filter(Conversation.assigned_to.isnot(None)),
            Conversation, user,
        )
        auto_claims, self_claim_waits = 0, []
        for assigned_by, secs in claimed_q.all():
            if assigned_by is None:
                auto_claims += 1
            elif secs is not None and secs >= 0:
                self_claim_waits.append(float(secs))

        self_claim_waits.sort()
        median_wait = (self_claim_waits[len(self_claim_waits) // 2]
                       if self_claim_waits else None)

        # Right now, not in-window: a queue you can't see is the problem.
        from app.assignment import find_unclaimed
        waiting = find_unclaimed(threshold_minutes=0)
        if user.role == 'agent':
            waiting = []          # roster management isn't an agent's view

        queue = {
            'auto_assigned':        auto_claims,
            'self_claimed':         len(self_claim_waits),
            'median_claim_seconds': int(median_wait) if median_wait is not None else None,
            'slowest_claim_seconds': int(self_claim_waits[-1]) if self_claim_waits else None,
            'unclaimed_now':        len(waiting),
            'longest_wait_minutes': waiting[0][1] if waiting else 0,
        }
    except Exception as e:
        log_event("warn", "analytics.queue_failed", str(e))
        queue = {'auto_assigned': 0, 'self_claimed': 0, 'median_claim_seconds': None,
                 'slowest_claim_seconds': None, 'unclaimed_now': 0, 'longest_wait_minutes': 0}

    # ── Top products (by ACTUAL product recommended) ──────────────────────
    # product_url carries the real handle (…/products/{handle}?utm=…), whereas
    # product_keyword is just the raw search word. Count by handle, then map to
    # the real product name from the cache.
    from app.models import ProductCache
    handle_expr = func.split_part(
        func.split_part(Message.product_url, '/products/', 2), '?', 1
    )
    # DISTINCT conversations, not messages — recommending the same item five
    # times in one thread is one customer asking, not five.
    prod_rows = _scope_filter(
        db.session.query(handle_expr.label('handle'),
                         func.count(func.distinct(Message.conversation_id)))
        .filter(Message.created_at >= cutoff)
        .filter(Message.product_url.isnot(None))
        .group_by(handle_expr),
        Message, user,
    ).all()

    handle_counts = {h: int(c) for h, c in prod_rows if h}
    top_handles = sorted(handle_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    info_by_handle = {}
    if top_handles:
        info_rows = (
            ProductCache.query
            .with_entities(ProductCache.handle, ProductCache.name, ProductCache.price, ProductCache.images)
            .filter(ProductCache.handle.in_([h for h, _ in top_handles]))
            .all()
        )
        info_by_handle = {
            h: {
                'name': n,
                'price': str(p) if p is not None else None,
                'image': (imgs[0] if imgs else None),
            }
            for h, n, p, imgs in info_rows
        }

    top_products = [
        {
            'name': (info_by_handle.get(h) or {}).get('name') or h,
            'mentions': cnt,
            'handle': h,
            'price': (info_by_handle.get(h) or {}).get('price'),
            'image': (info_by_handle.get(h) or {}).get('image'),
        }
        for h, cnt in top_handles
    ]

    return jsonify({
        'window_days': days,
        # Echo the resolved window so the UI can label it truthfully instead of
        # assuming what "this month" covers. Local dates; period is null in
        # rolling ?days=N mode.
        'period': win.period,
        'window_start': win.dates[0].isoformat() if win.dates else None,
        'window_end': win.dates[-1].isoformat() if win.dates else None,
        'previous_start': (win.prev_start + win.utc_offset).date().isoformat(),
        'scope': 'agent' if user.role == 'agent' else 'company',
        'kpis': kpis,
        'conversion': conversion,
        'weekly': weekly,
        'intent_breakdown': intent_breakdown,
        'channel_split': channel_split,
        'channel_performance': channel_performance,
        'queue': queue,
        'top_products': top_products,
        'failure_breakdown': failure_breakdown,
    }), 200


# ─────────────────────────────────────────────
# GET /api/analytics/agents — supervisor + admin only
# ─────────────────────────────────────────────

@analytics_bp.route('/analytics/agents', methods=['GET'])
@jwt_required()
def per_agent():
    """
    Per-agent breakdown for the supervisor drill-down. One row per active
    agent, plus totals scoped to their assigned conversations.
    """
    user, err = _require_user()
    if err:
        return err
    if user.role not in {'admin', 'supervisor'}:
        return jsonify({'error': 'Forbidden'}), 403

    try:
        days, cutoff = _window()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    agents = (AuthUser.query
              .filter(AuthUser.role == 'agent', AuthUser.status == 'active')
              .all())

    out = []
    for a in agents:
        conv_ids = (
            db.session.query(Conversation.id)
            .filter(Conversation.assigned_to == a.id)
            .subquery()
        )
        assigned_total = (
            Conversation.query.filter(Conversation.assigned_to == a.id).count()
        )
        active_total = (
            Conversation.query
            .filter(Conversation.assigned_to == a.id)
            .filter(Conversation.status != 'resolved')
            .count()
        )
        resolved_in_window = (
            Conversation.query
            .filter(Conversation.assigned_to == a.id)
            .filter(Conversation.resolved_at >= cutoff)
            .count()
        )
        human_replies = (
            Message.query
            .filter(Message.sender == 'human')
            .filter(Message.sender_id == a.id)
            .filter(Message.created_at >= cutoff)
            .count()
        )
        ai_replies_on_theirs = (
            Message.query
            .filter(Message.conversation_id.in_(conv_ids))
            .filter(Message.sender == 'ai')
            .filter(Message.created_at >= cutoff)
            .count()
        )
        out.append({
            'agent': a.to_brief(),
            'assigned_total': assigned_total,
            'active_total': active_total,
            'resolved_in_window': resolved_in_window,
            'human_replies_in_window': human_replies,
            'ai_replies_on_their_conversations': ai_replies_on_theirs,
        })

    return jsonify({
        'window_days': days,
        'agents': sorted(out, key=lambda r: r['active_total'], reverse=True),
    }), 200