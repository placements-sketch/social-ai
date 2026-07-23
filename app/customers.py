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
  never_bought — signed up, no orders yet
  vip          — top 25% by spend, ordered in last 60 days
  loyal        — 5+ orders, ordered in last 60 days
  new          — joined in last 30 days AND placed 1 order
  at_risk      — 2+ orders, last order 90-180 days ago
  churned      — 2+ orders, last order 180+ days ago
  regular      — anyone else with at least 1 order
"""

from datetime import datetime, timedelta
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func, or_

from app import db
from app.models import AuthUser, OrderCache, CustomerCache
from app.auth import log_audit, current_user_id
from app.integrations.shopify import list_all_customers
from app.sync_jobs import start_background_job, get_latest_job
from app.utils.logger import log_event

customers_bp = Blueprint('customers', __name__, url_prefix='/api')


STALE_AFTER = timedelta(hours=12)
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

# Segment → suggested action (shown on the customer detail panel).
SEGMENT_ACTIONS = {
    'vip':          'Send VIP invite + exclusive early access to new drops.',
    'loyal':        'Reward loyalty — offer a thank-you perk or referral bonus.',
    'regular':      'Encourage a repeat purchase with a curated recommendation.',
    'new':          'Welcome series — introduce bestsellers and the brand story.',
    'at_risk':      'Win-back nudge — a time-limited "we miss you" offer.',
    'churned':      'Reactivation campaign — strong incentive to return.',
    'never_bought': 'First-purchase incentive — a welcome discount to convert.',
}

# ─────────────────────────────────────────────
# RFM Segmentation
# ─────────────────────────────────────────────
def _truncate(value, max_len):
    """Coerce to string and clip to max_len. None → None."""
    if value is None:
        return None
    s = str(value)
    return s[:max_len] if len(s) > max_len else s


def compute_segment(customer, vip_spend_threshold):
    """
    Computes the RFM segment for a single customer dict/row.
    
    Segments:
      never_bought — signed up but never placed an order (regardless of how long ago)
      vip          — top spenders, ordered in last 60 days
      loyal        — 5+ orders, ordered in last 60 days
      new          — joined in last 30 days with 1 order
      churned      — 2+ orders, last order 180+ days ago
      at_risk      — 2+ orders, last order 90-180 days ago
      regular      — everyone else with at least 1 order
    """
    total_orders = customer.total_orders or 0
    total_spent = float(customer.total_spent or 0)
    last_order = customer.last_order_date
    created = customer.shopify_created_at

    now = datetime.utcnow()
    days_since_order = (now - last_order).days if last_order else None
    days_since_join = (now - created).days if created else None

    # Never bought — signed up but no conversion. Distinct from "new" (recent signup with 1 order).
    if total_orders == 0:
        return 'never_bought'

    if total_spent >= vip_spend_threshold and days_since_order is not None and days_since_order <= 60:
        return 'vip'
    if total_orders >= 5 and days_since_order is not None and days_since_order <= 60:
        return 'loyal'
    if days_since_order is not None and days_since_order > 180 and total_orders >= 2:
        return 'churned'
    if days_since_order is not None and days_since_order > 90 and total_orders >= 2:
        return 'at_risk'
    # Recently joined AND made 1 order (proper "new convert")
    if total_orders == 1 and days_since_join is not None and days_since_join <= 30:
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
# VAT
# ─────────────────────────────────────────────
# Shopify stores VAT-INCLUSIVE totals. Kenya VAT is 16%, so every figure we
# report as revenue is the stored amount ÷ 1.16. Dividing a sum is equivalent
# to dividing each line and re-summing, so this applies cleanly at the end.
VAT_DIVISOR = 1.16


def ex_vat(amount):
    """Strip VAT from a stored (VAT-inclusive) money figure."""
    try:
        return float(amount or 0) / VAT_DIVISOR
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────
# Serialization
# ─────────────────────────────────────────────

def _serialize_customer(c, vip_threshold):
    last_order = c.last_order_date
    if last_order:
        delta = (datetime.utcnow() - last_order).total_seconds()
        days_since = max(0, int(delta // 86400))
    else:
        days_since = None
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
        'total_spent': ex_vat(c.total_spent),
        'aov': (ex_vat(c.total_spent) / c.total_orders) if (c.total_orders or 0) > 0 else 0,
        'last_order_date': last_order.isoformat() if last_order else None,
        'days_since_last_order': days_since,
        'first_order_date': c.first_order_date.isoformat() if c.first_order_date else None,
        'created_at': c.shopify_created_at.isoformat() if c.shopify_created_at else None,
        'segment': compute_segment(c, vip_threshold),
        'rfm_r': c.rfm_r,
        'rfm_f': c.rfm_f,
        'rfm_m': c.rfm_m,
        'rfm_score': f"{c.rfm_r}.{c.rfm_f}.{c.rfm_m}" if c.rfm_r is not None else None,
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

    # Sort (pushed to SQL)
    sort_map = {
        'spent_desc':  CustomerCache.total_spent.desc(),
        'orders_desc': CustomerCache.total_orders.desc(),
        'recent':      CustomerCache.last_order_date.desc().nullslast(),
        'name':        CustomerCache.first_name.asc(),
    }
    query = query.order_by(sort_map.get(sort_by, CustomerCache.total_spent.desc()))

    vip_threshold = _vip_threshold()

    # If no segment filter: paginate in SQL (fast — only fetches `per_page` rows)
    if segment_filter and segment_filter != 'all':
        query = query.filter(CustomerCache.segment == segment_filter)

    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    serialized = [_serialize_customer(c, vip_threshold) for c in rows]

    last = db.session.query(func.max(CustomerCache.cached_at)).scalar()
    stale = (last is None) or (datetime.utcnow() - last) > STALE_AFTER

    return jsonify({
        'customers': serialized,
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
    """
    Aggregated data for the Customers overview page.
    
    All KPIs computed in SQL — no full-table loads. Top-N queries fetch
    only the 5 rows we display. Segment counts are computed in Python from
    a stream of small batches so peak memory stays bounded.
    """
    # ── Empty-state short-circuit ────────────────────────────────────────
    total = CustomerCache.query.count()
    if total == 0:
        return jsonify({
            'kpis': {'total_customers': 0, 'new_this_month': 0, 'repeat_customers': 0,
                     'retention_rate': 0, 'total_revenue': 0, 'avg_aov': 0},
            'segment_counts': {},
            'top_spenders': [], 'top_frequent': [],
            'aov_by_month': [], 'top_products': [],
        }), 200

    vip_threshold = _vip_threshold()
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)

    # ── KPIs: each one is a single SQL aggregate, milliseconds each ──────
    # Shopify stores VAT-INCLUSIVE totals. Kenya VAT is 16%, so gross sales —
    # what actually counts as revenue — is the total ÷ 1.16. Dividing the sum
    # is equivalent to dividing every line and re-summing.
    VAT_DIVISOR = 1.16
    total_revenue = ex_vat(
        db.session.query(func.coalesce(func.sum(CustomerCache.total_spent), 0)).scalar()
    ) / VAT_DIVISOR
    total_orders = int(
        db.session.query(func.coalesce(func.sum(CustomerCache.total_orders), 0)).scalar() or 0
    )
    avg_aov = (total_revenue / total_orders) if total_orders else 0

    new_this_month = (
        db.session.query(func.count(CustomerCache.id))
        .filter(CustomerCache.shopify_created_at >= month_ago)
        .scalar() or 0
    )

    repeat = (
        db.session.query(func.count(CustomerCache.id))
        .filter(CustomerCache.total_orders >= 2)
        .scalar() or 0
    )
    retention_rate = (repeat / total) if total else 0

    # ── Top spenders (only 5 rows loaded) ────────────────────────────────
    top_spenders_rows = (
        CustomerCache.query
        .order_by(CustomerCache.total_spent.desc().nullslast())
        .limit(5)
        .all()
    )
    top_spenders_out = [_serialize_customer(c, vip_threshold) for c in top_spenders_rows]

    # ── Top frequent (only 5 rows loaded) ────────────────────────────────
    top_frequent_rows = (
        CustomerCache.query
        .order_by(CustomerCache.total_orders.desc().nullslast())
        .limit(5)
        .all()
    )
    top_frequent_out = [_serialize_customer(c, vip_threshold) for c in top_frequent_rows]

# ── Segment counts ──────────────────────────────────────────────────
    # Segment is now persisted as a column on CustomerCache during sync,
    # so this is a single indexed GROUP BY query — milliseconds even for
    # millions of rows.
    segment_rows = (
        db.session.query(CustomerCache.segment, func.count(CustomerCache.id))
        .group_by(CustomerCache.segment)
        .all()
    )
    segment_counts = {seg: count for seg, count in segment_rows if seg}

    # ── Orders & revenue over time ──────────────────────────────────────
    # Granularity comes from the UI toggle. Whitelisted before it reaches the
    # SQL string — date_trunc can't take a bound parameter for its unit.
    gran = (request.args.get('granularity') or 'month').lower()
    if gran not in ('day', 'week', 'month'):
        gran = 'month'

    aov_by_month = []
    try:
        rows = db.session.execute(db.text(f"""
            SELECT date_trunc('{gran}', order_date) AS bucket,
                   COUNT(*)                        AS orders,
                   COALESCE(SUM(total), 0)         AS revenue
            FROM orders_cache
            WHERE order_date IS NOT NULL
              AND financial_status IN ('paid', 'partially_paid', 'partially_refunded')
            GROUP BY 1
            ORDER BY 1
        """)).fetchall()
        for r in rows:
            orders_n = int(r[1] or 0)
            revenue = ex_vat(r[2])
            bucket = r[0]
            label = bucket.strftime('%b %y') if gran == 'month' else bucket.strftime('%d %b %y')
            aov_by_month.append({
                'month':   label,
                'orders':  orders_n,
                'revenue': round(revenue),
                'aov':     round(revenue / orders_n) if orders_n else 0,
            })
    except Exception as e:
        log_event("warn", "customers.overview.revenue_by_month_failed", str(e))
        aov_by_month = []

    # ── Top products (from real orders when populated) ───────────────────
    top_products = []
    try:
        from app.models import OrderCache
        # OrderCache.products is a JSON list of titles. Postgres unnest gives
        # us per-line-item rows without loading everything into Python.
        from sqlalchemy import func as sf
        rows = db.session.execute(
            db.text("""
                SELECT title, COUNT(*) AS purchases
                FROM (
                  SELECT jsonb_array_elements_text(products::jsonb) AS title
                  FROM orders_cache
                ) AS line_items
                WHERE title IS NOT NULL AND title <> ''
                GROUP BY title
                ORDER BY purchases DESC
                LIMIT 6
            """)
        ).fetchall()
        top_products = [{'name': r[0], 'purchases': int(r[1])} for r in rows]
    except Exception as e:
        log_event("warn", "customers.overview.top_products_failed", str(e))
        top_products = []

    return jsonify({
        'kpis': {
            'total_customers': total,
            'new_this_month': int(new_this_month),
            'repeat_customers': int(repeat),
            'retention_rate': round(retention_rate, 4),
            'total_revenue': total_revenue,
            'avg_aov': round(avg_aov),
        },
        'segment_counts': segment_counts,
        'top_spenders': top_spenders_out,
        'top_frequent': top_frequent_out,
        'aov_by_month': aov_by_month,
        'top_products': top_products,
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

@customers_bp.route('/customers/<int:customer_id>/profile', methods=['GET'])
@jwt_required()
def customer_profile(customer_id):
    """
    Rich per-customer analytics for the detail panel:
    RFM tiles, customer-since, spend-over-time (by month), spend-by-brand,
    top items purchased, and the segment's suggested action.
    """
    c = CustomerCache.query.get(customer_id)
    if not c:
        return jsonify({'error': 'Customer not found'}), 404

    cid = c.shopify_customer_id

    # Spend & orders over time (by month) — from OrderCache.
    spend_over_time = []
    try:
        rows = db.session.execute(db.text("""
            SELECT to_char(date_trunc('month', order_date), 'YYYY-MM') AS ym,
                   COALESCE(SUM(total), 0) AS revenue,
                   COUNT(*) AS orders
            FROM orders_cache
            WHERE shopify_customer_id = :cid AND order_date IS NOT NULL
              AND financial_status IN ('paid', 'partially_paid', 'partially_refunded')
            GROUP BY 1 ORDER BY 1
        """), {'cid': cid}).fetchall()
        spend_over_time = [{'month': r[0], 'revenue': ex_vat(r[1]), 'orders': int(r[2])} for r in rows]
    except Exception as e:
        log_event("warn", "customers.profile.spend_over_time_failed", str(e))

    # Top items purchased — unnest the products JSON array of this customer's orders.
    top_items = []
    try:
        rows = db.session.execute(db.text("""
            SELECT title, COUNT(*) AS qty
            FROM (
              SELECT jsonb_array_elements_text(products::jsonb) AS title
              FROM orders_cache
              WHERE shopify_customer_id = :cid
            ) t
            WHERE title IS NOT NULL AND title <> ''
            GROUP BY title ORDER BY qty DESC LIMIT 8
        """), {'cid': cid}).fetchall()
        top_items = [{'name': r[0], 'count': int(r[1])} for r in rows]
    except Exception as e:
        log_event("warn", "customers.profile.top_items_failed", str(e))

    # Spend by brand — derive brand from the first token of each product title.
    # (Shop Zetu product titles start with the brand, e.g. "Vivo …", "Safari …".)
    spend_by_brand = []
    try:
        rows = db.session.execute(db.text("""
            SELECT split_part(title, ' ', 1) AS brand, COUNT(*) AS items
            FROM (
              SELECT jsonb_array_elements_text(products::jsonb) AS title
              FROM orders_cache
              WHERE shopify_customer_id = :cid
            ) t
            WHERE title IS NOT NULL AND title <> ''
            GROUP BY 1 ORDER BY items DESC LIMIT 6
        """), {'cid': cid}).fetchall()
        spend_by_brand = [{'brand': r[0], 'items': int(r[1])} for r in rows]
    except Exception as e:
        log_event("warn", "customers.profile.spend_by_brand_failed", str(e))

    since_year = c.first_order_date.year if c.first_order_date else (
        c.shopify_created_at.year if c.shopify_created_at else None)

    vip_threshold = _vip_threshold()
    segment = compute_segment(c, vip_threshold)

    return jsonify({
        'rfm': {'r': c.rfm_r, 'f': c.rfm_f, 'm': c.rfm_m,
                'score': f"{c.rfm_r}.{c.rfm_f}.{c.rfm_m}" if c.rfm_r is not None else None},
        'customer_since': since_year,
        'suggested_action': SEGMENT_ACTIONS.get(segment, 'Engage with a personalized recommendation.'),
        'spend_over_time': spend_over_time,
        'top_items': top_items,
        'spend_by_brand': spend_by_brand,
    }), 200

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
        'total': ex_vat(r.total),
        'currency': r.currency,
        'items': r.items_count,
        'products': r.products or [],
        'status': r.fulfillment_status or r.financial_status or 'pending',
    } for r in rows]

    return jsonify({'orders': orders, 'total': len(orders)}), 200


# ─────────────────────────────────────────────
# POST /api/customers/sync — async background job
# ─────────────────────────────────────────────

def _parse_dt(s):
    """ISO 8601 parser that strips tz to a naive UTC datetime (matches DB cols)."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


