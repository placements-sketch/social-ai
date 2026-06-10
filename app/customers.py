"""
app/customers.py
Customer profiling — list, detail, overview, RFM segmentation.

Endpoints (JWT-protected, /api prefix):
  GET  /api/customers                  list (paginated, filterable, sortable)
  GET  /api/customers/<id>             single customer detail
  GET  /api/customers/<id>/orders      live order history from Shopify
  GET  /api/customers/overview         aggregates for the overview page
  POST /api/customers/sync             mirror Shopify -> customers_cache
  GET  /api/customers/sync/status      last_synced_at + stale flag

Segments computed on-the-fly:
  vip      — top 25% by spend, ordered in last 60 days
  loyal    — 5+ orders, ordered in last 60 days
  new      — joined in last 30 days OR 0-1 orders
  at_risk  — 2+ orders, last order 90-180 days ago
  churned  — 2+ orders, last order 180+ days ago
  regular  — anyone else with at least 1 order
"""

from datetime import datetime, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func, or_

from app import db
from app.models import AuthUser, CustomerCache
from app.auth import log_audit, current_user_id
from app.integrations.shopify import list_all_customers

customers_bp = Blueprint('customers', __name__, url_prefix='/api')


STALE_AFTER = timedelta(hours=12)
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


# ─────────────────────────────────────────────
# RFM Segmentation
# ─────────────────────────────────────────────

def compute_segment(customer, vip_spend_threshold):
    """Computes the RFM segment for a single customer dict/row."""
    total_orders = customer.total_orders or 0
    total_spent = float(customer.total_spent or 0)
    last_order = customer.last_order_date
    created = customer.shopify_created_at

    now = datetime.utcnow()

    days_since_order = (now - last_order).days if last_order else None
    days_since_join = (now - created).days if created else None

    if total_orders == 0:
        return 'new'
    if total_spent >= vip_spend_threshold and days_since_order is not None and days_since_order <= 60:
        return 'vip'
    if total_orders >= 5 and days_since_order is not None and days_since_order <= 60:
        return 'loyal'
    if days_since_order is not None and days_since_order > 180 and total_orders >= 2:
        return 'churned'
    if days_since_order is not None and days_since_order > 90 and total_orders >= 2:
        return 'at_risk'
    if total_orders <= 1 and days_since_join is not None and days_since_join <= 30:
        return 'new'
    return 'regular'


def _vip_threshold():
    """Compute the VIP spend threshold (top 25% of spenders) once per request."""
    p75 = (
        db.session.query(func.percentile_cont(0.75).within_group(CustomerCache.total_spent.asc()))
        .scalar()
    )
    return float(p75 or 50000)  # Fallback if no data


# ─────────────────────────────────────────────
# Serialization
# ─────────────────────────────────────────────

def _serialize_customer(c, vip_threshold):
    last_order = c.last_order_date
    days_since = (datetime.utcnow() - last_order).days if last_order else None
    return {
        'id': c.id,
        'shopify_customer_id': c.shopify_customer_id,
        'name': c.full_name,
        'first_name': c.first_name,
        'last_name': c.last_name,
        'email': c.email,
        'phone': c.phone,
        'location': c.city or c.country or 'Unknown',
        'accepts_marketing': c.accepts_marketing,
        'tags': c.tags or [],
        'total_orders': c.total_orders or 0,
        'total_spent': float(c.total_spent or 0),
        'aov': float(c.total_spent or 0) / c.total_orders if (c.total_orders or 0) > 0 else 0,
        'last_order_date': last_order.isoformat() if last_order else None,
        'days_since_last_order': days_since,
        'first_order_date': c.first_order_date.isoformat() if c.first_order_date else None,
        'created_at': c.shopify_created_at.isoformat() if c.shopify_created_at else None,
        'segment': compute_segment(c, vip_threshold),
    }


# ─────────────────────────────────────────────
# GET /api/customers
# ─────────────────────────────────────────────

