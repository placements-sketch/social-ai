"""
app/shopify_webhooks.py
Shopify webhook handlers — a freshness layer over the cron delta+reconcile sync.
Each handler patches the local cache the moment an event lands.

Handlers MUST be idempotent and MUST NOT raise (the receiver already returned
200; a raise here just kills the background thread). The cron reconcile catches
anything missed while the instance was asleep.
"""
from app.utils.logger import log_event


def dispatch_shopify_webhook(topic: str, data: dict):
    """Route a verified Shopify webhook to its handler by topic."""
    handler = _HANDLERS.get(topic)
    if handler is None:
        log_event("info", "shopify_webhook.ignored",
                  f"No handler for topic '{topic}'", payload={"topic": topic})
        return
    log_event("info", "shopify_webhook.received",
              f"Handling Shopify webhook: {topic}", payload={"topic": topic})
    try:
        handler(data)
    except Exception as e:
        log_event("error", "shopify_webhook.handler_failed",
                  f"Handler for '{topic}' failed: {str(e)[:200]}", payload={"topic": topic})


# ── Handlers — Phase 1 stubs, filled in Phase 2 (product/order/customer)
#    and Phase 3 (inventory). ────────────────────────────────────────────────

def _raw_product_to_snap(product: dict) -> dict:
    """
    Transform a RAW Shopify product (webhook payload) into the same 'snap'
    shape the sync produces, so _shopify_to_cache_dict maps it identically.
    Mirrors the transform in shopify.py's product stream + refresh_live_stock.
    """
    variants = product.get('variants') or []
    inventory_tracked = any(v.get('inventory_management') == 'shopify' for v in variants)
    stock_quantity = sum(
        (v.get('inventory_quantity') or 0) for v in variants
        if v.get('inventory_management') == 'shopify'
    ) if inventory_tracked else None

    variants_detail = [
        {
            "shopify_variant_id": str(v.get('id')),
            "inventory_item_id": str(v.get('inventory_item_id')) if v.get('inventory_item_id') else None,
            "title": v.get('title', ''),
            "option1": v.get('option1'),
            "option2": v.get('option2'),
            "option3": v.get('option3'),
            "price": v.get('price'),
            "sku": v.get('sku'),
            "inventory_quantity": v.get('inventory_quantity'),
            "inventory_tracked": v.get('inventory_management') == 'shopify',
        }
        for v in variants
    ]

    tags_raw = product.get('tags')
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
    else:
        tags = [t for t in (tags_raw or []) if t]

    return {
        "shopify_id": str(product.get('id')),
        "name": product.get('title', 'Unknown'),
        "handle": product.get('handle') or '',
        "description": (product.get('body_html') or '')[:200],
        "price": f"KES {variants[0].get('price', 'N/A')}" if variants else "N/A",
        "variants": [v.get('title', '') for v in variants],
        "variants_detail": variants_detail,
        "images": [img.get('src') for img in (product.get('images') or []) if img.get('src')],
        "stock_quantity": stock_quantity,
        "inventory_tracked": inventory_tracked,
        "tags": tags,
    }


def _delete_product_by_id(spid: str):
    from app import db
    from app.models import ProductCache
    row = ProductCache.query.filter_by(shopify_product_id=str(spid)).first()
    if row:
        db.session.delete(row)
        db.session.commit()
        log_event("info", "shopify_webhook.product_deleted",
                  f"Product removed from cache: {spid}", payload={"id": spid})


def _handle_product_update(data: dict):
    """products/create + products/update → upsert the cache row."""
    from datetime import datetime
    from app import db
    from app.models import ProductCache
    from app.products import _shopify_to_cache_dict

    spid = str(data.get('id') or '')
    if not spid:
        return

    # Match the sync's filter: only ACTIVE + PUBLISHED products belong in the
    # cache. If a product goes draft/archived/unpublished, drop it — same as
    # the reconcile sync would on its next pass.
    is_active = (data.get('status') == 'active') and bool(data.get('published_at'))
    if not is_active:
        _delete_product_by_id(spid)
        return

    d = _shopify_to_cache_dict(_raw_product_to_snap(data))

    row = ProductCache.query.filter_by(shopify_product_id=spid).first()
    if row is None:
        row = ProductCache(shopify_product_id=spid)
        db.session.add(row)
    row.name = d['name']
    row.handle = d['handle']
    row.description = d['description']
    row.price = d['price']
    row.variants = d['variants']
    row.variants_detail = d['variants_detail']
    row.images = d['images']
    row.tags = d['tags']
    row.stock_quantity = d['stock_quantity']
    row.inventory_tracked = d['inventory_tracked']
    row.cached_at = datetime.utcnow()
    db.session.commit()

    # Keep the inventory map fresh so stock webhooks can resolve this product.
    upsert_inventory_map(spid, d['variants_detail'])

    log_event("info", "shopify_webhook.product_upserted",
              f"Product cached from webhook: {d['name']}", payload={"id": spid})


def _handle_product_delete(data: dict):
    """products/delete → remove the cache row."""
    _delete_product_by_id(str(data.get('id') or ''))