@customers_bp.route('/customers/sync', methods=['POST'])
@jwt_required()
def sync_customers():
    """
    Kick off a background job that mirrors Shopify customers into customers_cache.
    Returns 202 + job_id immediately. Frontend polls /api/customers/sync/status
    to see when it's done.
    """
    current_user = AuthUser.query.get(current_user_id())
    if current_user is None:
        return jsonify({'error': 'User not found'}), 404

    # Capture the user ID as a plain int — safe to use inside the background
    # thread where the ORM object would be detached.
    user_id = current_user.id
    
    def do_sync(job):
        # Capture job ID — refetch by ID after each expunge_all() since
        # the ORM object gets detached from the session.
        from app.models import SyncJob
        job_id = job.id

        def update_progress(text):
            j = SyncJob.query.get(job_id)
            if j is not None:
                j.progress = text
                db.session.commit()

        # VIP threshold computed once for this entire sync.
        vip_threshold = _vip_threshold()

        # Fetch from Shopify
        update_progress("Fetching customers from Shopify...")
        shopify_customers = list_all_customers()

        snapshot = {str(sc['shopify_id']): sc for sc in shopify_customers}
        # Don't load all rows just to check existence — fetch IDs only.
        # Far smaller (each ID ~10 bytes vs ~5KB for a full row).
        existing_ids = set(
            spid for (spid,) in
            db.session.query(CustomerCache.shopify_customer_id).all()
        )

        now = datetime.utcnow()
        added = updated = removed = 0

        job.progress = f"Upserting {len(snapshot)} customers..."
        db.session.commit()

        # Upsert in chunks so memory + transaction size stay manageable.
        CHUNK = 500
        items = list(snapshot.items())
        total_items = len(items)
        processed = 0

        for chunk_start in range(0, total_items, CHUNK):
            for spid, snap in items[chunk_start:chunk_start + CHUNK]:
                last_order = _parse_dt(snap.get('updated_at'))
                if spid in existing_ids:
                    # Targeted fetch — one row per UPDATE
                    row = CustomerCache.query.filter_by(shopify_customer_id=spid).first()
                    if row is None:
                        # Race condition: was in existing_ids but got deleted. Treat as insert.
                        existing_ids.discard(spid)
                    else:
                        row.email      = _truncate(snap.get('email'),      512)
                        row.first_name = _truncate(snap.get('first_name'), 512)
                        row.last_name  = _truncate(snap.get('last_name'),  512)
                        row.phone      = _truncate(snap.get('phone'),      128)
                        row.city       = _truncate(snap.get('city'),       256)
                        row.country    = _truncate(snap.get('country'),    128)
                        row.accepts_marketing = snap.get('accepts_marketing', False)
                        row.tags = snap.get('tags', [])
                        row.total_orders = snap.get('total_orders', 0)
                        row.total_spent = Decimal(str(snap.get('total_spent', 0)))
                        row.last_order_date = last_order if (row.total_orders or 0) > 0 else None
                        row.shopify_created_at = _parse_dt(snap.get('shopify_created_at'))
                        row.segment = compute_segment(row, vip_threshold)
                        row.cached_at = now
                        updated += 1
                        continue  # done, skip the insert branch

                # Insert path (either spid not in existing_ids, or row was missing)
                new_row = CustomerCache(
                    shopify_customer_id=spid,
                    email=_truncate(snap.get('email'),           512),
                    first_name=_truncate(snap.get('first_name'), 512),
                    last_name=_truncate(snap.get('last_name'),   512),
                    phone=_truncate(snap.get('phone'),           128),
                    city=_truncate(snap.get('city'),             256),
                    country=_truncate(snap.get('country'),       128),
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
            job.progress = f"Upserted {processed:,} / {total_items:,} customers..."
            db.session.commit()
            db.session.expunge_all()  # release per-row references between chunks

        # Deletes (also chunked for symmetry)
        to_delete_ids = existing_ids - set(snapshot.keys())
        to_delete_list = list(to_delete_ids)
        for d_start in range(0, len(to_delete_list), CHUNK):
            CustomerCache.query.filter(
                CustomerCache.shopify_customer_id.in_(to_delete_list[d_start:d_start + CHUNK])
            ).delete(synchronize_session=False)
            removed += len(to_delete_list[d_start:d_start + CHUNK])
            db.session.commit()

        # current_user was loaded in the request thread; pass the captured ID
        # rather than touching the detached ORM object inside the background thread.
        log_audit(
            user_id, 'sync_customers',
            resource_type='customers', resource_id=None,
            changes={'added': added, 'updated': updated, 'removed': removed},
        )

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
        user_id=user_id,
    )
    if not started:
        return jsonify({
            'job_id': job.id,
            'status': job.status,
            'message': 'A customers sync is already running.',
        }), 409

    return jsonify({'job_id': job.id, 'status': job.status}), 202

