"""
app/orders.py
Orders cache — mirrors Shopify orders locally for fast customer history reads.

Endpoints (JWT-protected, /api prefix):
  POST /api/orders/sync         async — mirror Shopify -> orders_cache and
                                refresh denormalized aggregates on customers_cache
  GET  /api/orders/sync/status  last_synced_at + count + stale flag + current_job
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
from app.sync_jobs import start_background_job, get_latest_job

orders_bp = Blueprint('orders', __name__, url_prefix='/api')

STALE_AFTER = timedelta(hours=12)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _parse_dt(s):
    """ISO 8601 parser that strips tz to a naive UTC datetime (matches DB cols)."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _truncate(value, max_len):
    """Coerce to string and clip to max_len. None → None."""
    if value is None:
        return None
    s = str(value)
    return s[:max_len] if len(s) > max_len else s


# ─────────────────────────────────────────────
# POST /api/orders/sync — async background job
# ─────────────────────────────────────────────

@orders_bp.route('/orders/sync', methods=['POST'])
@jwt_required()
def sync_orders():
    """
    Kick off a background job that mirrors Shopify orders into orders_cache
    AND recomputes customer aggregates from real order data.
    Returns 202 + job_id immediately. Frontend polls /api/orders/sync/status.
    """
    current_user = AuthUser.query.get(current_user_id())
    if current_user is None:
        return jsonify({'error': 'User not found'}), 404

    # Capture the user ID as a plain int — safe to use inside the background
    # thread where the ORM object would be detached from any session.
    user_id = current_user.id

    def do_sync(job):
        # ── Step 1: fetch from Shopify ──────────────────────────────────
        job.progress = "Fetching orders from Shopify..."
        db.session.commit()
        shopify_orders = list_all_orders()

        snapshot = {str(o['shopify_id']): o for o in shopify_orders}
        cached = {o.shopify_order_id: o for o in OrderCache.query.all()}

        now = datetime.utcnow()
        added = updated = removed = 0

        # ── Step 2: chunked upsert ──────────────────────────────────────
        CHUNK = 500
        items = list(snapshot.items())
        total_items = len(items)

        job.progress = f"Upserting 0 / {total_items:,} orders..."
        db.session.commit()

        for chunk_start in range(0, total_items, CHUNK):
            for spid, snap in items[chunk_start:chunk_start + CHUNK]:
                order_date = _parse_dt(snap.get('order_date'))
                if spid in cached:
                    row = cached[spid]
                    row.shopify_customer_id = _truncate(snap.get('shopify_customer_id'), 64)
                    row.order_number        = _truncate(snap.get('order_number'),         64)
                    row.total               = Decimal(str(snap.get('total', 0)))
                    row.currency            = _truncate(snap.get('currency'),              8)
                    row.items_count         = snap.get('items_count', 0)
                    row.products            = snap.get('products', [])
                    row.financial_status    = _truncate(snap.get('financial_status'),     32)
                    row.fulfillment_status  = _truncate(snap.get('fulfillment_status'),   32)
                    row.order_date          = order_date
                    row.cached_at           = now
                    updated += 1
                else:
                    db.session.add(OrderCache(
                        shopify_order_id=spid,
                        shopify_customer_id=_truncate(snap.get('shopify_customer_id'), 64),
                        order_number=_truncate(snap.get('order_number'),                64),
                        total=Decimal(str(snap.get('total', 0))),
                        currency=_truncate(snap.get('currency'),                         8),
                        items_count=snap.get('items_count', 0),
                        products=snap.get('products', []),
                        financial_status=_truncate(snap.get('financial_status'),        32),
                        fulfillment_status=_truncate(snap.get('fulfillment_status'),    32),
                        order_date=order_date,
                        cached_at=now,
                    ))
                    added += 1
            db.session.commit()
            processed = min(chunk_start + CHUNK, total_items)
            job.progress = f"Upserted {processed:,} / {total_items:,} orders..."
            db.session.commit()

        # ── Step 3: chunked deletes ─────────────────────────────────────
        to_delete = [row for spid, row in cached.items() if spid not in snapshot]
        for d_start in range(0, len(to_delete), CHUNK):
            for row in to_delete[d_start:d_start + CHUNK]:
                db.session.delete(row)
                removed += 1
            db.session.commit()

        # ── Step 4: recompute customer aggregates from real order data ──
        job.progress = "Recomputing customer aggregates..."
        db.session.commit()

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
        # Touch customers in chunks too — 161k rows in one transaction is rough.
        offset = 0
        while True:
            batch = (CustomerCache.query
                     .order_by(CustomerCache.id.asc())
                     .offset(offset)
                     .limit(CHUNK)
                     .all())
            if not batch:
                break

            for customer in batch:
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
            offset += CHUNK
            job.progress = f"Recomputed {customers_updated:,} customer aggregates..."
            db.session.commit()

        # ── Step 5: audit log (use captured user_id, not ORM object) ────
        log_audit(
            user_id, 'sync_orders',
            resource_type='orders', resource_id=None,
            changes={'added': added, 'updated': updated, 'removed': removed,
                     'customers_refreshed': customers_updated},
        )

        return {
            'added_count': added,
            'updated_count': updated,
            'removed_count': removed,
            'customers_refreshed': customers_updated,
            'total_orders': OrderCache.query.count(),
            'synced_at': now.isoformat(),
        }

    job, started = start_background_job(
        kind='orders_apply',
        work_fn=do_sync,
        user_id=user_id,
    )
    if not started:
        return jsonify({
            'job_id': job.id,
            'status': job.status,
            'message': 'An orders sync is already running.',
        }), 409

    return jsonify({'job_id': job.id, 'status': job.status}), 202


# ─────────────────────────────────────────────
# GET /api/orders/sync/status
# ─────────────────────────────────────────────

@orders_bp.route('/orders/sync/status', methods=['GET'])
@jwt_required()
def orders_sync_status():
    last = db.session.query(func.max(OrderCache.cached_at)).scalar()
    count = OrderCache.query.count()
    stale = (last is None) or (datetime.utcnow() - last) > STALE_AFTER

    job = get_latest_job('orders_apply')

    return jsonify({
        'last_synced_at': last.isoformat() if last else None,
        'order_count': count,
        'stale': stale,
        'stale_threshold_hours': int(STALE_AFTER.total_seconds() // 3600),
        'current_job': job.to_dict() if job else None,
    }), 200