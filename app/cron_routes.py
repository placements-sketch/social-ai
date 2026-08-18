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
from sqlalchemy.exc import IntegrityError

from app import db
from app.sync_jobs import start_background_job, get_latest_job
from app.utils.logger import log_event
from app.customers import compute_segment, _vip_threshold, recompute_rfm

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
        from app.integrations.shopify import iter_all_products, ShopifyCursorInvalidError
        from app.sync_jobs import get_resume_cursor, notify_discord_warning
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        def save_cursor(cursor_url):
            """Persist the current pagination cursor for resume."""
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.resume_cursor = cursor_url
                db.session.commit()

        # Check if we can resume from a previous failed attempt
        from app.sync_jobs import get_previous_progress_count
        resume_url = get_resume_cursor('products_apply')
        previous_count = get_previous_progress_count('products_apply') if resume_url else None
        if resume_url:
            base_msg = f"Resumed sync — continued from ~{previous_count:,} products" if previous_count else "Resumed sync"
            update_progress(f"{base_msg} · loading...")
        else:
            update_progress("Loading existing product IDs...")

        existing_ids = set(
            spid for (spid,) in
            db.session.query(ProductCache.shopify_product_id).all()
        )

        now = datetime.utcnow()
        added = updated = removed = 0
        CHUNK = 500
        buffer = []
        seen_ids = set()
        current_next_url = None  # cursor to save after each chunk

        update_progress("Streaming products from Shopify...")

        def flush_buffer():
            """Process one chunk: upsert, commit, expunge, then save cursor."""
            nonlocal added, updated
            for spid, snap in buffer:
                if spid in existing_ids:
                    row = ProductCache.query.filter_by(shopify_product_id=spid).first()
                    if row is None:
                        existing_ids.discard(spid)
                    else:
                        row.name = (snap.get('name') or '')[:512]
                        row.handle = (snap.get('handle') or '')[:256] or None
                        row.description = snap.get('description') or ''
                        row.price = Decimal(str(snap.get('price', '').replace('KES', '').replace(',', '').strip() or 0)) if snap.get('price') else None
                        row.variants = snap.get('variants') or []
                        row.variants_detail = snap.get('variants_detail') or []
                        row.images = snap.get('images') or []
                        row.tags = snap.get('tags') or []
                        row.stock_quantity = snap.get('stock_quantity')
                        row.inventory_tracked = snap.get('inventory_tracked', False)
                        row.cached_at = now
                        updated += 1
                        continue

                # Guard against duplicate IDs within the same stream (Shopify
                # pagination can repeat a product across pages, and migrated data
                # may already hold it). A plain INSERT on a dup crashes the whole
                # job (UniqueViolation), so upsert via a nested savepoint: try the
                # insert, and if it collides, fall back to updating the existing row.
                if spid in seen_ids:
                    # Already inserted/updated earlier in THIS run — skip the dup.
                    continue
                seen_ids.add(spid)
                try:
                    with db.session.begin_nested():
                        db.session.add(ProductCache(
                            shopify_product_id=spid,
                            name=(snap.get('name') or '')[:512],
                            handle=(snap.get('handle') or '')[:256] or None,
                            description=snap.get('description') or '',
                            price=Decimal(str(snap.get('price', '').replace('KES', '').replace(',', '').strip() or 0)) if snap.get('price') else None,
                            variants=snap.get('variants') or [],
                            variants_detail=snap.get('variants_detail') or [],
                            images=snap.get('images') or [],
                            tags=snap.get('tags') or [],
                            stock_quantity=snap.get('stock_quantity'),
                            inventory_tracked=snap.get('inventory_tracked', False),
                            cached_at=now,
                        ))
                    existing_ids.add(spid)
                    added += 1
                except IntegrityError:
                    # Row already exists (dup key) — update it instead of dying.
                    db.session.rollback()
                    row = ProductCache.query.filter_by(shopify_product_id=spid).first()
                    if row is not None:
                        row.name = (snap.get('name') or '')[:512]
                        row.handle = (snap.get('handle') or '')[:256] or None
                        row.description = snap.get('description') or ''
                        row.price = Decimal(str(snap.get('price', '').replace('KES', '').replace(',', '').strip() or 0)) if snap.get('price') else None
                        row.variants = snap.get('variants') or []
                        row.variants_detail = snap.get('variants_detail') or []
                        row.images = snap.get('images') or []
                        row.tags = snap.get('tags') or []
                        row.stock_quantity = snap.get('stock_quantity')
                        row.inventory_tracked = snap.get('inventory_tracked', False)
                        row.cached_at = now
                        updated += 1
                        existing_ids.add(spid)

            db.session.commit()
            db.session.expunge_all()
            buffer.clear()

            # Persist cursor AFTER commit — this is the resume point
            save_cursor(current_next_url)

        # Stream from Shopify, buffered upserts, cursor saved after each chunk
        total_received = 0
        try:
            for snap, next_url in iter_all_products(start_url=resume_url):
                current_next_url = next_url
                spid = str(snap['shopify_id'])
                seen_ids.add(spid)
                buffer.append((spid, snap))
                total_received += 1

                if len(buffer) >= CHUNK:
                    flush_buffer()
                    if resume_url and previous_count:
                        update_progress(f"Resumed sync — processed {total_received:,} products since resume point (continued from ~{previous_count:,})")
                    else:
                        update_progress(f"Processed {total_received:,} products...")

            if buffer:
                flush_buffer()
                if resume_url and previous_count:
                    update_progress(f"Resumed sync — processed {total_received:,} products since resume point (continued from ~{previous_count:,})")
                else:
                    update_progress(f"Processed {total_received:,} products...")

        except ShopifyCursorInvalidError as e:
            # Dead cursor. Alert on Discord, clear the cursor, restart from scratch.
            notify_discord_warning(
                title="Products sync cursor expired — restarting from scratch",
                message=(f"Shopify rejected the resume cursor. Discarding and starting a fresh sync.\n"
                         f"Progress so far this attempt: {total_received:,} products."),
                fields=[
                    {"name": "Job ID", "value": str(job_id), "inline": True},
                    {"name": "Detail", "value": f"```{str(e)[:200]}```", "inline": False},
                ]
            )
            save_cursor(None)  # discard the bad cursor
            # Reset state and restart from the beginning
            buffer.clear()
            seen_ids.clear()
            total_received = 0

            # Re-fetch existing_ids since we may have committed some rows already
            existing_ids = set(
                spid for (spid,) in
                db.session.query(ProductCache.shopify_product_id).all()
            )

            update_progress("Restarting products sync from scratch...")
            for snap, next_url in iter_all_products(start_url=None):
                current_next_url = next_url
                spid = str(snap['shopify_id'])
                seen_ids.add(spid)
                buffer.append((spid, snap))
                total_received += 1

                if len(buffer) >= CHUNK:
                    flush_buffer()
                    if resume_url and previous_count:
                        update_progress(f"Resumed sync — processed {total_received:,} products since resume point (continued from ~{previous_count:,})")
                    else:
                        update_progress(f"Processed {total_received:,} products...")

            if buffer:
                flush_buffer()
                if resume_url and previous_count:
                    update_progress(f"Resumed sync — processed {total_received:,} products since resume point (continued from ~{previous_count:,})")
                else:
                    update_progress(f"Processed {total_received:,} products...")

        # ── Delete stale products (in cache but not seen in Shopify this run) ──
        # ONLY delete if we did a full sync (seen_ids covers everything).
        # If we resumed partway, we can't tell if a "missing" product is genuinely
        # gone or just before our resume point.
        did_full_sync = resume_url is None
        if did_full_sync:
            to_delete_ids = list(existing_ids - seen_ids)
            for d_start in range(0, len(to_delete_ids), CHUNK):
                batch_ids = to_delete_ids[d_start:d_start + CHUNK]
                ProductCache.query.filter(
                    ProductCache.shopify_product_id.in_(batch_ids)
                ).delete(synchronize_session=False)
                removed += len(batch_ids)
                db.session.commit()

        # ── Clear cursor on successful completion ──
        save_cursor(None)

        return {
            'added_count': added,
            'updated_count': updated,
            'removed_count': removed,
            'total_products': ProductCache.query.count(),
            'synced_at': now.isoformat(),
            'was_resumed': resume_url is not None,
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
        from app.integrations.shopify import iter_all_customers, ShopifyCursorInvalidError
        from app.sync_jobs import get_resume_cursor, notify_discord_warning
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        def save_cursor(cursor_url):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.resume_cursor = cursor_url
                db.session.commit()

        # Check for resume cursor
        resume_url = get_resume_cursor('customers_apply')
        if resume_url:
            update_progress("Resuming from previous failure...")
        else:
            update_progress("Loading existing customer IDs...")

        vip_threshold = _vip_threshold()

        existing_ids = set(
            spid for (spid,) in
            db.session.query(CustomerCache.shopify_customer_id).all()
        )

        # ── Incremental: watermark decides full backfill vs delta ──────────
        from app.models import SyncState
        from datetime import timedelta

        state = SyncState.query.filter_by(kind='customers').first()
        watermark = state.watermark if state else None
        is_delta  = watermark is not None
        delta_filter = (watermark - timedelta(minutes=5)).isoformat() if is_delta else None

        now = datetime.utcnow()
        added = updated = removed = 0
        CHUNK = 1000
        buffer = []
        seen_ids = set()
        current_next_url = None

        update_progress("Streaming customers from Shopify...")

        def flush_buffer():
            nonlocal added, updated
            # One lookup for the whole buffer, not one per customer. Same fix as
            # the manual sync in customers.py: the per-row query measured 58x
            # slower on a 2,000-row sample, and every one of those trips crosses
            # the network from Render to Supabase.
            buffered_ids = [spid for spid, _snap in buffer]
            rows_by_id = {
                r.shopify_customer_id: r
                for r in CustomerCache.query.filter(
                    CustomerCache.shopify_customer_id.in_(buffered_ids)
                ).all()
            } if buffered_ids else {}

            for spid, snap in buffer:
                last_order = _parse_dt(snap.get('updated_at'))
                if spid in existing_ids:
                    row = rows_by_id.get(spid)
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
            db.session.expunge_all()
            buffer.clear()
            save_cursor(current_next_url)

        total_received = 0
        try:
            for snap, next_url in iter_all_customers(
                    start_url=resume_url,
                    updated_at_min=(None if resume_url else delta_filter)):
                current_next_url = next_url
                spid = str(snap['shopify_id'])
                seen_ids.add(spid)
                buffer.append((spid, snap))
                total_received += 1

                if len(buffer) >= CHUNK:
                    flush_buffer()
                    update_progress(f"Processed {total_received:,} customers...")

            if buffer:
                flush_buffer()
                update_progress(f"Processed {total_received:,} customers...")

        except ShopifyCursorInvalidError as e:
            notify_discord_warning(
                title="Customers sync cursor expired — restarting from scratch",
                message=(f"Shopify rejected the resume cursor. Discarding and starting a fresh sync.\n"
                         f"Progress so far this attempt: {total_received:,} customers."),
                fields=[
                    {"name": "Job ID", "value": str(job_id), "inline": True},
                    {"name": "Detail", "value": f"```{str(e)[:200]}```", "inline": False},
                ]
            )
            save_cursor(None)
            buffer.clear()
            seen_ids.clear()
            total_received = 0
            existing_ids = set(
                spid for (spid,) in
                db.session.query(CustomerCache.shopify_customer_id).all()
            )

            update_progress("Restarting customers sync from scratch...")
            for snap, next_url in iter_all_customers(start_url=None, updated_at_min=delta_filter):
                current_next_url = next_url
                spid = str(snap['shopify_id'])
                seen_ids.add(spid)
                buffer.append((spid, snap))
                total_received += 1

                if len(buffer) >= CHUNK:
                    flush_buffer()
                    update_progress(f"Processed {total_received:,} customers...")

            if buffer:
                flush_buffer()
                update_progress(f"Processed {total_received:,} customers...")

        # Deletes are NOT done here anymore — the weekly reconcile owns them.
        # (A delta run only sees changed customers, so existing_ids - seen_ids
        #  would wrongly target almost the whole table.)

        # Segments over the WHOLE table, not just the rows this delta touched.
        #
        # This is the run that matters for segments. A delta sync only sees
        # customers Shopify marked as changed, but segments move with the
        # calendar — everyone crosses 60/90/180 days at midnight whether or not
        # they did anything. Without this, an untouched customer keeps whatever
        # segment they had on the day they last ordered, forever.
        try:
            update_progress("Correcting last-order dates...")
            from app.customers import backfill_last_order_dates, refresh_all_segments
            # Order matters: segments are computed FROM last_order_date.
            backfill_last_order_dates()
            update_progress("Recomputing segments...")
            refresh_all_segments()
        except Exception as e:
            log_event("warn", "cron.segment_refresh_failed", str(e)[:160])

        # ── Advance watermark — only reached on successful completion ──────
        state = SyncState.query.filter_by(kind='customers').first()
        if state is None:
            state = SyncState(kind='customers', watermark=now)
            db.session.add(state)
        else:
            state.watermark = now
        db.session.commit()

        # Clear cursor on success
        save_cursor(None)

        return {
            'added_count': added,
            'updated_count': updated,
            'removed_count': removed,
            'total_customers': CustomerCache.query.count(),
            'synced_at': now.isoformat(),
            'was_resumed': resume_url is not None,
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
    from app.customers import _dec
    from app.refunds import upsert_refunds
    from decimal import Decimal

    def do_sync(job):
        from app.models import SyncJob
        from app.integrations.shopify import iter_all_orders, ShopifyCursorInvalidError
        from app.sync_jobs import get_resume_cursor, notify_discord_warning
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        def save_cursor(cursor_url):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.resume_cursor = cursor_url
                db.session.commit()

        # Check for resume cursor
        resume_url = get_resume_cursor('orders_apply')
        if resume_url:
            update_progress("Resuming from previous failure...")
        else:
            update_progress("Loading existing order IDs...")

        existing_ids = set(
            spid for (spid,) in
            db.session.query(OrderCache.shopify_order_id).all()
        )

        # ── Incremental: watermark decides full backfill vs delta ──────────
        from app.models import SyncState
        from datetime import timedelta

        state = SyncState.query.filter_by(kind='orders').first()
        watermark = state.watermark if state else None
        is_delta  = watermark is not None

        # Only fetch orders changed since the watermark (minus a 5-min overlap).
        # NULL watermark → delta_filter stays None → full backfill.
        delta_filter = (watermark - timedelta(minutes=5)).isoformat() if is_delta else None

        now = datetime.utcnow()
        added = updated = removed = 0
        affected_customer_ids = set()
        CHUNK = 1000
        buffer = []
        seen_ids = set()
        current_next_url = None

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
                        # Step 37 sales components. Decimal(str(...)) only
                        # when present — None must stay None, never 0.
                        row.gross_sales         = _dec(snap.get('gross_sales'))
                        row.total_discounts     = _dec(snap.get('total_discounts'))
                        row.total_tax           = _dec(snap.get('total_tax'))
                        row.total_shipping      = _dec(snap.get('total_shipping'))
                        row.total_refunded      = _dec(snap.get('total_refunded'))
                        row.cancelled_at        = _parse_dt(snap.get('cancelled_at'))
                        row.is_test             = snap.get('is_test')
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
                    gross_sales=_dec(snap.get('gross_sales')),
                    total_discounts=_dec(snap.get('total_discounts')),
                    total_tax=_dec(snap.get('total_tax')),
                    total_shipping=_dec(snap.get('total_shipping')),
                    total_refunded=_dec(snap.get('total_refunded')),
                    cancelled_at=_parse_dt(snap.get('cancelled_at')),
                    is_test=snap.get('is_test'),
                ))
                existing_ids.add(spid)
                added += 1

            # Step 38 — refunds ride along in the same transaction as their
            # orders. commit=False so the pair cannot be half-written: if this
            # raises, the batch rolls back instead of leaving orders whose
            # refunds never landed, which would read as revenue never returned.
            upsert_refunds([snap for _spid, snap in buffer], commit=False)
            db.session.commit()
            db.session.expunge_all()
            buffer.clear()
            save_cursor(current_next_url)

        total_received = 0
        try:
            for snap, next_url in iter_all_orders(
                    start_url=resume_url,
                    updated_at_min=(None if resume_url else delta_filter)):
                current_next_url = next_url
                spid = str(snap['shopify_id'])
                seen_ids.add(spid)
                cust = snap.get('shopify_customer_id')
                if cust:
                    affected_customer_ids.add(str(cust))
                buffer.append((spid, snap))
                total_received += 1

                if len(buffer) >= CHUNK:
                    flush_buffer()
                    update_progress(f"Processed {total_received:,} orders...")

            if buffer:
                flush_buffer()
                update_progress(f"Processed {total_received:,} orders...")

        except ShopifyCursorInvalidError as e:
            notify_discord_warning(
                title="Orders sync cursor expired — restarting from scratch",
                message=(f"Shopify rejected the resume cursor. Discarding and starting a fresh sync.\n"
                         f"Progress so far this attempt: {total_received:,} orders."),
                fields=[
                    {"name": "Job ID", "value": str(job_id), "inline": True},
                    {"name": "Detail", "value": f"```{str(e)[:200]}```", "inline": False},
                ]
            )
            save_cursor(None)
            buffer.clear()
            seen_ids.clear()
            total_received = 0
            existing_ids = set(
                spid for (spid,) in
                db.session.query(OrderCache.shopify_order_id).all()
            )

            update_progress("Restarting orders sync from scratch...")
            for snap, next_url in iter_all_orders(start_url=None, updated_at_min=delta_filter):
                current_next_url = next_url
                spid = str(snap['shopify_id'])
                seen_ids.add(spid)
                cust = snap.get('shopify_customer_id')
                if cust:
                    affected_customer_ids.add(str(cust))
                buffer.append((spid, snap))
                total_received += 1

                if len(buffer) >= CHUNK:
                    flush_buffer()
                    update_progress(f"Processed {total_received:,} orders...")

            if buffer:
                flush_buffer()
                update_progress(f"Processed {total_received:,} orders...")

        # ── Recompute customer aggregates + segment ───────────────────────
        # Backfill → recompute everyone (one-time). Delta → only customers
        # touched by this run. Deletes are NOT done here — the weekly
        # reconcile owns them.
        customers_updated = 0
        do_recompute = (not is_delta) or bool(affected_customer_ids)

        if do_recompute:
            update_progress("Recomputing customer aggregates...")
            vip_threshold = _vip_threshold()

            from sqlalchemy import func as sqla_func
            # Dates only. total_orders and total_spent are Shopify's to state.
            #
            # This query used to sum OrderCache.total and count its rows, then
            # write both over the figures the customer sync had just taken from
            # Shopify. Two writers, same two columns, and whichever job finished
            # last decided what the page showed — so the numbers never
            # reconciled with Shopify and would not have stayed reconciled even
            # if the arithmetic had been right.
            #
            # And it was not right. There was no financial_status filter, so
            # every order counted at full value: 19,769 voided orders worth
            # KES 107.5M, 1,337 fully refunded, 2,819 partially refunded
            # counted gross, and 356 unpaid. Shopify reports paid, net of
            # refunds. Currencies were added together too — 130,122 KES orders
            # and one USD order, summed as if they were the same unit.
            #
            # first/last order date stay here because Shopify's customer
            # payload carries last_order but not the first, and dates are not
            # money — no netting rule applies to them.
            agg_q = db.session.query(
                OrderCache.shopify_customer_id,
                sqla_func.max(OrderCache.order_date),
                sqla_func.min(OrderCache.order_date),
            ).filter(OrderCache.shopify_customer_id.isnot(None))

            cust_q = CustomerCache.query
            if is_delta:
                agg_q  = agg_q.filter(OrderCache.shopify_customer_id.in_(affected_customer_ids))
                cust_q = cust_q.filter(CustomerCache.shopify_customer_id.in_(affected_customer_ids))

            customer_aggs = dict(
                (cid, (last_date, first_date))
                for cid, last_date, first_date in
                agg_q.group_by(OrderCache.shopify_customer_id).all()
            )

            cust_q = cust_q.order_by(CustomerCache.id.asc())
            offset = 0
            while True:
                batch = cust_q.offset(offset).limit(CHUNK).all()
                if not batch:
                    break
                for customer in batch:
                    agg = customer_aggs.get(customer.shopify_customer_id)
                    if agg:
                        last_date, first_date = agg
                        customer.last_order_date  = last_date
                        customer.first_order_date = first_date
                    else:
                        # No orders in our cache. That is NOT a statement that
                        # the customer has never ordered — our cache can lag or
                        # be partial — so total_orders/total_spent are left
                        # exactly as Shopify reported them. Zeroing them here is
                        # what used to make long-standing customers appear brand
                        # new the morning after a partial sync.
                        customer.last_order_date  = None
                        customer.first_order_date = None
                    # Segment still derives from the (now Shopify-sourced)
                    # totals, so it moves with the figures on screen.
                    customer.segment = compute_segment(customer, vip_threshold)
                    customers_updated += 1
                db.session.commit()
                offset += CHUNK
                update_progress(f"Recomputed {customers_updated:,} customer aggregates...")
                db.session.expunge_all()

            update_progress("Scoring RFM...")
            recompute_rfm()

        # ── Advance watermark — only reached on successful completion ──────
        state = SyncState.query.filter_by(kind='orders').first()
        if state is None:
            state = SyncState(kind='orders', watermark=now)
            db.session.add(state)
        else:
            state.watermark = now
        db.session.commit()

        # Clear cursor on success
        save_cursor(None)

        return {
            'added_count': added,
            'updated_count': updated,
            'removed_count': removed,
            'customers_refreshed': customers_updated,
            'total_orders': OrderCache.query.count(),
            'synced_at': now.isoformat(),
            'was_resumed': resume_url is not None,
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

@cron_bp.route('/reconcile', methods=['POST'])
@require_cron_secret
def cron_reconcile():
    """
    Weekly reconcile for orders + customers: delete cache rows whose Shopify
    id no longer exists live. Products self-reconcile via their full 3-hour sync.

    Safety: the id fetchers raise on any page error, so the full live set is
    built BEFORE any delete — a truncated fetch fails the job instead of
    nuking the cache. We also refuse to delete more than a threshold of a
    table in one run.
    """
    from app.integrations.shopify import iter_all_order_ids, iter_all_customer_ids
    from app.models import OrderCache, CustomerCache

    def do_sync(job):
        from app.models import SyncJob
        from app.sync_jobs import notify_discord_warning
        job_id = job.id
        CHUNK = 1000

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        def reconcile_entity(label, id_iter_fn, model, id_col):
            update_progress(f"Reconcile: loading live {label} ids from Shopify...")
            # Build the FULL live set first. If any page errors, this raises
            # BEFORE any delete happens — the job fails, cache untouched.
            live_ids = set(id_iter_fn())
            existing_ids = set(spid for (spid,) in db.session.query(id_col).all())
            to_delete = list(existing_ids - live_ids)

            # Safety valve: refuse an implausibly large delete (likely bad fetch).
            limit = max(100, int(0.10 * len(existing_ids)))
            if len(to_delete) > limit:
                notify_discord_warning(
                    title=f"Reconcile aborted deletes for {label}",
                    message=(f"Wanted to delete {len(to_delete):,} {label} "
                             f"(> safety limit {limit:,} of {len(existing_ids):,}). "
                             f"Skipped — investigate a possible bad Shopify fetch."),
                    fields=[{"name": "Job ID", "value": str(job_id), "inline": True}],
                )
                update_progress(f"Reconcile {label}: ABORTED ({len(to_delete):,} > {limit:,})")
                return {"deleted": 0, "aborted": True, "candidates": len(to_delete)}

            deleted = 0
            for i in range(0, len(to_delete), CHUNK):
                batch = to_delete[i:i + CHUNK]
                model.query.filter(id_col.in_(batch)).delete(synchronize_session=False)
                deleted += len(batch)
                db.session.commit()
                update_progress(f"Reconcile {label}: deleted {deleted:,}/{len(to_delete):,}")
            return {"deleted": deleted, "aborted": False, "candidates": len(to_delete)}

        orders_res = reconcile_entity("orders", iter_all_order_ids,
                                      OrderCache, OrderCache.shopify_order_id)
        customers_res = reconcile_entity("customers", iter_all_customer_ids,
                                         CustomerCache, CustomerCache.shopify_customer_id)

        return {
            "orders": orders_res,
            "customers": customers_res,
            "reconciled_at": datetime.utcnow().isoformat(),
        }

    job, started = start_background_job(kind='reconcile', work_fn=do_sync, user_id=None)
    if not started:
        return jsonify({'job_id': job.id, 'status': job.status,
                        'message': 'A reconcile is already running.'}), 409

    log_event("info", "cron.reconcile.started", f"Cron triggered reconcile job {job.id}")
    return jsonify({'job_id': job.id, 'status': job.status, 'triggered_by': 'cron'}), 202

@cron_bp.route('/attribute', methods=['POST'])
@require_cron_secret
def cron_attribute():
    """
    Conversion attribution: scan recent Shopify orders; for any whose landing
    URL carries OUR utm token, link the order back to the DM/message that drove
    it, writing a row into conversion_attributions. Idempotent per order.
    """
    from app.integrations.shopify import iter_orders_for_attribution
    from app.models import ConversionAttribution, Message
    from app.utm import extract_utm_token_from_url, parse_utm_token
    from app.orders import _parse_dt
    from decimal import Decimal
    from datetime import timedelta

    def do_sync(job):
        from app.models import SyncJob
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        # Look back a window so orders that convert a few days after the DM get
        # caught. Idempotent: orders already attributed are skipped.
        window_days = 7
        updated_min = (datetime.utcnow() - timedelta(days=window_days)).isoformat()

        existing = set(
            oid for (oid,) in
            db.session.query(ConversionAttribution.shopify_order_id).all()
        )

        scanned = attributed = 0
        update_progress("Scanning recent orders for UTM attribution...")

        for o in iter_orders_for_attribution(updated_at_min=updated_min):
            scanned += 1
            if o['id'] in existing:
                continue
            token = extract_utm_token_from_url(o.get('landing_site'))
            if not token:
                continue  # not one of our DM-driven orders
            parsed = parse_utm_token(token)
            if not parsed:
                continue

            # Only set FKs if the message still exists (avoid dangling refs).
            # The conversation comes from the MESSAGE ROW, not from the token:
            # the token travels through a customer-visible URL, so treating its
            # conversation_id as authoritative would let a hand-edited link
            # credit an order to any conversation. The message id is still
            # taken from the token, but it has to resolve to a real row, and
            # whatever that row says is the truth.
            msg = Message.query.get(parsed['message_id'])
            if msg is None:
                log_event("warn", "cron.attribute.orphan_token",
                          f"Order {o['id']} carries a token for message "
                          f"{parsed['message_id']}, which no longer exists",
                          payload={"order_id": o['id'], "token": token})
            conv_id = msg.conversation_id if msg else None
            msg_id  = msg.id if msg else None

            order_dt = _parse_dt(o.get('order_date'))
            minutes = None
            if msg is not None and msg.created_at and order_dt:
                minutes = max(0, int((order_dt - msg.created_at).total_seconds() // 60))

            db.session.add(ConversionAttribution(
                shopify_order_id=o['id'],
                order_number=o.get('order_number'),
                order_total=Decimal(str(o.get('total') or 0)),
                order_tax=(Decimal(str(o['tax'])) if o.get('tax') is not None else None),
                order_currency=o.get('currency'),
                order_date=order_dt or datetime.utcnow(),
                conversation_id=conv_id,
                message_id=msg_id,
                utm_token=token,
                minutes_to_convert=minutes,
                product_handle=parsed.get('product_handle'),
            ))
            existing.add(o['id'])
            attributed += 1

            # Tell the team a link the assistant sent turned into an order.
            #
            # Routed through notifications rather than a new polling endpoint:
            # the bell already polls, every client already listens, and the row
            # doubles as the permanent record. The UI celebrates on seeing the
            # type; nothing here knows or cares about the animation.
            try:
                from app.notifications import notify_admins
                _amt = o.get('total') or 0
                _cur = o.get('currency') or 'KES'
                notify_admins(
                    type_='conversion_attributed',
                    title=f"Sale from an AI recommendation — {_cur} {_amt}",
                    body=(f"Order {o.get('order_number') or o['id']} came from a "
                          f"link the assistant sent"
                          + (f", {minutes} minutes after the message" if minutes is not None else "")
                          + "."),
                    severity='info',
                    resource_type='conversation',
                    resource_id=conv_id,
                    coalesce=False,   # every sale is its own event worth seeing
                )
            except Exception as e:
                # A missed celebration must never cost an attribution row.
                log_event("warning", "cron.attribution_notify_failed", str(e)[:160])
            if attributed % 100 == 0:
                db.session.commit()
                update_progress(f"Attributed {attributed} (scanned {scanned})...")

        db.session.commit()
        return {"scanned": scanned, "attributed": attributed}

    job, started = start_background_job(kind='attribute', work_fn=do_sync, user_id=None)
    if not started:
        return jsonify({'job_id': job.id, 'status': job.status,
                        'message': 'An attribution run is already running.'}), 409

    log_event("info", "cron.attribute.started", f"Cron triggered attribution job {job.id}")
    return jsonify({'job_id': job.id, 'status': job.status, 'triggered_by': 'cron'}), 202


@cron_bp.route('/watchdog', methods=['POST'])
@require_cron_secret
def cron_watchdog():
    from datetime import timedelta
    from app.models import SyncJob

    THRESHOLDS = {
        'products_apply':  timedelta(minutes=10),
        'customers_apply': timedelta(minutes=45),
        'orders_apply':    timedelta(minutes=90),
        'products_check':  timedelta(minutes=10),
        'reconcile':       timedelta(minutes=60),
    }
    # Anything past this is definitely dead, not just slow. Auto-mark as failed
    # so it stops alerting forever.
    HARD_DEATH = timedelta(hours=6)

    now = datetime.utcnow()
    stuck = []
    cleaned = []

    running_jobs = (SyncJob.query
                    .filter(SyncJob.status == 'running')
                    .all())

    for job in running_jobs:
        threshold = THRESHOLDS.get(job.kind, timedelta(minutes=60))
        started = job.started_at
        if started is None:
            continue
        elapsed = now - started

        # First: if it's WAY past threshold, mark as dead and stop alerting
        if elapsed > HARD_DEATH:
            job.status = 'failed'
            job.finished_at = now
            job.error = f'Auto-cleanup: stuck in running state for {int(elapsed.total_seconds()/60)} min'
            cleaned.append({'id': job.id, 'kind': job.kind})
            continue

        # Otherwise: alert if past kind-specific threshold but not yet dead
        if elapsed > threshold:
            stuck.append({
                'id': job.id,
                'kind': job.kind,
                'elapsed_min': int(elapsed.total_seconds() / 60),
                'threshold_min': int(threshold.total_seconds() / 60),
                'progress': job.progress or 'unknown',
            })

    if cleaned:
        db.session.commit()

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
        from app.settings import discord_webhook_for
        webhook_url = discord_webhook_for('warning')
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

@cron_bp.route('/prune-notifications', methods=['POST'])
@require_cron_secret
def cron_prune_notifications():
    """
    Delete read notifications older than 7 days and ALL notifications older
    than 30 days. Keeps the table from growing unbounded. Fast single query —
    no background job needed.
    """
    from app.models import Notification
    from datetime import timedelta
    now = datetime.utcnow()

    # Read notifications older than 7 days — safe to remove.
    read_cutoff = now - timedelta(days=7)
    read_deleted = (Notification.query
                    .filter(Notification.read_at.isnot(None))
                    .filter(Notification.created_at < read_cutoff)
                    .delete(synchronize_session=False))

    # Anything older than 30 days, read or not — hard cap.
    hard_cutoff = now - timedelta(days=30)
    old_deleted = (Notification.query
                   .filter(Notification.created_at < hard_cutoff)
                   .delete(synchronize_session=False))

    db.session.commit()
    log_event("info", "cron.prune_notifications",
              f"Pruned {read_deleted} read (>7d) + {old_deleted} old (>30d) notifications")
    return jsonify({
        'read_pruned': read_deleted,
        'old_pruned': old_deleted,
        'pruned_at': now.isoformat(),
    }), 200

@cron_bp.route('/check-unclaimed', methods=['POST'])
@require_cron_secret
def cron_check_unclaimed():
    """
    Alert on conversations left waiting in the human queue with nobody
    assigned. Run every few minutes.

    Escalations auto-assign, so a conversation only lands here when
    pick_next_agent() had no active agent to give it to, or someone
    unassigned it by hand. Either way a customer is waiting and no one owns
    it. Alerts once per waiting spell, not once per tick.
    """
    from app.assignment import alert_unclaimed, alert_silent

    result = alert_unclaimed()
    log_event("info", "cron.check_unclaimed",
              f"Unclaimed queue check: {result['stuck']} waiting, "
              f"{len(result['alerted'])} newly alerted",
              payload=result)

    # Second, broader sweep on the same tick.
    #
    # alert_unclaimed only looks at status='human_override', which is the queue
    # an escalation lands in. It structurally cannot see a conversation left at
    # status='active' with ai_enabled=true and no assignee — nobody answering,
    # nobody able to find it. That blind spot hid 13 direct messages for up to
    # 18 days. This one ignores every internal flag and asks only whether the
    # customer spoke last and how long ago.
    silent = alert_silent()
    log_event("info", "cron.check_silent",
              f"Silent conversation check: {silent['silent']} unanswered, "
              f"{len(silent['alerted'])} newly alerted",
              payload=silent)

    return jsonify({'ok': True, **result, 'silent': silent}), 200


@cron_bp.route('/auto-resolve', methods=['POST'])
@require_cron_secret
def cron_auto_resolve():
    """
    Close conversations that have gone quiet, so the inbox stays a worklist
    rather than an archive.

    NOTHING else ever resolves a conversation — the only other path is an agent
    clicking Resolve, and nobody watches AI-handled conversations, so they sat
    open indefinitely. That also defeated conversation threading: a returning
    customer joins the most recent OPEN conversation, so without closure every
    customer had one thread for life and "a dress in July / trousers in
    September" were the same conversation.

    The rule is deliberately one-sided: only close where WE spoke last. If the
    customer spoke last we still owe them a reply, and auto-closing that would
    bury a dropped customer instead of finishing a conversation.
    """
    from sqlalchemy import text as _sql
    from app.settings import get_section

    days = int(get_section('handoff').get('auto_resolve_days', 14))
    if days <= 0:
        return jsonify({'ok': True, 'resolved': 0, 'reason': 'auto-resolve disabled'}), 200

    # One statement: pick open conversations idle past the cutoff whose newest
    # message is outbound, and close them.
    result = db.session.execute(_sql("""
        WITH candidates AS (
          SELECT c.id
          FROM conversations c
          JOIN LATERAL (
              SELECT direction FROM messages
               WHERE conversation_id = c.id
               ORDER BY created_at DESC LIMIT 1
          ) last_msg ON true
          WHERE c.status <> 'resolved'
            AND c.last_message_at IS NOT NULL
            AND c.last_message_at < now() - make_interval(days => :days)
            AND last_msg.direction = 'outbound'
        )
        UPDATE conversations SET status = 'resolved', resolved_at = now()
        WHERE id IN (SELECT id FROM candidates)
        RETURNING id
    """), {'days': days})
    ids = [r[0] for r in result]
    db.session.commit()

    log_event("info", "cron.auto_resolve",
              f"Auto-resolved {len(ids)} conversation(s) idle for {days}+ days",
              payload={'days': days, 'count': len(ids), 'conversation_ids': ids[:50]})
    return jsonify({'ok': True, 'resolved': len(ids), 'days': days}), 200


@cron_bp.route('/refresh-ig-tokens', methods=['POST'])
@require_cron_secret
def cron_refresh_ig_tokens():
    """
    Refresh Instagram Login user tokens before they lapse.

    These last 60 days and can only be refreshed WHILE STILL VALID — miss the
    window and the only way back is re-running the OAuth flow by hand, with
    Instagram DMs down until someone notices. Page tokens never expire, so
    nothing else in this app has needed a job like this.

    Safe to run daily; it skips anything not near expiry unless ?force=1.
    """
    from app.integrations.meta import refresh_ig_login_tokens
    force = request.args.get('force') in ('1', 'true', 'yes')
    summary = refresh_ig_login_tokens(force=force)
    status = 200 if summary.get('failed', 0) == 0 else 207
    return jsonify(summary), status