def _handle_order(data: dict):
    """
    orders/create + orders/updated → upsert the order row, then recompute just
    this customer's aggregates + segment (recency drives at_risk/churned/vip).
    """
    from decimal import Decimal
    from datetime import datetime
    from sqlalchemy import func
    from app import db
    from app.models import OrderCache, CustomerCache
    from app.customers import compute_segment, _vip_threshold, _truncate, _dec
    # Same two helpers the sync paths use, so a webhook-written row and a
    # sync-written row can never disagree about what "shipping" means.
    from app.integrations.shopify import _shipping_total, _refunded_total

    oid = str(data.get('id') or '')
    if not oid:
        return

    customer = data.get('customer') or {}
    cid = str(customer.get('id')) if customer.get('id') else None
    line_items = data.get('line_items') or []
    now = datetime.utcnow()

    row = OrderCache.query.filter_by(shopify_order_id=oid).first()
    if row is None:
        row = OrderCache(shopify_order_id=oid)
        db.session.add(row)
    row.shopify_customer_id = _truncate(cid, 64)
    row.order_number        = _truncate(str(data.get('order_number') or data.get('name') or ''), 128)
    row.total               = Decimal(str(data.get('total_price', 0) or 0))
    row.currency            = _truncate(data.get('currency', 'KES'), 8)
    row.items_count         = sum(int(li.get('quantity', 0) or 0) for li in line_items)
    row.products            = [li.get('title', '') for li in line_items if li.get('title')]
    row.financial_status    = _truncate(data.get('financial_status'), 64)
    row.fulfillment_status  = _truncate(data.get('fulfillment_status'), 64)
    row.order_date          = _parse_dt(data.get('created_at'))
    row.cached_at           = now
    # Step 37 sales components. This path matters more than the two sync paths:
    # it is the only one that sees an order the moment it changes, so an order
    # refunded today gets its `total_refunded` here and not days later. Omitting
    # it would leave live orders permanently NULL between full syncs.
    row.gross_sales         = _dec(data.get('total_line_items_price'))
    row.total_discounts     = _dec(data.get('total_discounts'))
    row.total_tax           = _dec(data.get('total_tax'))
    row.total_shipping      = _dec(_shipping_total(data))
    row.total_refunded      = _dec(_refunded_total(data))
    row.cancelled_at        = _parse_dt(data.get('cancelled_at'))
    row.is_test             = bool(data.get('test')) if data.get('test') is not None else None
    db.session.commit()

    log_event("info", "shopify_webhook.order_upserted",
              f"Order cached from webhook: {row.order_number or oid}",
              payload={"id": oid, "customer": cid})

    # Refresh ONLY this customer's order DATES from cache.
    #
    # This used to recompute total_orders and total_spent here too, which made
    # it the third writer of those two columns — and the most aggressive, since
    # it fires on every orders/create and orders/updated rather than nightly.
    # It summed OrderCache.total with no financial_status filter, so a voided
    # or refunded order still pushed a customer's lifetime spend up, seconds
    # after Shopify had told us the correct net figure.
    #
    # Those two columns now come from Shopify alone, via the customers/create
    # and customers/update webhooks and the customer sync. Shopify emits a
    # customer update when an order changes a customer's totals, so the figures
    # still refresh promptly — they just refresh with Shopify's arithmetic
    # instead of ours.
    if cid:
        cust = CustomerCache.query.filter_by(shopify_customer_id=cid).first()
        if cust is not None:
            last_date, first_date = (
                db.session.query(
                    func.max(OrderCache.order_date),
                    func.min(OrderCache.order_date),
                )
                .filter(OrderCache.shopify_customer_id == cid)
                .first()
            )
            cust.last_order_date  = last_date
            cust.first_order_date = first_date
            try:
                cust.segment = compute_segment(cust, _vip_threshold())
            except Exception:
                pass
            db.session.commit()
            log_event("info", "shopify_webhook.customer_aggregates_refreshed",
                      f"Recomputed aggregates for customer {cid}",
                      payload={"customer": cid, "orders": cust.total_orders, "segment": cust.segment})

def _parse_dt(s):
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _handle_customer(data: dict):
    """
    customers/create + customers/update → upsert profile + totals, recompute
    segment. Deliberately does NOT touch last_order_date / first_order_date —
    this payload doesn't carry them; the orders sync/webhook owns those.
    """
    from app import db
    from app.models import CustomerCache
    from app.customers import compute_segment, _vip_threshold, _truncate

    cid = str(data.get('id') or '')
    if not cid:
        return

    addr = data.get('default_address') or {}
    row = CustomerCache.query.filter_by(shopify_customer_id=cid).first()
    is_new = row is None
    if is_new:
        row = CustomerCache(shopify_customer_id=cid)
        db.session.add(row)

    row.email      = _truncate(data.get('email'), 512)
    row.first_name = _truncate(data.get('first_name'), 512)
    row.last_name  = _truncate(data.get('last_name'), 512)
    row.phone      = _truncate(data.get('phone') or addr.get('phone'), 128)
    row.city       = _truncate(addr.get('city'), 256)
    row.country    = _truncate(addr.get('country'), 256)
    row.accepts_marketing = bool(data.get('accepts_marketing', False))
    row.tags = [t.strip() for t in (data.get('tags') or '').split(',') if t.strip()]
    row.total_orders = int(data.get('orders_count', 0) or 0)
    row.total_spent  = float(data.get('total_spent', 0) or 0)
    if not row.shopify_created_at and data.get('created_at'):
        row.shopify_created_at = _parse_dt(data.get('created_at'))

    try:
        row.segment = compute_segment(row, _vip_threshold())
    except Exception:
        pass

    db.session.commit()
    log_event("info", "shopify_webhook.customer_upserted",
              f"Customer cached from webhook: {cid}",
              payload={"id": cid, "new": is_new, "segment": row.segment})

