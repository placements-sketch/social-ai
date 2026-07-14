"""
Safe, parameterized query layer for the Customer Profiling AI assistant.

The AI NEVER writes SQL. It calls these two functions with structured params,
every one of which is validated against a strict allow-list. Anything not on
the list is rejected. Read-only. Hard row cap. This is the security boundary.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, and_

from app import db
from app.models import CustomerCache, OrderCache

MAX_ROWS = 50  # hard cap — the AI cannot exceed this no matter what it asks

# ── Allow-lists. If it's not here, it cannot be queried. ──────────────────
_FILTER_FIELDS = {
    'city':               ('ilike', CustomerCache.city),
    'country':            ('ilike', CustomerCache.country),
    'segment':            ('eq',    CustomerCache.segment),
    'accepts_marketing':  ('bool',  CustomerCache.accepts_marketing),
    'min_total_spent':    ('gte',   CustomerCache.total_spent),
    'max_total_spent':    ('lte',   CustomerCache.total_spent),
    'min_total_orders':   ('gte',   CustomerCache.total_orders),
    'max_total_orders':   ('lte',   CustomerCache.total_orders),
}
_SORT_FIELDS = {
    'total_spent':     CustomerCache.total_spent,
    'total_orders':    CustomerCache.total_orders,
    'last_order_date': CustomerCache.last_order_date,
    'first_order_date': CustomerCache.first_order_date,
}
_SEGMENTS = {'vip', 'loyal', 'regular', 'new', 'never_bought', 'at_risk', 'churned'}

_TIME_WINDOWS = {
    'this_month':  lambda now: now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    'last_7_days': lambda now: now - timedelta(days=7),
    'last_30_days': lambda now: now - timedelta(days=30),
    'last_90_days': lambda now: now - timedelta(days=90),
    'this_year':   lambda now: now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
    'all_time':    lambda now: None,
}
_AGG_GROUP = {'customer', 'city', 'segment'}
_AGG_METRIC = {'sum_spend', 'order_count', 'aov'}


def _clamp_limit(limit):
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 10
    return max(1, min(n, MAX_ROWS))


def _customer_row(c):
    return {
        'name': c.full_name,
        'email': c.email,
        'city': c.city,
        'country': c.country,
        'segment': c.segment,
        'total_spent': float(c.total_spent or 0),
        'total_orders': c.total_orders or 0,
        'last_order_date': c.last_order_date.strftime('%Y-%m-%d') if c.last_order_date else None,
    }


# ──────────────────────────────────────────────────────────────────────────
# Tool 1: query_customers — filter/sort/limit over the customer cache
# ──────────────────────────────────────────────────────────────────────────

def query_customers(filters=None, sort_by='total_spent', order='desc', limit=10):
    """
    Filter, sort, and rank customers. Lifetime figures (total_spent, total_orders)
    come straight from the cache. Every filter/sort key is allow-listed.
    Returns {'count': N, 'rows': [...], 'note': str|None}.
    """
    filters = filters or {}
    q = CustomerCache.query
    applied, ignored = [], []

    for key, raw in filters.items():
        spec = _FILTER_FIELDS.get(key)
        if not spec:
            ignored.append(key)
            continue
        op, col = spec
        try:
            if op == 'ilike':
                q = q.filter(col.ilike(f"%{str(raw).strip()}%"))
            elif op == 'eq':
                val = str(raw).strip().lower()
                if key == 'segment' and val not in _SEGMENTS:
                    ignored.append(f"{key}={raw}")
                    continue
                q = q.filter(func.lower(col) == val)
            elif op == 'bool':
                q = q.filter(col.is_(bool(raw)))
            elif op == 'gte':
                q = q.filter(col >= Decimal(str(raw)))
            elif op == 'lte':
                q = q.filter(col <= Decimal(str(raw)))
            applied.append(key)
        except Exception:
            ignored.append(key)

    sort_col = _SORT_FIELDS.get(sort_by, CustomerCache.total_spent)
    sort_col = sort_col.asc() if str(order).lower() == 'asc' else sort_col.desc()
    q = q.order_by(sort_col.nullslast() if hasattr(sort_col, 'nullslast') else sort_col)

    n = _clamp_limit(limit)
    rows = q.limit(n).all()
    note = None
    if ignored:
        note = f"Ignored unsupported filters: {', '.join(ignored)}"
    return {'count': len(rows), 'rows': [_customer_row(c) for c in rows], 'note': note}


# ──────────────────────────────────────────────────────────────────────────
# Tool 2: aggregate_orders — time-windowed spend/orders from real order data
# ──────────────────────────────────────────────────────────────────────────

def aggregate_orders(time_window='this_month', group_by='customer', metric='sum_spend', city=None, segment=None, limit=10):
    """
    Aggregate the ORDERS cache over a time window — this is what answers
    'spend THIS MONTH' (vs lifetime). Optionally scoped by city/segment
    (joined via the customer cache). Every param is allow-listed.
    Returns {'window': str, 'metric': str, 'rows': [...], 'note': str|None}.
    """
    now = datetime.utcnow()
    if time_window not in _TIME_WINDOWS:
        time_window = 'this_month'
    if group_by not in _AGG_GROUP:
        group_by = 'customer'
    if metric not in _AGG_METRIC:
        metric = 'sum_spend'

    start = _TIME_WINDOWS[time_window](now)

    base = db.session.query(OrderCache).join(
        CustomerCache, CustomerCache.shopify_customer_id == OrderCache.shopify_customer_id
    )
    if start is not None:
        base = base.filter(OrderCache.order_date >= start)
    if city:
        base = base.filter(CustomerCache.city.ilike(f"%{str(city).strip()}%"))
    if segment and str(segment).strip().lower() in _SEGMENTS:
        base = base.filter(func.lower(CustomerCache.segment) == str(segment).strip().lower())

    # group column + label
    if group_by == 'customer':
        grp = CustomerCache.shopify_customer_id
        label_cols = [CustomerCache.first_name, CustomerCache.last_name, CustomerCache.city, CustomerCache.segment]
    elif group_by == 'city':
        grp = CustomerCache.city
        label_cols = [CustomerCache.city]
    else:  # segment
        grp = CustomerCache.segment
        label_cols = [CustomerCache.segment]

    rev = func.coalesce(func.sum(OrderCache.total), 0)
    cnt = func.count(OrderCache.id)

    rows_q = (
        base.with_entities(grp.label('grp'), *label_cols, rev.label('revenue'), cnt.label('orders'))
            .group_by(grp, *label_cols)
    )

    # sort by chosen metric
    if metric == 'order_count':
        rows_q = rows_q.order_by(cnt.desc())
    else:  # sum_spend or aov both rank by revenue primarily
        rows_q = rows_q.order_by(rev.desc())

    n = _clamp_limit(limit)
    results = rows_q.limit(n).all()

    out = []
    for r in results:
        revenue = float(r.revenue or 0)
        orders = int(r.orders or 0)
        if group_by == 'customer':
            name = ' '.join(p for p in [r[1], r[2]] if p) or 'Unknown'
            entry = {'name': name, 'city': r[3], 'segment': r[4]}
        elif group_by == 'city':
            entry = {'city': r[1] or 'Unknown'}
        else:
            entry = {'segment': r[1] or 'Unknown'}
        entry['revenue'] = round(revenue)
        entry['orders'] = orders
        if metric == 'aov':
            entry['aov'] = round(revenue / orders) if orders else 0
        out.append(entry)

    note = None
    if not out:
        note = 'No orders found for that window/filters (order cache may be sparse).'
    return {'window': time_window, 'metric': metric, 'group_by': group_by, 'rows': out, 'note': note}