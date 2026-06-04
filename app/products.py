"""
app/products.py
Products administration — read-only view of the Shopify catalog,
mirrored locally in products_cache.

Endpoints (all JWT-protected, /api prefix):
  GET    /api/products              list cached products (paginated)
  GET    /api/products/<id>         single product detail
  GET    /api/products/sync/status  cheap: last_synced_at + stale flag
  POST   /api/products/sync/check   moderate: diff vs Shopify (no writes)
  POST   /api/products/sync         full: mirror Shopify into the cache

Cache philosophy:
  products_cache mirrors Shopify exactly. No manual edits; no manual deletes.
  Sync upserts existing rows by shopify_product_id, inserts new ones, and
  deletes rows that no longer exist in Shopify.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import re

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app import db
from app.models import AuthUser, ProductCache
from app.auth import log_audit, current_user_id

from app.integrations.shopify import list_all_products

products_bp = Blueprint('products', __name__, url_prefix='/api')


# Anything older than this is "stale" — the page shows a sync prompt.
STALE_AFTER = timedelta(hours=12)

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _parse_price(price_value) -> Decimal | None:
    """
    Shopify mock returns price like 'KES 3,500'. Real Shopify returns a
    numeric string. Strip non-numeric chars and parse.
    """
    if price_value is None:
        return None
    if isinstance(price_value, (int, float, Decimal)):
        try:
            return Decimal(str(price_value))
        except InvalidOperation:
            return None
    s = re.sub(r'[^0-9.]', '', str(price_value))
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _format_price(value) -> str | None:
    """Format the numeric price column back to 'KES 3,500' for display."""
    if value is None:
        return None
    try:
        n = Decimal(value)
    except InvalidOperation:
        return None
    # No fractional part for KES (mock uses whole numbers); preserve cents otherwise.
    if n == n.to_integral_value():
        return f"KES {int(n):,}"
    return f"KES {n:,.2f}"


def _serialize_product(p: ProductCache) -> dict:
    return {
        'id': p.id,
        'shopify_product_id': p.shopify_product_id,
        'name': p.name,
        'description': p.description,
        'price': _format_price(p.price),       # display string
        'price_value': float(p.price) if p.price is not None else None,  # numeric
        'variants': p.variants or [],
        'images': p.images or [],
        'tags': p.tags or [],
        'cached_at': p.cached_at.isoformat() if p.cached_at else None,
    }


def _shopify_to_cache_dict(sp: dict) -> dict:
    """Normalize a Shopify product dict into the columns of products_cache."""
    return {
        'shopify_product_id': str(sp.get('shopify_id') or sp.get('id') or ''),
        'name': sp.get('name', ''),
        'description': sp.get('description'),
        'price': _parse_price(sp.get('price')),
        'variants': sp.get('variants', []) or [],
        'images': sp.get('images', []) or [],
        'tags': sp.get('tags', []) or [],
    }


def _row_matches_shopify(row: ProductCache, snap: dict) -> bool:
    """Return True if the cached row already matches the Shopify snapshot."""
    return (
        row.name == snap['name']
        and row.description == snap['description']
        and (row.price or None) == (snap['price'] or None)
        and (row.variants or []) == (snap['variants'] or [])
        and (row.images or []) == (snap['images'] or [])
        and (row.tags or []) == (snap['tags'] or [])
    )


def _last_synced_at():
    return db.session.query(func.max(ProductCache.cached_at)).scalar()


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@products_bp.route('/products', methods=['GET'])
@jwt_required()
def list_products():
    """
    List cached products with pagination + optional search.

    Query params:
      page      default 1
      per_page  default 20, max 100
      search    case-insensitive match on name

    Response:
      { products, total, page, per_page, last_synced_at, stale }
    """
    page = max(1, request.args.get('page', default=1, type=int))
    per_page = request.args.get('per_page', default=DEFAULT_PER_PAGE, type=int)
    if per_page < 1: per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE: per_page = MAX_PER_PAGE

    search = request.args.get('search', type=str)

    query = ProductCache.query
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(ProductCache.name.ilike(like))

    total = query.count()
    rows = (
        query.order_by(ProductCache.name.asc())
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    last = _last_synced_at()
    stale = (last is None) or (utc_now() - last) > STALE_AFTER

    return jsonify({
        'products': [_serialize_product(p) for p in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'last_synced_at': last.isoformat() if last else None,
        'stale': stale,
    }), 200


@products_bp.route('/products/<int:product_id>', methods=['GET'])
@jwt_required()
def get_product(product_id):
    """Single cached product by primary key."""
    p = ProductCache.query.get(product_id)
    if not p:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'product': _serialize_product(p)}), 200


@products_bp.route('/products/sync/status', methods=['GET'])
@jwt_required()
def sync_status():
    """
    Cheap status — last_synced_at, product_count, stale flag.
    Used by the page banner. Does NOT hit Shopify.
    """
    last = _last_synced_at()
    count = ProductCache.query.count()
    stale = (last is None) or (utc_now() - last) > STALE_AFTER
    return jsonify({
        'last_synced_at': last.isoformat() if last else None,
        'product_count': count,
        'stale': stale,
        'stale_threshold_hours': int(STALE_AFTER.total_seconds() // 3600),
    }), 200


@products_bp.route('/products/sync/check', methods=['POST'])
@jwt_required()
def sync_check():
    """
    Hits Shopify, compares to local cache, returns the diff WITHOUT writing.
    Used by the "Check for changes" button.

    Response:
      {
        ok: true,
        added:   [{shopify_product_id, name, price}, ...],   # in Shopify, not cached
        updated: [{shopify_product_id, name, price}, ...],   # in both but different
        removed: [{shopify_product_id, name}, ...],          # in cache, not in Shopify
        in_sync: bool                                         # true iff all three are empty
      }
    """
    if AuthUser.query.get(current_user_id()) is None:
        return jsonify({'error': 'User not found'}), 404

    try:
        shopify = list_all_products()
    except NotImplementedError:
        return jsonify({
            'ok': False,
            'reason': 'shopify_not_configured',
            'message': 'Shopify integration is not yet configured. Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN.',
        }), 200
    except Exception as e:
        return jsonify({'ok': False, 'reason': 'shopify_error', 'message': str(e)}), 502

    snapshot = {s['shopify_product_id']: s for s in (_shopify_to_cache_dict(p) for p in shopify)}
    cached = {r.shopify_product_id: r for r in ProductCache.query.all()}

    added, updated, removed = [], [], []
    for spid, snap in snapshot.items():
        if spid not in cached:
            added.append({'shopify_product_id': spid, 'name': snap['name'],
                          'price': _format_price(snap['price'])})
        elif not _row_matches_shopify(cached[spid], snap):
            updated.append({'shopify_product_id': spid, 'name': snap['name'],
                            'price': _format_price(snap['price'])})
    for spid, row in cached.items():
        if spid not in snapshot:
            removed.append({'shopify_product_id': spid, 'name': row.name})

    in_sync = not (added or updated or removed)
    return jsonify({
        'ok': True,
        'added': added,
        'updated': updated,
        'removed': removed,
        'in_sync': in_sync,
        'checked_at': utc_now().isoformat(),
    }), 200


@products_bp.route('/products/sync', methods=['POST'])
@jwt_required()
def sync_products():
    """
    Mirror Shopify into the cache.
      - Insert products that are in Shopify but not cached
      - Update cached rows whose fields differ
      - Delete cached rows no longer in Shopify

    Returns counts and the diff that was applied.
    """
    current_user = AuthUser.query.get(current_user_id())
    if current_user is None:
        return jsonify({'error': 'User not found'}), 404

    try:
        shopify = list_all_products()
    except NotImplementedError:
        return jsonify({
            'ok': False,
            'reason': 'shopify_not_configured',
            'message': 'Shopify integration is not yet configured. Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN.',
        }), 200
    except Exception as e:
        return jsonify({'ok': False, 'reason': 'shopify_error', 'message': str(e)}), 502

    snapshot = {s['shopify_product_id']: s for s in (_shopify_to_cache_dict(p) for p in shopify)}
    cached = {r.shopify_product_id: r for r in ProductCache.query.all()}

    now = utc_now()
    added_count = updated_count = removed_count = 0
    added, updated, removed = [], [], []

    # Inserts + updates
    for spid, snap in snapshot.items():
        if spid in cached:
            row = cached[spid]
            if not _row_matches_shopify(row, snap):
                row.name = snap['name']
                row.description = snap['description']
                row.price = snap['price']
                row.variants = snap['variants']
                row.images = snap['images']
                row.tags = snap['tags']
                row.cached_at = now
                updated_count += 1
                updated.append({'shopify_product_id': spid, 'name': snap['name']})
            else:
                # In sync but refresh the cached_at so staleness is honest.
                row.cached_at = now
        else:
            new_row = ProductCache(
                shopify_product_id=spid,
                name=snap['name'],
                description=snap['description'],
                price=snap['price'],
                variants=snap['variants'],
                images=snap['images'],
                tags=snap['tags'],
                cached_at=now,
            )
            db.session.add(new_row)
            added_count += 1
            added.append({'shopify_product_id': spid, 'name': snap['name']})

    # Deletes
    for spid, row in cached.items():
        if spid not in snapshot:
            db.session.delete(row)
            removed_count += 1
            removed.append({'shopify_product_id': spid, 'name': row.name})

    db.session.commit()

    log_audit(
        current_user.id,
        'sync_products',
        resource_type='products',
        resource_id=None,
        changes={'added': added_count, 'updated': updated_count, 'removed': removed_count},
    )

    return jsonify({
        'ok': True,
        'added': added,
        'updated': updated,
        'removed': removed,
        'added_count': added_count,
        'updated_count': updated_count,
        'removed_count': removed_count,
        'synced_at': now.isoformat(),
        'total_products': ProductCache.query.count(),
    }), 201