def _handle_inventory_update(data: dict):
    """
    inventory_levels/update → map inventory_item_id to its product, refresh that
    product's stock from Shopify (authoritative variant totals), patch the cache.
    """
    from datetime import datetime
    from app import db
    from app.models import InventoryMap, ProductCache
    from app.integrations.shopify import refresh_stock_for_products
    from sqlalchemy.orm.exc import ObjectDeletedError, StaleDataError

    iid = str(data.get('inventory_item_id') or '')
    if not iid:
        return

    m = InventoryMap.query.get(iid)
    if m is None:
        log_event("info", "shopify_webhook.inventory_unmapped",
                  f"No product mapped for inventory_item {iid} — sync/backfill will map it",
                  payload={"inventory_item_id": iid})
        return

    pid = str(m.shopify_product_id)

    # Hand the database connection back BEFORE calling Shopify.
    #
    # refresh_stock_for_products() is an HTTP round trip. Holding a pooled
    # connection across it meant every inventory webhook occupied one of the
    # five this worker has (pool_size 4 + overflow 1) for the whole call — and
    # Shopify delivers these in bursts, so the pool drained and handlers began
    # failing with "QueuePool limit of size 4 overflow 1 reached, connection
    # timed out". The connection was idle that entire time; nothing needed it.
    #
    # commit() ends the transaction and releases the connection back to the
    # pool. The next query below transparently checks one out again. `pid` is a
    # plain string, so nothing here depends on the session staying open.
    db.session.commit()

    info = (refresh_stock_for_products([pid]) or {}).get(pid)
    if not info:
        return

    row = ProductCache.query.filter_by(shopify_product_id=pid).first()
    if row is None:
        return

    row.stock_quantity = info.get('stock_quantity')
    row.inventory_tracked = info.get('inventory_tracked', row.inventory_tracked)
    if info.get('variants_detail'):
        row.variants_detail = info['variants_detail']
    row.cached_at = datetime.utcnow()

    # Read the value BEFORE committing. commit() expires every attribute on the
    # instance, so the next read re-SELECTs it — and if the product was deleted
    # meanwhile that raises ObjectDeletedError. The log line below used to read
    # row.stock_quantity after the commit, which is precisely the crash seen as
    # "Instance '<ProductCache ...>' has been deleted, or its row is otherwise
    # not present."
    stock = row.stock_quantity

    try:
        db.session.commit()
    except (ObjectDeletedError, StaleDataError):
        # The product was deleted while we were away fetching its stock from
        # Shopify — refresh_stock_for_products() is a network round trip, which
        # is a wide window, and Shopify delivers webhooks concurrently so a
        # products/delete can land in the middle of this one. Nothing to update
        # and nothing wrong: the product is gone, which is the outcome we want.
        db.session.rollback()
        log_event("info", "shopify_webhook.inventory_product_gone",
                  f"Product {pid} was deleted while its stock was being refreshed",
                  payload={"product": pid, "inventory_item_id": iid})
        return

    log_event("info", "shopify_webhook.inventory_updated",
              f"Stock refreshed for product {pid}: {stock}",
              payload={"product": pid, "stock": stock})


_HANDLERS = {
    "products/create":         _handle_product_update,
    "products/update":         _handle_product_update,
    "products/delete":         _handle_product_delete,
    "orders/create":           _handle_order,
    "orders/updated":          _handle_order,
    "customers/create":        _handle_customer,
    "customers/update":        _handle_customer,
    "inventory_levels/update": _handle_inventory_update,
}

def upsert_inventory_map(shopify_product_id: str, variants_detail: list):
    """Populate inventory_map from a product's variants_detail."""
    from app import db
    from app.models import InventoryMap
    pid = str(shopify_product_id or '')
    if not pid or not variants_detail:
        return
    changed = False
    for v in variants_detail:
        iid = v.get('inventory_item_id')
        if not iid:
            continue
        row = InventoryMap.query.get(str(iid))
        if row is None:
            row = InventoryMap(inventory_item_id=str(iid))
            db.session.add(row)
        row.shopify_product_id = pid
        row.shopify_variant_id = v.get('shopify_variant_id')
        changed = True
    if changed:
        db.session.commit()