# ─────────────────────────────────────────────
# GET /api/customers/sync/status
# ─────────────────────────────────────────────

@customers_bp.route('/customers/sync/status', methods=['GET'])
@jwt_required()
def customers_sync_status():
    last = db.session.query(func.max(CustomerCache.cached_at)).scalar()
    count = CustomerCache.query.count()
    stale = (last is None) or (datetime.utcnow() - last) > STALE_AFTER

    # Include the most recent customer sync job for polling
    job = get_latest_job('customers_apply')

    return jsonify({
        'last_synced_at': last.isoformat() if last else None,
        'customer_count': count,
        'stale': stale,
        'stale_threshold_hours': int(STALE_AFTER.total_seconds() // 3600),
        'current_job': job.to_dict() if job else None,
    }), 200

@customers_bp.route('/customers/recompute-rfm', methods=['POST'])
@jwt_required()
def recompute_rfm_endpoint():
    current_user = AuthUser.query.get(current_user_id())
    if not current_user or current_user.role not in ('admin', 'supervisor'):
        return jsonify({'error': 'Not authorized'}), 403
    recompute_rfm()
    scored = db.session.query(func.count(CustomerCache.id)).filter(CustomerCache.rfm_r.isnot(None)).scalar()
    return jsonify({'scored': scored}), 200

def recompute_rfm():
    """
    Score every customer WITH orders 1-5 on Recency, Frequency, Monetary using
    quintiles (NTILE 5) across the whole buyer base. Recency is inverted so
    fewer days since last order = higher score. Zero-order customers are left
    NULL (kept aside as 'no orders yet'). One SQL statement — fast at scale.
    """
    from sqlalchemy import text
    sql = text("""
        WITH scored AS (
            SELECT
                id,
                NTILE(5) OVER (ORDER BY last_order_date ASC NULLS FIRST)  AS r,
                NTILE(5) OVER (ORDER BY total_orders ASC)                 AS f,
                NTILE(5) OVER (ORDER BY total_spent ASC)                  AS m
            FROM customers_cache
            WHERE total_orders > 0 AND last_order_date IS NOT NULL
        )
        UPDATE customers_cache c
        SET rfm_r = s.r, rfm_f = s.f, rfm_m = s.m
        FROM scored s
        WHERE c.id = s.id
    """)
    db.session.execute(sql)
    # Clear scores for anyone with no orders (in case they had scores before).
    db.session.execute(text(
        "UPDATE customers_cache SET rfm_r=NULL, rfm_f=NULL, rfm_m=NULL "
        "WHERE total_orders = 0 OR last_order_date IS NULL"
    ))
    db.session.commit()

@customers_bp.route('/customers/trends', methods=['GET'])
@jwt_required()
def customer_trends():
    """
    Data for the Trends page:
      revenue_by_segment  — total spend grouped by segment (where money comes from)
      recency_buckets     — count of buyers by days-since-last-order buckets
    """
    # Revenue contribution by segment.
    seg_rows = db.session.execute(db.text("""
        SELECT segment, COALESCE(SUM(total_spent), 0) AS revenue, COUNT(*) AS customers
        FROM customers_cache
        WHERE segment IS NOT NULL
        GROUP BY segment
        ORDER BY revenue DESC
    """)).fetchall()
    revenue_by_segment = [
        {'segment': r[0], 'revenue': ex_vat(r[1]), 'customers': int(r[2])}
        for r in seg_rows
    ]

    # Customers by recency bucket (days since last order).
    bucket_rows = db.session.execute(db.text("""
        SELECT
          CASE
            WHEN last_order_date IS NULL THEN 'none'
            WHEN last_order_date >= NOW() - INTERVAL '30 days'  THEN '0-30'
            WHEN last_order_date >= NOW() - INTERVAL '60 days'  THEN '31-60'
            WHEN last_order_date >= NOW() - INTERVAL '90 days'  THEN '61-90'
            WHEN last_order_date >= NOW() - INTERVAL '180 days' THEN '91-180'
            ELSE '180+'
          END AS bucket,
          COUNT(*) AS customers
        FROM customers_cache
        WHERE total_orders > 0
        GROUP BY bucket
    """)).fetchall()
    # Order the buckets consistently.
    order = ['0-30', '31-60', '61-90', '91-180', '180+']
    bucket_map = {r[0]: int(r[1]) for r in bucket_rows if r[0] != 'none'}
    recency_buckets = [{'bucket': b, 'customers': bucket_map.get(b, 0)} for b in order]

    return jsonify({
        'revenue_by_segment': revenue_by_segment,
        'recency_buckets': recency_buckets,
    }), 200