@customers_bp.route('/customers', methods=['GET'])
@jwt_required()
def list_customers():
    page = max(1, request.args.get('page', default=1, type=int))
    per_page = min(MAX_PER_PAGE, max(1, request.args.get('per_page', default=DEFAULT_PER_PAGE, type=int)))
    search = request.args.get('search', type=str)
    segment_filter = request.args.get('segment', type=str)
    sort_by = request.args.get('sort_by', default='spent_desc', type=str)

    query = CustomerCache.query

    if search:
        like = f"%{search.strip()}%"
        query = query.filter(or_(
            CustomerCache.email.ilike(like),
            CustomerCache.first_name.ilike(like),
            CustomerCache.last_name.ilike(like),
            CustomerCache.phone.ilike(like),
        ))

    # Sort
    sort_map = {
        'spent_desc': CustomerCache.total_spent.desc(),
        'orders_desc': CustomerCache.total_orders.desc(),
        'recent': CustomerCache.last_order_date.desc().nullslast(),
        'name': CustomerCache.first_name.asc(),
    }
    query = query.order_by(sort_map.get(sort_by, CustomerCache.total_spent.desc()))

    # Filter by segment AFTER fetching (segment is computed, not stored)
    vip_threshold = _vip_threshold()
    all_rows = query.all()
    serialized = [_serialize_customer(c, vip_threshold) for c in all_rows]

    if segment_filter and segment_filter != 'all':
        serialized = [c for c in serialized if c['segment'] == segment_filter]

    total = len(serialized)
    start = (page - 1) * per_page
    paged = serialized[start:start + per_page]

    last = db.session.query(func.max(CustomerCache.cached_at)).scalar()
    stale = (last is None) or (datetime.utcnow() - last) > STALE_AFTER

    return jsonify({
        'customers': paged,
        'total': total,
        'page': page,
        'per_page': per_page,
        'last_synced_at': last.isoformat() if last else None,
        'stale': stale,
    }), 200


# ─────────────────────────────────────────────
# GET /api/customers/overview
# ─────────────────────────────────────────────

@customers_bp.route('/customers/overview', methods=['GET'])
@jwt_required()
def customers_overview():
    """Aggregated data for the Customers overview page."""
    customers = CustomerCache.query.all()
    if not customers:
        return jsonify({
            'kpis': {'total_customers': 0, 'new_this_month': 0, 'repeat_customers': 0,
                     'retention_rate': 0, 'total_revenue': 0, 'avg_aov': 0},
            'segment_counts': {},
            'top_spenders': [], 'top_frequent': [],
            'aov_by_month': [], 'top_products': [],
        }), 200

    vip_threshold = _vip_threshold()
    now = datetime.utcnow()

    # KPIs
    total = len(customers)
    total_revenue = float(sum(c.total_spent or 0 for c in customers))
    total_orders = sum(c.total_orders or 0 for c in customers)
    avg_aov = (total_revenue / total_orders) if total_orders else 0
    new_this_month = sum(
        1 for c in customers
        if c.shopify_created_at and (now - c.shopify_created_at).days <= 30
    )
    repeat = sum(1 for c in customers if (c.total_orders or 0) >= 2)
    retention_rate = (repeat / total) if total else 0

    # Segment counts
    segments = [compute_segment(c, vip_threshold) for c in customers]
    segment_counts = {}
    for s in segments:
        segment_counts[s] = segment_counts.get(s, 0) + 1

    # Top spenders (5)
    top_spenders = sorted(customers, key=lambda c: float(c.total_spent or 0), reverse=True)[:5]
    top_spenders_out = [_serialize_customer(c, vip_threshold) for c in top_spenders]

    # Top frequent (5)
    top_frequent = sorted(customers, key=lambda c: c.total_orders or 0, reverse=True)[:5]
    top_frequent_out = [_serialize_customer(c, vip_threshold) for c in top_frequent]

    # AOV by month — last 6 months (placeholder until orders_cache exists)
    # For now: compute from customers' last_order_date as a proxy
    months_out = []
    for i in range(5, -1, -1):
        month_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        in_month = [c for c in customers
                    if c.last_order_date and month_start <= c.last_order_date < next_month]
        revenue = float(sum(c.total_spent or 0 for c in in_month))
        orders = sum(c.total_orders or 0 for c in in_month)
        months_out.append({
            'month': month_start.strftime('%b'),
            'aov': round(revenue / orders) if orders else 0,
            'orders': orders,
        })

    return jsonify({
        'kpis': {
            'total_customers': total,
            'new_this_month': new_this_month,
            'repeat_customers': repeat,
            'retention_rate': round(retention_rate, 4),
            'total_revenue': total_revenue,
            'avg_aov': round(avg_aov),
        },
        'segment_counts': segment_counts,
        'top_spenders': top_spenders_out,
        'top_frequent': top_frequent_out,
        'aov_by_month': months_out,
        'top_products': [],  # Will populate from orders_cache when added
    }), 200


# ─────────────────────────────────────────────
# GET /api/customers/<id>
# ─────────────────────────────────────────────

