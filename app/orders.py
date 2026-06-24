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
from app.integrations.shopify import list_all_orders, iter_all_orders
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
        # Capture job ID — we refetch by ID after each expunge_all() since
        # the ORM object gets detached from the session.
        from app.models import SyncJob
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        # ── Step 1: load existing IDs (small footprint) ─────────────────
        update_progress("Loading existing order IDs...")

        existing_ids = set(
            spid for (spid,) in
            db.session.query(OrderCache.shopify_order_id).all()
        )

        now = datetime.utcnow()
        added = updated = removed = 0
        CHUNK = 500
        buffer = []
        seen_ids = set()

        update_progress("Streaming orders from Shopify...")

        def flush_buffer():
            nonlocal added, updated
            for spid, snap in buffer:
                order_date = _parse_dt(snap.get('order_date'))
                if spid in existing_ids:
                    row = OrderCache.query.filter_by(shopify_order_id=spid).first()
                    if row is None:
                        existing_ids.discard(spid)
                    else:
                        row.shopify_customer_id = _truncate(snap.get('shopify_customer_id'),  64)
                        row.order_number        = _truncate(snap.get('order_number'),        128)
                        row.total               = Decimal(str(snap.get('total', 0)))
                        row.currency            = _truncate(snap.get('currency'),              8)
                        row.items_count         = snap.get('items_count', 0)
                        row.products            = snap.get('products', [])
                        row.financial_status    = _truncate(snap.get('financial_status'),    64)
                        row.fulfillment_status  = _truncate(snap.get('fulfillment_status'),  64)
                        row.order_date          = order_date
                        row.cached_at           = now
                        updated += 1
                        continue

                db.session.add(OrderCache(
                    shopify_order_id=spid,
                    shopify_customer_id=_truncate(snap.get('shopify_customer_id'),  64),
                    order_number=_truncate(snap.get('order_number'),                128),
                    total=Decimal(str(snap.get('total', 0))),
                    currency=_truncate(snap.get('currency'),                         8),
                    items_count=snap.get('items_count', 0),
                    products=snap.get('products', []),
                    financial_status=_truncate(snap.get('financial_status'),        64),
                    fulfillment_status=_truncate(snap.get('fulfillment_status'),    64),
                    order_date=order_date,
                    cached_at=now,
                ))
                existing_ids.add(spid)
                added += 1

            db.session.commit()
            db.session.expunge_all()
            buffer.clear()

        # ── Step 2: stream from Shopify, flush every CHUNK ──────────────
        total_received = 0
        for snap in iter_all_orders():
            spid = str(snap['shopify_id'])
            seen_ids.add(spid)
            buffer.append((spid, snap))
            total_received += 1

            if len(buffer) >= CHUNK:
                flush_buffer()
                update_progress(f"Processed {total_received:,} orders...")

        if buffer:
            flush_buffer()
            update_progress(f"Processed {total_received:,} orders...")

        # ── Step 3: chunked deletes via IN-clause ───────────────────────
        to_delete_ids = list(existing_ids - seen_ids)
        for d_start in range(0, len(to_delete_ids), CHUNK):
            batch_ids = to_delete_ids[d_start:d_start + CHUNK]
            OrderCache.query.filter(
                OrderCache.shopify_order_id.in_(batch_ids)
            ).delete(synchronize_session=False)
            removed += len(batch_ids)
            db.session.commit()

        # ── Step 4: recompute customer aggregates from real order data ──
        update_progress("Recomputing customer aggregates...")

        customer_aggs = dict(
            (cid, (count, total_spent, last_date, first_date))
            for cid, count, total_spent, last_date, first_date in
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
            update_progress(f"Recomputed {customers_updated:,} customer aggregates...")
            db.session.expunge_all()

        # ── Step 5: audit log ───────────────────────────────────────────
        log_audit(
            user_id, 'sync_orders',
            resource_type='orders', resource_id=None,
            changes={'added': added, 'updated': updated, 'removed': removed,
                     'customers_refreshed': customers_updated,
                     'total_received': total_received},
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