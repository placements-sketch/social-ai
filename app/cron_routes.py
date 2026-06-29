"""
app/cron_routes.py
Scheduled-job trigger endpoints, hit by GitHub Actions cron.

Auth: shared secret in the X-Cron-Secret header. No JWT.
Pattern: each endpoint kicks off the existing async sync via start_background_job,
returns 202 immediately. GitHub Actions doesn't wait for the sync to finish —
it just confirms the job was queued.

Endpoints (all POST, all /api/cron prefix):
  POST /api/cron/sync-products
  POST /api/cron/sync-customers
  POST /api/cron/sync-orders
  GET  /api/cron/ping                — health check (no auth needed)
"""

import os
from datetime import datetime
from flask import Blueprint, request, jsonify
from functools import wraps

from app import db
from app.sync_jobs import start_background_job, get_latest_job
from app.utils.logger import log_event
from app.customers import compute_segment, _vip_threshold

cron_bp = Blueprint('cron', __name__, url_prefix='/api/cron')


def require_cron_secret(f):
    """
    Decorator that checks X-Cron-Secret header matches CRON_SECRET env var.
    Returns 401 if missing or wrong.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        expected = os.getenv('CRON_SECRET')
        if not expected:
            log_event("error", "cron.config",
                      "CRON_SECRET env var not set — refusing to authenticate")
            return jsonify({'error': 'Cron not configured on server'}), 500

        provided = request.headers.get('X-Cron-Secret', '')
        if provided != expected:
            log_event("warn", "cron.auth.bad_secret",
                      f"Cron auth failed from {request.remote_addr}")
            return jsonify({'error': 'Invalid cron secret'}), 401

        return f(*args, **kwargs)
    return wrapped


@cron_bp.route('/ping', methods=['GET'])
def ping():
    """Health check — no auth, useful for testing the route is alive."""
    return jsonify({
        'ok': True,
        'service': 'social-ai-cron',
        'time': datetime.utcnow().isoformat(),
    }), 200


@cron_bp.route('/sync-products', methods=['POST'])
@require_cron_secret
def cron_sync_products():
    """
    Trigger a products sync. Mirrors the body of POST /api/products/sync
    but without requiring a JWT-authenticated user.
    """
    from app.integrations.shopify import list_all_products
    from app.models import ProductCache
    from decimal import Decimal

    def do_sync(job):
        from app.models import SyncJob
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        vip_threshold = _vip_threshold()

        update_progress("Fetching products from Shopify...")
        products = list_all_products()
        now = datetime.utcnow()

        existing_ids = set(
            spid for (spid,) in
            db.session.query(ProductCache.shopify_product_id).all()
        )

        added = updated = 0
        CHUNK = 500
        for i in range(0, len(products), CHUNK):
            batch = products[i:i + CHUNK]
            for p in batch:
                spid = str(p['shopify_id'])
                if spid in existing_ids:
                    row = ProductCache.query.filter_by(shopify_product_id=spid).first()
                    if row is None:
                        existing_ids.discard(spid)
                    else:
                        row.name = (p.get('name') or '')[:512]
                        row.description = p.get('description') or ''
                        row.price = Decimal(str(p.get('price', '').replace('KES', '').replace(',', '').strip() or 0)) if p.get('price') else None
                        row.variants = p.get('variants') or []
                        row.tags = p.get('tags') or []
                        row.stock_quantity = p.get('stock_quantity')
                        row.inventory_tracked = p.get('inventory_tracked', False)
                        row.cached_at = now
                        updated += 1
                        continue

                db.session.add(ProductCache(
                    shopify_product_id=spid,
                    name=(p.get('name') or '')[:512],
                    description=p.get('description') or '',
                    price=Decimal(str(p.get('price', '').replace('KES', '').replace(',', '').strip() or 0)) if p.get('price') else None,
                    variants=p.get('variants') or [],
                    tags=p.get('tags') or [],
                    stock_quantity=p.get('stock_quantity'),
                    inventory_tracked=p.get('inventory_tracked', False),
                    cached_at=now,
                ))
                existing_ids.add(spid)
                added += 1

            db.session.commit()
            update_progress(f"Processed {min(i + CHUNK, len(products)):,} / {len(products):,}...")
            db.session.expunge_all()

        return {
            'added_count': added,
            'updated_count': updated,
            'total_products': ProductCache.query.count(),
            'synced_at': now.isoformat(),
        }

    job, started = start_background_job(
        kind='products_apply',
        work_fn=do_sync,
        user_id=None,  # cron has no user
    )
    if not started:
        return jsonify({
            'job_id': job.id,
            'status': job.status,
            'message': 'A products sync is already running.',
        }), 409

    log_event("info", "cron.products_sync.started", f"Cron triggered job {job.id}")
    return jsonify({'job_id': job.id, 'status': job.status, 'triggered_by': 'cron'}), 202


@cron_bp.route('/sync-customers', methods=['POST'])
@require_cron_secret
def cron_sync_customers():
    """Trigger a customers sync. Uses the same async pattern as /api/customers/sync."""
    from app.integrations.shopify import list_all_customers
    from app.models import CustomerCache
    from app.customers import _truncate, _parse_dt
    from decimal import Decimal

    def do_sync(job):
        from app.models import SyncJob
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        # Compute VIP threshold once at start of sync
        vip_threshold = _vip_threshold()

        update_progress("Fetching customers from Shopify...")
        shopify_customers = list_all_customers()

        snapshot = {str(sc['shopify_id']): sc for sc in shopify_customers}
        existing_ids = set(
            spid for (spid,) in
            db.session.query(CustomerCache.shopify_customer_id).all()
        )

        now = datetime.utcnow()
        added = updated = removed = 0
        CHUNK = 500
        items = list(snapshot.items())
        total_items = len(items)

        for chunk_start in range(0, total_items, CHUNK):
            for spid, snap in items[chunk_start:chunk_start + CHUNK]:
                last_order = _parse_dt(snap.get('updated_at'))
                if spid in existing_ids:
                    row = CustomerCache.query.filter_by(shopify_customer_id=spid).first()
                    if row is None:
                        existing_ids.discard(spid)
                    else:
                        row.email = _truncate(snap.get('email'), 512)
                        row.first_name = _truncate(snap.get('first_name'), 512)
                        row.last_name = _truncate(snap.get('last_name'), 512)
                        row.phone = _truncate(snap.get('phone'), 128)
                        row.city = _truncate(snap.get('city'), 256)
                        row.country = _truncate(snap.get('country'), 128)
                        row.accepts_marketing = snap.get('accepts_marketing', False)
                        row.tags = snap.get('tags', [])
                        row.total_orders = snap.get('total_orders', 0)
                        row.total_spent = Decimal(str(snap.get('total_spent', 0)))
                        row.last_order_date = last_order if (row.total_orders or 0) > 0 else None
                        row.shopify_created_at = _parse_dt(snap.get('shopify_created_at'))
                        row.segment = compute_segment(row, vip_threshold)
                        row.cached_at = now
                        updated += 1
                        continue

                new_row = CustomerCache(
                    shopify_customer_id=spid,
                    email=_truncate(snap.get('email'), 512),
                    first_name=_truncate(snap.get('first_name'), 512),
                    last_name=_truncate(snap.get('last_name'), 512),
                    phone=_truncate(snap.get('phone'), 128),
                    city=_truncate(snap.get('city'), 256),
                    country=_truncate(snap.get('country'), 128),
                    accepts_marketing=snap.get('accepts_marketing', False),
                    tags=snap.get('tags', []),
                    total_orders=snap.get('total_orders', 0),
                    total_spent=Decimal(str(snap.get('total_spent', 0))),
                    last_order_date=last_order if (snap.get('total_orders') or 0) > 0 else None,
                    shopify_created_at=_parse_dt(snap.get('shopify_created_at')),
                    cached_at=now,
                )
                new_row.segment = compute_segment(new_row, vip_threshold)
                db.session.add(new_row)
                existing_ids.add(spid)
                added += 1

            db.session.commit()
            processed = min(chunk_start + CHUNK, total_items)
            update_progress(f"Upserted {processed:,} / {total_items:,} customers...")
            db.session.expunge_all()

        # Chunked deletes
        to_delete_list = list(existing_ids - set(snapshot.keys()))
        for d_start in range(0, len(to_delete_list), CHUNK):
            CustomerCache.query.filter(
                CustomerCache.shopify_customer_id.in_(to_delete_list[d_start:d_start + CHUNK])
            ).delete(synchronize_session=False)
            removed += len(to_delete_list[d_start:d_start + CHUNK])
            db.session.commit()

        return {
            'added_count': added,
            'updated_count': updated,
            'removed_count': removed,
            'total_customers': CustomerCache.query.count(),
            'synced_at': now.isoformat(),
        }

    job, started = start_background_job(
        kind='customers_apply',
        work_fn=do_sync,
        user_id=None,
    )
    if not started:
        return jsonify({
            'job_id': job.id,
            'status': job.status,
            'message': 'A customers sync is already running.',
        }), 409

    log_event("info", "cron.customers_sync.started", f"Cron triggered job {job.id}")
    return jsonify({'job_id': job.id, 'status': job.status, 'triggered_by': 'cron'}), 202


@cron_bp.route('/sync-orders', methods=['POST'])
@require_cron_secret
def cron_sync_orders():
    """Trigger an orders sync. Uses streaming pattern from /api/orders/sync."""
    from app.integrations.shopify import iter_all_orders
    from app.models import OrderCache, CustomerCache
    from sqlalchemy import func
    from app.orders import _truncate, _parse_dt
    from decimal import Decimal

    def do_sync(job):
        from app.models import SyncJob
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

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
                        row.shopify_customer_id = _truncate(snap.get('shopify_customer_id'), 64)
                        row.order_number = _truncate(snap.get('order_number'), 128)
                        row.total = Decimal(str(snap.get('total', 0)))
                        row.currency = _truncate(snap.get('currency'), 8)
                        row.items_count = snap.get('items_count', 0)
                        row.products = snap.get('products', [])
                        row.financial_status = _truncate(snap.get('financial_status'), 64)
                        row.fulfillment_status = _truncate(snap.get('fulfillment_status'), 64)
                        row.order_date = order_date
                        row.cached_at = now
                        updated += 1
                        continue

                db.session.add(OrderCache(
                    shopify_order_id=spid,
                    shopify_customer_id=_truncate(snap.get('shopify_customer_id'), 64),
                    order_number=_truncate(snap.get('order_number'), 128),
                    total=Decimal(str(snap.get('total', 0))),
                    currency=_truncate(snap.get('currency'), 8),
                    items_count=snap.get('items_count', 0),
                    products=snap.get('products', []),
                    financial_status=_truncate(snap.get('financial_status'), 64),
                    fulfillment_status=_truncate(snap.get('fulfillment_status'), 64),
                    order_date=order_date,
                    cached_at=now,
                ))
                existing_ids.add(spid)
                added += 1

            db.session.commit()
            db.session.expunge_all()
            buffer.clear()

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

        # Deletes
        to_delete_ids = list(existing_ids - seen_ids)
        for d_start in range(0, len(to_delete_ids), CHUNK):
            batch_ids = to_delete_ids[d_start:d_start + CHUNK]
            OrderCache.query.filter(
                OrderCache.shopify_order_id.in_(batch_ids)
            ).delete(synchronize_session=False)
            removed += len(batch_ids)
            db.session.commit()

        # Recompute customer aggregates AND segment
        update_progress("Recomputing customer aggregates...")
        vip_threshold = _vip_threshold()

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
                customer.segment = compute_segment(customer, vip_threshold)
                customers_updated += 1

            db.session.commit()
            offset += CHUNK
            update_progress(f"Recomputed {customers_updated:,} customer aggregates...")
            db.session.expunge_all()

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
        user_id=None,
    )
    if not started:
        return jsonify({
            'job_id': job.id,
            'status': job.status,
            'message': 'An orders sync is already running.',
        }), 409

    log_event("info", "cron.orders_sync.started", f"Cron triggered job {job.id}")
    return jsonify({'job_id': job.id, 'status': job.status, 'triggered_by': 'cron'}), 202

@cron_bp.route('/watchdog', methods=['POST'])
@require_cron_secret
def cron_watchdog():
    """
    Detects stuck sync jobs and alerts Discord.
    A job is 'stuck' if its status is 'running' for longer than the kind's threshold.
    Thresholds reflect realistic max durations:
      products  — 10 min
      customers — 45 min
      orders    — 90 min
    """
    from datetime import timedelta
    from app.models import SyncJob

    THRESHOLDS = {
        'products_apply':  timedelta(minutes=10),
        'customers_apply': timedelta(minutes=45),
        'orders_apply':    timedelta(minutes=90),
    }

    now = datetime.utcnow()
    stuck = []

    running_jobs = (SyncJob.query
                    .filter(SyncJob.status == 'running')
                    .all())

    for job in running_jobs:
        threshold = THRESHOLDS.get(job.kind, timedelta(minutes=60))
        started = job.started_at
        if started is None:
            continue
        elapsed = now - started
        if elapsed > threshold:
            stuck.append({
                'id': job.id,
                'kind': job.kind,
                'elapsed_min': int(elapsed.total_seconds() / 60),
                'threshold_min': int(threshold.total_seconds() / 60),
                'progress': job.progress or 'unknown',
            })

    if stuck:
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
        if webhook_url:
            try:
                fields = []
                for j in stuck[:5]:
                    fields.append({
                        "name": f"Job #{j['id']} ({j['kind']})",
                        "value": f"Running {j['elapsed_min']} min (limit {j['threshold_min']}). Progress: {j['progress'][:200]}",
                        "inline": False,
                    })
                import requests as _requests
                _requests.post(webhook_url, json={
                    "username": "Sync Alerts",
                    "embeds": [{
                        "title": "🟡 Sync Job(s) Running Unusually Long",
                        "description": f"Found {len(stuck)} job(s) past their normal duration.",
                        "color": 16763904,
                        "fields": fields,
                    }]
                }, timeout=5)
            except Exception:
                pass

    return jsonify({
        'checked': len(running_jobs),
        'stuck': stuck,
    }), 200