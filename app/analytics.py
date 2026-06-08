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

    # ── KPIs ──────────────────────────────────────────────────────────────
    msg_q = _scope_filter(
        Message.query.filter(Message.created_at >= cutoff),
        Message, user,
    )

    total_messages = msg_q.count()
    inbound_total = msg_q.filter(Message.direction == 'inbound').count()
    ai_replies = msg_q.filter(
        Message.direction == 'outbound', Message.sender == 'ai'
    ).count()
    human_replies = msg_q.filter(
        Message.direction == 'outbound', Message.sender == 'human'
    ).count()

    # Avg AI response time over messages in window that have a timing.
    avg_response_ms = (
        _scope_filter(
            db.session.query(func.avg(Message.ai_response_time_ms))
            .filter(Message.created_at >= cutoff)
            .filter(Message.ai_response_time_ms.isnot(None)),
            Message, user,
        ).scalar()
    )

    # Override rate: conversations that ended up in human_override, divided by
    # all conversations with activity in the window.
    conv_q = _scope_filter(
        Conversation.query.filter(Conversation.last_message_at >= cutoff),
        Conversation, user,
    )
    total_convs = conv_q.count()
    overridden_convs = conv_q.filter(Conversation.status == 'human_override').count()
    override_rate = (overridden_convs / total_convs) if total_convs else 0.0

    # AI success rate: outbound AI replies / all outbound (proxy until we have
    # real success/failure signals from the AI call layer).
    total_outbound = ai_replies + human_replies
    ai_success_rate = (ai_replies / total_outbound) if total_outbound else 0.0

    kpis = {
        'messages_total': total_messages,
        'inbound_total': inbound_total,
        'ai_replies_total': ai_replies,
        'human_replies_total': human_replies,
        'avg_response_time_ms': int(avg_response_ms) if avg_response_ms else None,
        'ai_success_rate': round(ai_success_rate, 4),
        'override_rate': round(override_rate, 4),
        'conversations_total': total_convs,
        'human_override_total': overridden_convs,
    }

    # ── Weekly chart data ─────────────────────────────────────────────────
    # One row per day in the window: inbound count, AI-reply count.
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

    # Fill missing days with zeros so the chart always has N points.
    weekly = []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date()
        inb, ai_r = weekly_rows.get(d, (0, 0))
        weekly.append({
            'date': d.isoformat(),
            'day': d.strftime('%a'),
            'inbound': int(inb),
            'ai_replied': int(ai_r),
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