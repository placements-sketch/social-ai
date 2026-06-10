"""
app/orders.py
Orders cache — mirrors Shopify orders locally for fast customer history reads.

Endpoints (JWT-protected, /api prefix):
  POST /api/orders/sync         mirror Shopify -> orders_cache
                                (and refresh denormalized fields on customers_cache)
  GET  /api/orders/sync/status  last_synced_at + count + stale flag
"""

from datetime import datetime, timedelta
from decimal import Decimal
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app import db
from app.models import AuthUser, OrderCache, CustomerCache
from app.auth import log_audit, current_user_id
from app.integrations.shopify import list_all_orders

orders_bp = Blueprint('orders', __name__, url_prefix='/api')

STALE_AFTER = timedelta(hours=12)


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


@orders_bp.route('/orders/sync', methods=['POST'])
@jwt_required()
def sync_orders():
    """Mirror Shopify orders, then recompute customer summaries from real data."""
    current_user = AuthUser.query.get(current_user_id())
    if current_user is None:
        return jsonify({'error': 'User not found'}), 404

    try:
        shopify_orders = list_all_orders()
    except Exception as e:
        return jsonify({'ok': False, 'reason': 'shopify_error', 'message': str(e)}), 502

    snapshot = {o['shopify_id']: o for o in shopify_orders}
    cached = {o.shopify_order_id: o for o in OrderCache.query.all()}

    now = datetime.utcnow()
    added = updated = removed = 0

    # Inserts + updates
    for spid, snap in snapshot.items():
        order_date = _parse_dt(snap.get('order_date'))
        if spid in cached:
            row = cached[spid]
            row.shopify_customer_id = snap.get('shopify_customer_id')
            row.order_number = snap.get('order_number')
            row.total = Decimal(str(snap.get('total', 0)))
            row.currency = snap.get('currency')
            row.items_count = snap.get('items_count', 0)
            row.products = snap.get('products', [])
            row.financial_status = snap.get('financial_status')
            row.fulfillment_status = snap.get('fulfillment_status')
            row.order_date = order_date
            row.cached_at = now
            updated += 1
        else:
            db.session.add(OrderCache(
                shopify_order_id=spid,
                shopify_customer_id=snap.get('shopify_customer_id'),
                order_number=snap.get('order_number'),
                total=Decimal(str(snap.get('total', 0))),
                currency=snap.get('currency'),
                items_count=snap.get('items_count', 0),
                products=snap.get('products', []),
                financial_status=snap.get('financial_status'),
                fulfillment_status=snap.get('fulfillment_status'),
                order_date=order_date,
                cached_at=now,
            ))
            added += 1

    # Deletes
    for spid, row in cached.items():
        if spid not in snapshot:
            db.session.delete(row)
            removed += 1

    db.session.flush()  # so the aggregates below see new rows

    # Recompute customer summaries from real order data
    customer_aggs = dict(
        db.session.query(
            OrderCache.shopify_customer_id,
            func.count(OrderCache.id),
            func.coalesce(func.sum(OrderCache.total), 0),
            func.max(OrderCache.order_date),
            func.min(OrderCache.order_date),
        )
        .filter(OrderCache.shopify_customer_id.isnot(None))
        .group_by(OrderCache.shopify_customer_id)
        .all()
    )

    customers_updated = 0
    for customer in CustomerCache.query.all():
        agg = customer_aggs.get(customer.shopify_customer_id)
        if agg:
            count, total_spent, last_date, first_date = agg
            customer.total_orders = count
            customer.total_spent = Decimal(str(total_spent))
            customer.last_order_date = last_date
            customer.first_order_date = first_date
        else:
            customer.total_orders = 0
            customer.total_spent = Decimal('0')
            customer.last_order_date = None
            customer.first_order_date = None
        customers_updated += 1

    db.session.commit()

    log_audit(
        current_user.id, 'sync_orders',
        resource_type='orders', resource_id=None,
        changes={'added': added, 'updated': updated, 'removed': removed,
                 'customers_refreshed': customers_updated},
    )

    return jsonify({
        'ok': True,
        'added_count': added,
        'updated_count': updated,
        'removed_count': removed,
        'customers_refreshed': customers_updated,
        'synced_at': now.isoformat(),
        'total_orders': OrderCache.query.count(),
    }), 200


@orders_bp.route('/orders/sync/status', methods=['GET'])
@jwt_required()
def orders_sync_status():
    last = db.session.query(func.max(OrderCache.cached_at)).scalar()
    count = OrderCache.query.count()
    stale = (last is None) or (datetime.utcnow() - last) > STALE_AFTER
    return jsonify({
        'last_synced_at': last.isoformat() if last else None,
        'order_count': count,
        'stale': stale,
        'stale_threshold_hours': int(STALE_AFTER.total_seconds() // 3600),
    }), 200