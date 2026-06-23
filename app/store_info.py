"""
app/store_info.py
Store-wide info cache layer — locations, shipping zones, active discounts.

Data lives in store_info_cache (one row per kind). Reads use a small in-process
TTL cache so the AI pipeline doesn't hit the DB on every message.

Sync is on-demand via /api/store-info/sync (admin only).
"""

from datetime import datetime, timedelta
from app import db
from app.models import StoreInfoCache
from app.utils.logger import log_event


# In-process cache so the AI pipeline doesn't query the DB on every reply.
# Locations don't change often; a 5-minute TTL is plenty.
_CACHE = {}
_CACHE_TTL = timedelta(minutes=5)


def _cache_get(kind: str):
    entry = _CACHE.get(kind)
    if entry is None:
        return None
    cached_at, value = entry
    if datetime.utcnow() - cached_at > _CACHE_TTL:
        return None
    return value


def _cache_set(kind: str, value):
    _CACHE[kind] = (datetime.utcnow(), value)


def _cache_invalidate(kind: str = None):
    if kind:
        _CACHE.pop(kind, None)
    else:
        _CACHE.clear()


def get_cached_locations() -> list[dict]:
    """
    Return the cached list of physical store locations.
    Returns [] if nothing has been synced yet.
    """
    cached = _cache_get('locations')
    if cached is not None:
        return cached

    row = StoreInfoCache.query.filter_by(kind='locations').first()
    value = row.data if row else []
    _cache_set('locations', value)
    return value


def sync_locations_now() -> dict:
    """
    Fetch locations from Shopify and write them to the cache.
    Returns a result dict suitable for use as a sync_jobs result.
    """
    from app.integrations.shopify import list_all_locations

    locations = list_all_locations()

    row = StoreInfoCache.query.filter_by(kind='locations').first()
    if row is None:
        row = StoreInfoCache(kind='locations', data=locations)
        db.session.add(row)
    else:
        row.data = locations
        row.updated_at = datetime.utcnow()
    db.session.commit()

    _cache_invalidate('locations')  # force a fresh read next time

    log_event("info", "store_info.sync_locations",
              f"Synced {len(locations)} locations to cache")
    return {
        "locations_synced": len(locations),
        "locations": [
            {"name": loc.get("name"), "city": loc.get("city")}
            for loc in locations
        ],
    }


def format_locations_for_prompt() -> str:
    """
    Format the cached locations as a string block to inject into Claude's
    system prompt. Returns an empty string if no locations are synced yet.
    """
    locations = get_cached_locations()
    if not locations:
        return ""

    lines = ["Shop Zetu physical store locations:"]
    for loc in locations:
        # Build a compact one-line representation per shop
        parts = [loc.get("name") or "Branch"]
        addr_bits = [
            loc.get("address1"),
            loc.get("city"),
        ]
        addr = ", ".join([b for b in addr_bits if b])
        if addr:
            parts.append(addr)
        if loc.get("phone"):
            parts.append(f"phone: {loc['phone']}")
        lines.append(f"  - {' | '.join(parts)}")

    return "\n".join(lines)