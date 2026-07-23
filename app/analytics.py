"""
app/analytics.py
Analytics endpoints — KPIs, charts data, per-agent breakdown.

Endpoints (JWT-protected, /api prefix):
  GET /api/analytics/summary    aggregated data for the Analytics page
  GET /api/analytics/agents     per-agent breakdown (supervisor + admin only)

Shared query params:
  ?days=N           time window (default 7, max 365)

Role-aware scoping (summary endpoint):
  - admin, supervisor : data for all conversations company-wide
  - agent             : data scoped to conversations assigned to them
"""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func, case

from app import db
from app.models import AuthUser, Conversation, Message, Channel
from app.auth import current_user_id
from app.utils.logger import log_event

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')


MAX_DAYS = 365
DEFAULT_DAYS = 7


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _require_user():
    user = AuthUser.query.get(current_user_id())
    if not user:
        return None, (jsonify({'error': 'User not found'}), 404)
    return user, None


def _window():
    """Resolve (days, cutoff_datetime) from ?days=N (default 7, capped at MAX_DAYS)."""
    days = request.args.get('days', default=DEFAULT_DAYS, type=int) or DEFAULT_DAYS
    if days < 1:
        days = DEFAULT_DAYS
    if days > MAX_DAYS:
        days = MAX_DAYS
    cutoff = datetime.utcnow() - timedelta(days=days)
    return days, cutoff


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
        .subquery()
    )
    if model is Conversation:
        return query.filter(Conversation.id.in_(assigned_conv_ids))
    if model is Message:
        return query.filter(Message.conversation_id.in_(assigned_conv_ids))
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

    days, cutoff = _window()

    # ── KPIs: current window + previous window (same size) ───────────────
    # The frontend picks "today", "week", or "month" via ?days=1, 7, or 30.
    # We return both current and previous so the cards can show change.

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

        total_convs    = conv_q.count()
        human_override = conv_q.filter(
            Conversation.ai_enabled == False,
            Conversation.handoff_reason.is_(None),
        ).count()
        escalated      = conv_q.filter(Conversation.handoff_reason.isnot(None)).count()

        # ── AI eligibility: inbound on convs where AI was supposed to reply ─
        # A message is "AI-eligible" iff its conversation has ai_enabled=True
        # AND its channel has enabled=True (or has no Channel row — fail open).
        # Disabled channels are admin-suppressed and excluded from failure count.
        disabled_channels = (
            db.session.query(Channel.channel)
            .filter(Channel.enabled == False)
            .subquery()
        )
        ai_eligible_conv_ids = (
            db.session.query(Conversation.id)
            .filter(Conversation.ai_enabled == True)
            .subquery()
        )
        eligible_msg_q = _scope_filter(
            Message.query
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'inbound')
              .filter(Message.conversation_id.in_(ai_eligible_conv_ids))
              .filter(~Message.channel.in_(disabled_channels)),
            Message, user,
        )
        eligible_inbound = eligible_msg_q.count()

        eligible_ai_replies_q = _scope_filter(
            Message.query
              .filter(Message.created_at >= start_dt)
              .filter(Message.created_at < end_dt)
              .filter(Message.direction == 'outbound')
              .filter(Message.sender == 'ai')
              .filter(Message.conversation_id.in_(ai_eligible_conv_ids))
              .filter(~Message.channel.in_(disabled_channels)),
            Message, user,
        )
        eligible_ai_replies = eligible_ai_replies_q.count()

        # Real AI failures only: the generator threw and fell back to a mock
        # reply. This used to be (eligible_inbound - ai_replies), which counted
        # normal coalescing — 3 messages answered by 1 reply scored 2
        # "failures" — so the number climbed even when nothing was wrong.
        from app.models import Log
        failed = (db.session.query(func.count(Log.id))
                  .filter(Log.source == 'ai.generator.failure')
                  .filter(Log.created_at >= start_dt)
                  .filter(Log.created_at < end_dt)
                  .scalar() or 0)

        # Still worth tracking separately: inbound with no AI reply. Mostly
        # legitimate (coalesced bursts, skipped non-question comments), so it
        # is NOT a failure count.
        unanswered = max(0, eligible_inbound - eligible_ai_replies)
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
                  .filter(Message.conversation_id.in_(ai_eligible_conv_ids))
                  .filter(~Message.channel.in_(disabled_channels)),
                Message, user,
            ).distinct().all()
        )
        response_rate = (
            len(inbound_conv_ids & answered_conv_ids) / len(inbound_conv_ids)
        ) if inbound_conv_ids else 0.0

        # ── SUCCESS rate ──────────────────────────────────────────────────
        # A conversation "succeeds" when the AI handled it WITHOUT escalating
        # to a human AND the customer engaged (multi-turn OR ordered).
        #   denominator = AI-handled conversations active in the window
        #                 (never escalated: handoff_reason IS NULL)
        #   numerator   = those with >=2 inbound msgs (multi-turn) OR an
        #                 attributed order.
        from app.models import ConversionAttribution

        handled_conv_ids_q = _scope_filter(
            Conversation.query
                .filter(Conversation.last_message_at >= start_dt)
                .filter(Conversation.last_message_at < end_dt)
                .filter(Conversation.handoff_reason.is_(None)),   # never escalated
            Conversation, user,
        )
        handled_conv_ids = [c.id for c in handled_conv_ids_q.with_entities(Conversation.id).all()]
        handled_total = len(handled_conv_ids)

        engaged_total = 0
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
            engaged_total = len(multiturn_ids | ordered_ids)

        success_rate = (engaged_total / handled_total) if handled_total else 0.0

        return {
            'messages_total':      total_msgs,
            'inbound_total':       inbound,
            'ai_replies_total':    ai_repl,
            'human_replies_total': human_repl,
            'failed_responses':    failed,
            'unanswered_inbound':  unanswered,
            'avg_response_time_ms': int(avg_ms) if avg_ms is not None else None,
            'ai_response_rate':    round(response_rate, 4),   # renamed from ai_success_rate
            'ai_success_rate':     round(success_rate, 4),    # NEW — real success
            'ai_handled_total':    handled_total,             # denominator, for context
            'ai_engaged_total':    engaged_total,             # numerator, for context
            'human_override_total': human_override,
            'escalated_total':     escalated,
            'conversations_total': total_convs,
        }

    now = datetime.utcnow()
    current_start = cutoff
    current_end   = now
    previous_start = cutoff - timedelta(days=days)
    previous_end   = cutoff

    current  = _kpis_for_window(current_start, current_end)
    previous = _kpis_for_window(previous_start, previous_end)

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
        recommended_conv_ids = set(
            cid for (cid,) in db.session.query(Message.conversation_id)
              .filter(Message.utm_token.isnot(None))
              .filter(Message.created_at >= cutoff)
              .filter(Message.created_at < now)
              .distinct().all()
            if cid is not None
        )
        recommended_convos = len(recommended_conv_ids)

        converted_convos = 0
        attributed_orders = 0
        attributed_revenue_raw = 0
        if recommended_conv_ids:
            conv_rows = (
                db.session.query(ConversionAttribution)
                  .filter(ConversionAttribution.conversation_id.in_(recommended_conv_ids))
                  .all()
            )
            converted_convos = len({r.conversation_id for r in conv_rows})
            attributed_orders = len(conv_rows)
            attributed_revenue_raw = sum(float(r.order_total or 0) for r in conv_rows)

        from app.customers import ex_vat
        attributed_revenue = ex_vat(attributed_revenue_raw)
        conversion = {
            'recommended_conversations': recommended_convos,
            'converted_conversations':   converted_convos,
            'conversion_rate':           round((converted_convos / recommended_convos) if recommended_convos else 0.0, 4),
            'attributed_orders':         attributed_orders,
            'attributed_revenue':        attributed_revenue,
        }
    except Exception as e:
        log_event("warn", "analytics.conversion_failed", str(e))
        conversion = {
            'recommended_conversations': 0,
            'converted_conversations':   0,
            'conversion_rate':           0.0,
            'attributed_orders':         0,
            'attributed_revenue':        0.0,
        }

    # ── AI failure breakdown (why replies failed) ────────────────────────
    # Groups ai.generator.failure logs in the window by their structured
    # `reason`. Wrapped so a query issue can't 500 the dashboard.
    try:
        from app.models import Log
        from sqlalchemy import text
        reason_expr = text("payload ->> 'reason'")
        rows = (db.session.query(reason_expr, func.count(Log.id))
                .filter(Log.source == 'ai.generator.failure')
                .filter(Log.created_at >= cutoff)
                .filter(Log.created_at < now)
                .group_by(reason_expr)
                .all())
        failure_breakdown = [
            {'reason': (r or 'unknown'), 'count': int(c)}
            for r, c in sorted(rows, key=lambda x: x[1], reverse=True)
        ]
    except Exception as e:
        log_event("warn", "analytics.failure_breakdown_failed", str(e))
        failure_breakdown = []
        
    except Exception as e:
        log_event("warn", "analytics.conversion_failed", str(e))
        conversion = {
            'recommended_conversations': 0,
            'converted_conversations':   0,
            'conversion_rate':           0.0,
            'attributed_orders':         0,
            'attributed_revenue':        0.0,
        }

    # Keep these in scope for the chart/intent/etc. blocks below
    inbound_total = current['inbound_total']
    ai_replies    = current['ai_replies_total']

    # ── Weekly chart data ─────────────────────────────────────────────────
    # One row per day in the window with both totals and per-channel inbound
    # counts (used for the multi-line graph on the Dashboard).
    weekly_q = _scope_filter(
        db.session.query(
            func.date(Message.created_at).label('day'),
            func.count(case((Message.direction == 'inbound', 1))).label('inbound'),
            func.count(case((db.and_(Message.direction == 'outbound',
                                     Message.sender == 'ai'), 1))).label('ai_replied'),
        ).filter(Message.created_at >= cutoff)
         .group_by(func.date(Message.created_at)),
        Message, user,
    )
    weekly_rows = {row.day: (row.inbound, row.ai_replied) for row in weekly_q.all()}

    # Per-channel-per-day counts for the Dashboard channel graph.
    # We group all instagram_* into 'instagram', facebook_* into 'facebook', etc.
    # Three counts per (day, channel): inbound, ai_replied, human_replied
    channel_group = case(
        (Message.channel.like('instagram%'), 'instagram'),
        (Message.channel.like('facebook%'),  'facebook'),
        (Message.channel.like('tiktok%'),    'tiktok'),
        (Message.channel == 'whatsapp',      'whatsapp'),
        else_='other',
    )
    per_channel_q = _scope_filter(
        db.session.query(
            func.date(Message.created_at).label('day'),
            channel_group.label('channel'),
            func.count(case((Message.direction == 'inbound', 1))).label('inbound'),
            func.count(case((db.and_(Message.direction == 'outbound',
                                     Message.sender == 'ai'), 1))).label('ai_replied'),
            func.count(case((db.and_(Message.direction == 'outbound',
                                     Message.sender == 'human'), 1))).label('human_replied'),
        ).filter(Message.created_at >= cutoff)
         .group_by(func.date(Message.created_at), channel_group),
        Message, user,
    )
    per_channel = {}
    for row in per_channel_q.all():
        per_channel.setdefault(row.day, {})[row.channel] = {
            'inbound': int(row.inbound),
            'ai_replied': int(row.ai_replied),
            'human_replied': int(row.human_replied),
        }

    # Fill missing days with zeros so the chart always has N points.
    weekly = []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date()
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
        'scope': 'agent' if user.role == 'agent' else 'company',
        'kpis': kpis,
        'conversion': conversion,
        'weekly': weekly,
        'intent_breakdown': intent_breakdown,
        'channel_split': channel_split,
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

    days, cutoff = _window()

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