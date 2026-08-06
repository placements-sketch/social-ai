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
    Shop Zetu is an ONLINE-ONLY store — it has no physical shops of its own.
    (Shopify "locations" are fulfilment/warehouse points, not customer-facing
    stores, and the physical branches belong to the sister brand Vivo, which
    this app does not represent.) So instead of listing addresses, we tell the
    AI the brand is online-only and delivers across Kenya.
    """
    base = (
        "Shop Zetu is an online-only store — it does NOT have any physical shops "
        "or walk-in branches of its own. All Shop Zetu orders are placed online "
        "and delivered across Kenya. If a customer asks to visit a Shop Zetu "
        "store or asks where our shops are, explain warmly that we are "
        "online-only and offer to help them order online with delivery to their "
        "location.\n"
        # The blanket ban that used to end this block — "never refer customers
        # to Vivo or any other brand's stores" — was written when Vivo was
        # treated as a separate business this app did not represent. It is not:
        # Shop Zetu manages products and stock for a number of brands, Vivo
        # among them, and a customer asking where they can try a Vivo piece on
        # is asking a reasonable question we can answer. Refusing on principle
        # sent them away for no reason.
        #
        # What replaces it is narrower and safer: answer from what the business
        # has actually written down, never from memory. An invented branch
        # address sends a real person across Nairobi to a shop that isn't there.
        "Shop Zetu manages products for other brands, some of which DO have "
        "their own physical stores. If a customer asks where they can find a "
        "particular brand in person, answer ONLY from the brand store list "
        "below (or the 'About the business' section, if it says something "
        "relevant). If the branch they want is not listed, say you don't have "
        "details for that one and offer to help them order online instead. "
        "Never state or guess a street address, branch, mall or phone number "
        "that is not written down for you."
    )
    return base + _format_brand_stores()


def _format_brand_stores() -> str:
    """
    The brand stores block, or "" if none are configured.

    Kept in StoreInfoCache under kind='brand_stores', NOT kind='locations'.
    That key already belongs to sync_locations_now(), which overwrites it with
    Shopify's fulfilment locations — warehouses and pickup points, not
    customer-facing shops. Sharing the key would mean these addresses survive
    exactly until the next Shopify sync, and then vanish without anyone
    noticing.

    Rendered compactly and factored: hours are stated once for all branches
    rather than repeated per store. The naive layout ran to four lines each,
    which on twenty-one stores is most of a page carried by every reply,
    including "what sizes does this come in?".
    """
    try:
        row = StoreInfoCache.query.filter_by(kind='brand_stores').first()
        stores = row.data if (row and isinstance(row.data, list)) else []
    except Exception:
        return ""
    if not stores:
        return ""

    lines = []
    # State shared hours once if every branch agrees, which is the normal case.
    hours = {(s.get('hours') or '').strip() for s in stores if s.get('hours')}
    shared = hours.pop() if len(hours) == 1 else None

    lines.append("\n\nBrand stores you MAY give addresses for (these are the "
                 "brand's own shops, not Shop Zetu's):")
    if shared:
        lines.append(f"All branches: {shared}")
    for s in stores:
        if not (s.get('name') or '').strip():
            continue
        bits = [s['name'].strip()]
        for key in ('address', 'area'):
            if (s.get(key) or '').strip():
                bits.append(s[key].strip())
        if (s.get('phone') or '').strip():
            bits.append(s['phone'].strip())
        if not shared and (s.get('hours') or '').strip():
            bits.append(s['hours'].strip())
        lines.append("  - " + " | ".join(bits))
    return "\n".join(lines)