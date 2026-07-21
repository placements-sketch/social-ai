"""
One-off backfill for customers whose orders are missing from orders_cache.

Root cause: the bulk orders sync only sees the last ~60 days (no read_all_orders
scope). Customers whose orders are ALL older than 60 days never get cached.
The per-customer Shopify endpoint returns ALL their orders regardless of age,
so we use that to backfill the stragglers.

Run:  python backfill_orders.py
"""
from datetime import datetime

from app import create_app, db
from app.models import CustomerCache, OrderCache
from app.integrations.shopify import _real_get_customer_orders
from app.customers import recompute_rfm


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def main():
    app = create_app()
    with app.app_context():
        # Customers that claim orders but have none cached.
        missing = [
            c for c in CustomerCache.query.filter(CustomerCache.total_orders > 0).all()
            if not OrderCache.query.filter_by(shopify_customer_id=c.shopify_customer_id).first()
        ]
        print(f"Found {len(missing)} customers with missing orders:")
        for c in missing:
            print(f"  - {c.first_name} {c.last_name} ({c.shopify_customer_id}) claims {c.total_orders}")

        total_added = 0
        for c in missing:
            try:
                orders = _real_get_customer_orders(c.shopify_customer_id)
                added = 0
                for o in orders:
                    # Skip if already present (idempotent).
                    if OrderCache.query.filter_by(shopify_order_id=o['shopify_id']).first():
                        continue
                    db.session.add(OrderCache(
                        shopify_order_id=o['shopify_id'],
                        shopify_customer_id=o['shopify_customer_id'],
                        order_number=o.get('order_number'),
                        total=o.get('total', 0),
                        currency=o.get('currency', 'KES'),
                        items_count=o.get('items_count', 0),
                        products=o.get('products', []),
                        financial_status=o.get('financial_status'),
                        fulfillment_status=o.get('fulfillment_status'),
                        order_date=_parse_dt(o.get('order_date')),
                    ))
                    added += 1
                db.session.commit()
                total_added += added
                print(f"  ✓ {c.first_name} {c.last_name}: +{added} orders (Shopify returned {len(orders)})")
            except Exception as e:
                db.session.rollback()
                print(f"  ✗ {c.first_name} {c.last_name}: ERROR {e}")

        print(f"\nAdded {total_added} orders total.")

        # Recompute aggregates for the affected customers from the now-complete cache.
        print("Recomputing aggregates for backfilled customers...")
        for c in missing:
            rows = OrderCache.query.filter_by(shopify_customer_id=c.shopify_customer_id).all()
            if rows:
                c.total_orders = len(rows)
                c.total_spent = sum(float(r.total or 0) for r in rows)
                dates = [r.order_date for r in rows if r.order_date]
                c.last_order_date = max(dates) if dates else None
                c.first_order_date = min(dates) if dates else None
        db.session.commit()

        # Refresh RFM so their scores reflect the restored history.
        print("Recomputing RFM...")
        recompute_rfm()
        print("Done.")


if __name__ == '__main__':
    main()