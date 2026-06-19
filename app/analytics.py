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
from app.models import AuthUser, Conversation, Message
from app.auth import current_user_id

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
        failed         = max(0, inbound - ai_repl)
        ai_success     = (ai_repl / inbound) if inbound else 0.0

        return {
            'messages_total':      total_msgs,
            'inbound_total':       inbound,
            'ai_replies_total':    ai_repl,
            'human_replies_total': human_repl,
            'failed_responses':    failed,
            'avg_response_time_ms': int(avg_ms) if avg_ms else None,
            'ai_success_rate':     round(ai_success, 4),
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
    total_intents = sum(intent_counts.values()) or 1
    intent_breakdown = sorted(
        [{'name': k, 'count': v, 'percent': round(100 * v / total_intents, 1)}
         for k, v in intent_counts.items()],
        key=lambda x: x['count'], reverse=True,
    )[:6]  # top 6 fits the donut chart legend nicely

    # ── Channel split ─────────────────────────────────────────────────────
    channel_q = _scope_filter(
        db.session.query(Message.channel, func.count(Message.id))
        .filter(Message.created_at >= cutoff)
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

    # ── Top products (by product_keyword mention) ─────────────────────────
    prod_q = _scope_filter(
        db.session.query(Message.product_keyword, func.count(Message.id))
        .filter(Message.created_at >= cutoff)
        .filter(Message.product_keyword.isnot(None))
        .group_by(Message.product_keyword),
        Message, user,
    )
    top_products = sorted(
        [{'name': name, 'mentions': int(c)} for name, c in prod_q.all() if name],
        key=lambda x: x['mentions'], reverse=True,
    )[:5]

    return jsonify({
        'window_days': days,
        'scope': 'agent' if user.role == 'agent' else 'company',
        'kpis': kpis,
        'weekly': weekly,
        'intent_breakdown': intent_breakdown,
        'channel_split': channel_split,
        'top_products': top_products,
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