@customers_bp.route('/customers/<int:customer_id>', methods=['GET'])
@jwt_required()
def get_customer(customer_id):
    c = CustomerCache.query.get(customer_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404
    vip_threshold = _vip_threshold()
    return jsonify({'customer': _serialize_customer(c, vip_threshold)}), 200


# ─────────────────────────────────────────────
# GET /api/customers/<id>/orders
# ─────────────────────────────────────────────

@customers_bp.route('/customers/<int:customer_id>/orders', methods=['GET'])
@jwt_required()
def customer_orders(customer_id):
    """Order history from local orders_cache (synced separately via /api/orders/sync)."""
    from app.models import OrderCache

    c = CustomerCache.query.get(customer_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404

    rows = (OrderCache.query
            .filter_by(shopify_customer_id=c.shopify_customer_id)
            .order_by(OrderCache.order_date.desc().nullslast())
            .all())

    orders = [{
        'id': r.shopify_order_id,
        'order_number': r.order_number,
        'date': r.order_date.isoformat() if r.order_date else None,
        'total': float(r.total or 0),
        'currency': r.currency,
        'items': r.items_count,
        'products': r.products or [],
        'status': r.fulfillment_status or r.financial_status or 'pending',
    } for r in rows]

    return jsonify({'orders': orders, 'total': len(orders)}), 200


# ─────────────────────────────────────────────
# POST /api/customers/sync
# ─────────────────────────────────────────────

@customers_bp.route('/customers/sync', methods=['POST'])
@jwt_required()
def sync_customers():
    current_user = AuthUser.query.get(current_user_id())
    if current_user is None:
        return jsonify({'error': 'User not found'}), 404

    try:
        shopify_customers = list_all_customers()
    except Exception as e:
        return jsonify({'ok': False, 'reason': 'shopify_error', 'message': str(e)}), 502

    snapshot = {str(sc['shopify_id']): sc for sc in shopify_customers}
    cached = {c.shopify_customer_id: c for c in CustomerCache.query.all()}

    now = datetime.utcnow()
    added = updated = removed = 0

    def parse_dt(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return None

    # Inserts + updates
    for spid, snap in snapshot.items():
        last_order = parse_dt(snap.get('updated_at'))  # proxy until orders_cache exists
        if spid in cached:
            row = cached[spid]
            row.email = snap.get('email')
            row.first_name = snap.get('first_name')
            row.last_name = snap.get('last_name')
            row.phone = snap.get('phone')
            row.city = snap.get('city')
            row.country = snap.get('country')
            row.accepts_marketing = snap.get('accepts_marketing', False)
            row.tags = snap.get('tags', [])
            row.total_orders = snap.get('total_orders', 0)
            row.total_spent = Decimal(str(snap.get('total_spent', 0)))
            row.last_order_date = last_order if (row.total_orders or 0) > 0 else None
            row.shopify_created_at = parse_dt(snap.get('shopify_created_at'))
            row.cached_at = now
            updated += 1
        else:
            new_row = CustomerCache(
                shopify_customer_id=spid,
                email=snap.get('email'),
                first_name=snap.get('first_name'),
                last_name=snap.get('last_name'),
                phone=snap.get('phone'),
                city=snap.get('city'),
                country=snap.get('country'),
                accepts_marketing=snap.get('accepts_marketing', False),
                tags=snap.get('tags', []),
                total_orders=snap.get('total_orders', 0),
                total_spent=Decimal(str(snap.get('total_spent', 0))),
                last_order_date=last_order if (snap.get('total_orders') or 0) > 0 else None,
                shopify_created_at=parse_dt(snap.get('shopify_created_at')),
                cached_at=now,
            )
            db.session.add(new_row)
            added += 1

    # Deletes
    for spid, row in cached.items():
        if spid not in snapshot:
            db.session.delete(row)
            removed += 1

    db.session.commit()

    log_audit(
        current_user.id, 'sync_customers',
        resource_type='customers', resource_id=None,
        changes={'added': added, 'updated': updated, 'removed': removed},
    )

    return jsonify({
        'ok': True,
        'added_count': added,
        'updated_count': updated,
        'removed_count': removed,
        'synced_at': now.isoformat(),
        'total_customers': CustomerCache.query.count(),
    }), 200


# ─────────────────────────────────────────────
# GET /api/customers/sync/status
# ─────────────────────────────────────────────

@customers_bp.route('/customers/sync/status', methods=['GET'])
@jwt_required()
def customers_sync_status():
    last = db.session.query(func.max(CustomerCache.cached_at)).scalar()
    count = CustomerCache.query.count()
    stale = (last is None) or (datetime.utcnow() - last) > STALE_AFTER
    return jsonify({
        'last_synced_at': last.isoformat() if last else None,
        'customer_count': count,
        'stale': stale,
        'stale_threshold_hours': int(STALE_AFTER.total_seconds() // 3600),
    }), 200