"""
Writing refunds into refunds_cache (Step 38).

One function, imported by every path that syncs orders — the full sync, the
paged sync, the nightly cron and the webhook. It lives here rather than being
inlined four times because orders_cache already has four writers, and the last
time a mapping was duplicated across them they drifted apart.
"""

from datetime import datetime

from app import db
from app.models import RefundCache


def _parse_dt(s):
    """ISO 8601 -> naive UTC datetime, matching the other cache tables."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError, TypeError):
        return None


def upsert_refunds(snaps, commit=True):
    """
    Mirror the refunds carried on a batch of order snapshots.

    `snaps` is the list of order dicts the sync already built; each may carry a
    'refunds' list from shopify._refund_rows(). Returns (added, updated).

    Keyed on shopify_refund_id, which is stable and unique. Refunds are
    effectively immutable once settled, but they are re-read on every full sync,
    so this updates in place rather than inserting duplicates — a duplicated
    refund row would inflate Returns for that month with no error anywhere.

    Deliberately does NOT delete refunds that are absent from the payload. A
    partial or interrupted sync would otherwise wipe real refunds and quietly
    raise net sales, which is the same class of failure that nearly destroyed
    the customer cache in Step 22.
    """
    rows = []
    for snap in (snaps or []):
        rows.extend(snap.get('refunds') or [])
    if not rows:
        return 0, 0

    # One lookup for the whole batch instead of a query per refund.
    ids = [r['shopify_refund_id'] for r in rows if r.get('shopify_refund_id')]
    existing = {}
    CHUNK = 500
    for i in range(0, len(ids), CHUNK):
        for row in (RefundCache.query
                    .filter(RefundCache.shopify_refund_id.in_(ids[i:i + CHUNK]))
                    .all()):
            existing[row.shopify_refund_id] = row

    now = datetime.utcnow()
    added = updated = 0

    for r in rows:
        rid = r.get('shopify_refund_id')
        if not rid:
            continue
        row = existing.get(rid)
        if row is None:
            row = RefundCache(shopify_refund_id=rid)
            db.session.add(row)
            existing[rid] = row      # a batch can carry the same refund twice
            added += 1
        else:
            updated += 1

        row.shopify_order_id = r.get('shopify_order_id')
        row.refund_date      = _parse_dt(r.get('refund_date'))
        row.goods_subtotal   = r.get('goods_subtotal')
        row.goods_tax        = r.get('goods_tax')
        row.amount_refunded  = r.get('amount_refunded')
        row.currency         = (r.get('currency') or '')[:8] or None
        row.cached_at        = now

    if commit:
        db.session.commit()
    return added, updated
