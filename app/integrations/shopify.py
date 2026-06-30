"""
app/integrations/shopify.py
Shopify Admin API integration — product metadata AND stock levels.
Shopify is now the single source of truth for all product and inventory data.

Current state: MOCK — returns hardcoded data.
To activate: implement the _real_* functions and flip USE_MOCK = False.

Authentication:
  - Uses OAuth flow: exchange SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET for access token
  - Token is cached in memory (or could be persisted to DB for multi-instance deployments)
  - Docs: https://shopify.dev/docs/api/admin-rest/2024-01
"""

import os
from datetime import datetime, timezone, timedelta
import requests
from app.utils.logger import log_event

from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Module-level session with built-in retry on transient Shopify failures.
# This handles 429 (rate limit), 502/503/504 (Shopify server hiccups),
# and connection errors with exponential backoff.
_shopify_session = None

def _get_shopify_session():
    """Returns a singleton requests.Session configured with retry-with-backoff.
    Retries: 5 attempts total, waits 2s/4s/8s/16s/32s between them.
    Total worst-case extra delay before giving up: ~62 seconds."""
    global _shopify_session
    if _shopify_session is None:
        _shopify_session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET', 'POST'],
            raise_on_status=False,
            respect_retry_after_header=True,  # honour Shopify's Retry-After on rate limits
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        _shopify_session.mount('https://', adapter)
        _shopify_session.mount('http://', adapter)
    return _shopify_session

USE_MOCK = False  # Flip to False once Shopify credentials are configured

# Token cache (in production, store in DB or Redis).
# Tokens expire after 24h per Shopify docs; we refresh proactively
# with a small safety buffer to avoid using one that's about to expire.
_SHOPIFY_ACCESS_TOKEN = None
_SHOPIFY_TOKEN_EXPIRES_AT = None  # datetime | None
_TOKEN_REFRESH_BUFFER = timedelta(minutes=5)


def _get_shopify_access_token():
    """
    Exchange Client ID + Secret for an Admin API access token.
    Caches the token in memory (expires after 24 hours per Shopify docs).
    
    Endpoint: POST https://{shop}.myshopify.com/admin/oauth/access_token
    Content-Type: application/x-www-form-urlencoded
    Body: grant_type=client_credentials&client_id={id}&client_secret={secret}
    
    Response: {"access_token": "shpat_xxxxx", "scope": "read_products,...", "expires_in": 86399}
    """
    global _SHOPIFY_ACCESS_TOKEN, _SHOPIFY_TOKEN_EXPIRES_AT
    
    # Return the cached token only if it's not about to expire.
    if _SHOPIFY_ACCESS_TOKEN and _SHOPIFY_TOKEN_EXPIRES_AT:
        if datetime.utcnow() < (_SHOPIFY_TOKEN_EXPIRES_AT - _TOKEN_REFRESH_BUFFER):
            return _SHOPIFY_ACCESS_TOKEN
    
    store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    client_id = os.getenv('SHOPIFY_CLIENT_ID')
    client_secret = os.getenv('SHOPIFY_CLIENT_SECRET')
    
    if not all([store_url, client_id, client_secret]):
        raise ValueError("SHOPIFY_STORE_URL, SHOPIFY_CLIENT_ID, and SHOPIFY_CLIENT_SECRET are required")
    
    # Extract shop name from store URL (e.g., https://my-store.myshopify.com -> my-store)
    shop_name = store_url.split('//')[1].split('.')[0] if '//' in store_url else None
    
    if not shop_name:
        raise ValueError(f"Invalid SHOPIFY_STORE_URL format: {store_url}")
    
    token_url = f"https://{shop_name}.myshopify.com/admin/oauth/access_token"
    
    # Use application/x-www-form-urlencoded per Shopify docs
    payload = f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        response = _get_shopify_session().post(token_url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        _SHOPIFY_ACCESS_TOKEN = data.get('access_token')
        if not _SHOPIFY_ACCESS_TOKEN:
            raise ValueError(f"No access_token in Shopify response: {data}")
        
        expires_in = int(data.get('expires_in', 86399))
        _SHOPIFY_TOKEN_EXPIRES_AT = datetime.utcnow() + timedelta(seconds=expires_in)
        log_event("info", "integrations.shopify.token",
                  f"Access token obtained",
                  payload={"expires_at": _SHOPIFY_TOKEN_EXPIRES_AT.isoformat()})
        return _SHOPIFY_ACCESS_TOKEN
    
    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to get access token: {str(e)}")
        raise


def get_product_info(keyword: str) -> dict:
    """
    Fetches product metadata from Shopify by keyword search.
    Returns name, description, price, variants, stock quantity.
    """
    if USE_MOCK:
        return _mock_get_product_info(keyword)
    return _real_get_product_info(keyword)


def get_stock_level(keyword: str) -> dict:
    """
    Returns stock level for a product from Shopify inventory.
    Shopify is the single source of truth for all inventory data.
    """
    if USE_MOCK:
        product = _mock_get_product_info(keyword)
        return {
            "product_name": product.get("name", keyword),
            "quantity": product.get("stock_quantity", 0),
            "unit": "pcs",
        }
    return _real_get_stock_level(keyword)

def list_all_products() -> list[dict]:
    """
    Returns the FULL catalog from Shopify — used by the Products page sync.
    Each dict has the same shape as get_product_info() returns.
    """
    if USE_MOCK:
        return _mock_list_all_products()
    return _real_list_all_products()

def search_products(keyword, limit: int = 3) -> list[dict]:
    """
    Search the local ProductCache. Accepts either:
      - a single keyword string (matches across name/desc/variants/tags), OR
      - a list of keywords (products matching MORE terms rank higher).
    Returns up to `limit` matches, best first.
    """
    if not keyword:
        return []
    # Normalize to a list
    terms = [keyword] if isinstance(keyword, str) else list(keyword)
    terms = [t for t in terms if t and t.strip()]
    if not terms:
        return []

    if USE_MOCK:
        return _mock_search_products(terms, limit=limit)
    return _cache_search_products(terms, limit=limit)

# ─────────────────────────────────────────────
# Mock implementation
# ─────────────────────────────────────────────

_MOCK_PRODUCTS = [
    {
        "shopify_id": "001",
        "name": "Floral Wrap Dress",
        "description": "A lightweight floral wrap dress perfect for any occasion.",
        "price": "KES 3,500",
        "variants": ["XS", "S", "M", "L", "XL"],
        "stock_quantity": 14,
    },
    {
        "shopify_id": "002",
        "name": "Matte Lipstick",
        "description": "Long-lasting matte lipstick available in 12 shades.",
        "price": "KES 850",
        "variants": ["Red", "Nude", "Berry", "Coral"],
        "stock_quantity": 52,
    },
    {
        "shopify_id": "003",
        "name": "Vitamin C Serum",
        "description": "Brightening serum with 20% Vitamin C for glowing skin.",
        "price": "KES 2,200",
        "variants": ["30ml", "50ml"],
        "stock_quantity": 0,
    },
    {
        "shopify_id": "004",
        "name": "Black Wrap Dress",
        "description": "An elegant black wrap dress for evening occasions.",
        "price": "KES 4,200",
        "variants": ["XS", "S", "M", "L", "XL"],
        "stock_quantity": 8,
    },
    {
        "shopify_id": "005",
        "name": "Hydrating Moisturizer",
        "description": "Deep hydration moisturizer for all skin types.",
        "price": "KES 1,800",
        "variants": ["50ml", "100ml"],
        "stock_quantity": 23,
    },
]

def _mock_list_all_products() -> list[dict]:
    """Returns the entire mock catalog."""
    log_event("info", "integrations.shopify", f"Mock catalog: {len(_MOCK_PRODUCTS)} products")
    return list(_MOCK_PRODUCTS)


def _mock_get_product_info(keyword: str) -> dict:
    keyword_lower = keyword.lower()
    for product in _MOCK_PRODUCTS:
        if keyword_lower in product["name"].lower():
            log_event("info", "integrations.shopify", f"Mock product found for '{keyword}'")
            return product

    log_event("info", "integrations.shopify", f"No mock product matched '{keyword}', using fallback")
    return {
        "shopify_id": "000",
        "name": keyword.title(),
        "description": "A beautiful piece from our latest collection.",
        "price": "KES 1,800",
        "variants": [],
        "stock_quantity": 0,
    }

def _mock_search_products(terms: list[str], limit: int = 3) -> list[dict]:
    """Multi-term search over the in-memory mock catalog."""
    if not terms:
        return []

    expanded = []
    for t in terms:
        t = t.lower().strip()
        if not t:
            continue
        expanded.append(t)
        if len(t) > 3 and t.endswith('s'):
            expanded.append(t.rstrip('s'))

    matches = []
    for product in _MOCK_PRODUCTS:
        name_lc = product["name"].lower()
        desc_lc = (product.get("description") or "").lower()
        variants_lc = " ".join(str(v).lower() for v in product.get("variants", []))

        score = 0
        for term in expanded:
            if term in name_lc:        score += 10
            elif term in variants_lc:  score += 5
            elif term in desc_lc:      score += 2

        if score > 0:
            matches.append((score, product))

    matches.sort(key=lambda x: -x[0])
    return [p for _, p in matches[:limit]]

# ─────────────────────────────────────────────
# Real Shopify implementation (TODO)
# ─────────────────────────────────────────────

def _cache_search_products(terms: list[str], limit: int = 3) -> list[dict]:
    """
    Multi-term ProductCache search. Each term contributes to the score based on
    where it hits (name > variants > tags > description). Products that match
    multiple terms naturally outrank single-term matches.
    """
    try:
        from app.models import ProductCache
        from app import db
        from sqlalchemy import or_, case, cast, String

        # Build a combined OR filter across all terms + a summed score expression
        like_clauses = []
        score_components = []

        for raw in terms:
            t = raw.lower().strip()
            t_singular = t.rstrip('s') if len(t) > 3 and t.endswith('s') else t
            for kw in {t, t_singular}:
                like_kw = f"%{kw}%"
                like_clauses.extend([
                    ProductCache.name.ilike(like_kw),
                    cast(ProductCache.variants, String).ilike(like_kw),
                    cast(ProductCache.tags, String).ilike(like_kw),
                    ProductCache.description.ilike(like_kw),
                ])
                score_components.append(case((ProductCache.name.ilike(like_kw), 10), else_=0))
                score_components.append(case((cast(ProductCache.variants, String).ilike(like_kw), 5), else_=0))
                score_components.append(case((cast(ProductCache.tags, String).ilike(like_kw), 4), else_=0))
                score_components.append(case((ProductCache.description.ilike(like_kw), 2), else_=0))

        if not like_clauses:
            return []

        # Sum all score components into one expression
        score = score_components[0]
        for c in score_components[1:]:
            score = score + c
        score = score.label('score')

        rows = (
            db.session.query(ProductCache, score)
            .filter(or_(*like_clauses))
            .order_by(
                # In-stock products first. NULL stock = unknown, treat as available.
                (ProductCache.stock_quantity == 0).asc(),
                score.desc(),
                ProductCache.name.asc(),
            )
            .limit(limit)
            .all()
        )

        result = []
        for product, _score in rows:
            result.append({
                "shopify_id": product.shopify_product_id,
                "name": product.name,
                "handle": product.handle,
                "description": (product.description or '')[:200],
                "price": str(product.price) if product.price is not None else 'N/A',
                "variants": product.variants or [],
                "stock_quantity": product.stock_quantity or 0,
            })

        log_event("info", "integrations.shopify.cache_search",
                  f"Cache search for {terms}: {len(result)} matches",
                  payload={"terms": terms,
                           "matches": [p["name"] for p in result]})
        return result

    except Exception as e:
        log_event("error", "integrations.shopify.cache_search",
                  f"Cache search failed for {terms}: {str(e)}")
        return []
    
def _real_get_product_info(keyword: str) -> dict:
    """
    Fetches product metadata from Shopify by keyword search.
    
    Endpoint: GET /admin/api/2024-01/products.json?title=<keyword>
    Docs: https://shopify.dev/docs/api/admin-rest/2024-01/resources/product
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }
        
        # Search by product title
        url = f"{store_url}/admin/api/2024-01/products.json?title={keyword}"
        response = _get_shopify_session().get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        products = response.json().get('products', [])
        if not products:
            log_event("info", "integrations.shopify", f"No Shopify product found for '{keyword}'")
            return {
                "shopify_id": "000",
                "name": keyword.title(),
                "description": "Product not found in Shopify catalog.",
                "price": "N/A",
                "variants": [],
                "stock_quantity": 0,
            }
        
        product = products[0]
        
        # Sum inventory across ALL variants — a product with size S/M/L has
        # inventory tracked per variant; taking [0] alone undercounts.
        # `inventory_quantity` may be null if the variant isn't tracked
        # or your token lacks read_inventory scope; treat null as 0.
        stock_quantity = sum(
            (v.get('inventory_quantity') or 0) for v in product.get('variants', [])
        )
        
        log_event("info", "integrations.shopify", f"Product found: {product['title']}")
        return {
            "shopify_id": str(product['id']),
            "name": product.get('title', keyword),
            "handle": product.get('handle') or '',
            "description": product.get('body_html', '')[:200],
            "price": f"KES{product['variants'][0].get('price', 'N/A')}" if product.get('variants') else "N/A",
            "variants": [v.get('title', '') for v in product.get('variants', [])],
            "stock_quantity": stock_quantity,
        }
    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to fetch product: {str(e)}")
        raise


def _real_get_stock_level(keyword: str) -> dict:
    """
    Fetches inventory level for a product from Shopify.
    """
    try:
        product = _real_get_product_info(keyword)
        return {
            "product_name": product.get("name", keyword),
            "quantity": product.get("stock_quantity", 0),
            "unit": "pcs",
        }
    except Exception as e:
        log_event("error", "integrations.shopify", f"Failed to fetch stock level: {str(e)}")
        raise


def _real_list_all_products() -> list[dict]:
    """
    Pages through Shopify's full product catalog.
    Shopify paginates using the Link header with rel="next".
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()

        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        all_products = []
        url = f"{store_url}/admin/api/2024-01/products.json?limit=250&status=active&published_status=published"

        while url:
            response = _get_shopify_session().get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for product in response.json().get('products', []):
                variants = product.get('variants') or []

                # Inventory is "tracked" only if at least one variant is managed by Shopify
                inventory_tracked = any(v.get('inventory_management') == 'shopify' for v in variants)

                # Sum stock only across tracked variants; None means untracked product
                stock_quantity = sum(
                    (v.get('inventory_quantity') or 0) for v in variants
                    if v.get('inventory_management') == 'shopify'
                ) if inventory_tracked else None

                all_products.append({
                    "shopify_id": str(product['id']),
                    "name": product.get('title', 'Unknown'),
                    "handle": product.get('handle') or '',
                    "description": (product.get('body_html') or '')[:200],
                    "price": f"KES {variants[0].get('price', 'N/A')}" if variants else "N/A",
                    "variants": [v.get('title', '') for v in variants],
                    "stock_quantity": stock_quantity,
                    "inventory_tracked": inventory_tracked,
                })

            # Pagination: extract next URL from Link header
            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify.sync",
                  f"Shopify sync completed — {len(all_products)} products updated",
                  payload={"count": len(all_products), "kind": "products"})
        return all_products

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to fetch catalog: {str(e)}")
        raise

def iter_all_products():
    """
    Generator version of list_all_products. Yields one product at a time as we
    page through Shopify, so callers never need to hold the full list in memory.

    Same dict shape as list_all_products. Use this for sync loops that process
    products one-by-one. Use list_all_products only when you actually need the
    whole list at once (e.g., for diff/check operations).
    """
    if USE_MOCK:
        return
    yield from _real_iter_all_products()


def _real_iter_all_products():
    """Streams products page by page. Same shape as _real_list_all_products."""
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()

        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        url = f"{store_url}/admin/api/2024-01/products.json?limit=250&status=active&published_status=published"
        total_yielded = 0

        while url:
            response = _get_shopify_session().get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for product in response.json().get('products', []):
                variants = product.get('variants') or []
                inventory_tracked = any(v.get('inventory_management') == 'shopify' for v in variants)
                stock_quantity = sum(
                    (v.get('inventory_quantity') or 0) for v in variants
                    if v.get('inventory_management') == 'shopify'
                ) if inventory_tracked else None

                yield {
                    "shopify_id": str(product['id']),
                    "name": product.get('title', 'Unknown'),
                    "handle": product.get('handle') or '',
                    "description": (product.get('body_html') or '')[:200],
                    "price": f"KES {variants[0].get('price', 'N/A')}" if variants else "N/A",
                    "variants": [v.get('title', '') for v in variants],
                    "stock_quantity": stock_quantity,
                    "inventory_tracked": inventory_tracked,
                }
                total_yielded += 1

            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify.sync",
                  f"Shopify products stream completed — {total_yielded} products",
                  payload={"count": total_yielded, "kind": "products_stream"})

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed during product stream: {str(e)}")
        raise

def list_all_locations() -> list[dict]:
    """
    Fetch all physical store locations from Shopify. Used by store-info sync
    to populate the AI's brand-context. Locations are small (a handful per store)
    so we don't paginate.
    """
    if USE_MOCK:
        return []
    return _real_list_all_locations()


def _real_list_all_locations() -> list[dict]:
    """GET /admin/api/2024-01/locations.json — requires read_locations scope."""
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }
        url = f"{store_url}/admin/api/2024-01/locations.json"
        response = _get_shopify_session().get(url, headers=headers, timeout=15)
        response.raise_for_status()

        locations = response.json().get('locations', [])
        result = []
        for loc in locations:
            if not loc.get('active'):
                continue  # skip deactivated locations
            result.append({
                "shopify_id": str(loc.get('id')),
                "name": loc.get('name'),
                "address1": loc.get('address1') or '',
                "address2": loc.get('address2') or '',
                "city": loc.get('city') or '',
                "province": loc.get('province') or '',
                "country": loc.get('country_name') or loc.get('country') or '',
                "zip": loc.get('zip') or '',
                "phone": loc.get('phone') or '',
            })

        log_event("info", "integrations.shopify.sync",
                  f"Shopify locations fetched — {len(result)} active locations",
                  payload={"count": len(result), "kind": "locations"})
        return result

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to fetch locations: {str(e)}")
        raise
    
# ─────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────

def list_all_customers() -> list[dict]:
    """
    Full customer list from Shopify, paginated.
    Each customer dict includes order summary (orders_count, total_spent, last_order).
    """
    if USE_MOCK:
        return []  # No mock customers — flip USE_MOCK to False before using.
    return _real_list_all_customers()


def get_customer_orders(shopify_customer_id: str) -> list[dict]:
    """
    Fetch all orders for a single customer. Used by the detail page on demand.
    """
    if USE_MOCK:
        return []
    return _real_get_customer_orders(shopify_customer_id)


def _real_list_all_customers() -> list[dict]:
    """
    GET /admin/api/2024-01/customers.json?limit=250
    Shopify includes order summary fields directly on the customer object:
      orders_count, total_spent, last_order_id, last_order_name
    But NOT last_order_date — we'd need an extra orders query for that.
    For the first sync we use shopify's updated_at as a proxy for activity.
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        all_customers = []
        url = f"{store_url}/admin/api/2024-01/customers.json?limit=250"

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for c in response.json().get('customers', []):
                default_address = c.get('default_address') or {}
                all_customers.append({
                    "shopify_id": str(c['id']),
                    "email": c.get('email'),
                    "first_name": c.get('first_name'),
                    "last_name": c.get('last_name'),
                    "phone": c.get('phone') or default_address.get('phone'),
                    "city": default_address.get('city'),
                    "country": default_address.get('country'),
                    "accepts_marketing": bool(c.get('accepts_marketing', False)),
                    "tags": [t.strip() for t in (c.get('tags') or '').split(',') if t.strip()],
                    "total_orders": int(c.get('orders_count', 0) or 0),
                    "total_spent": float(c.get('total_spent', 0) or 0),
                    "shopify_created_at": c.get('created_at'),
                    "updated_at": c.get('updated_at'),
                })

            # Pagination via Link header
            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify.sync",
                  f"Shopify sync completed — {len(all_customers)} customers updated",
                  payload={"count": len(all_customers), "kind": "customers"})
        return all_customers

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to fetch customers: {str(e)}")
        raise

def iter_all_customers():
    """
    Generator version of list_all_customers. Yields one customer at a time
    so callers never need to hold all 160k+ customers in memory.
    """
    if USE_MOCK:
        return
    yield from _real_iter_all_customers()


def _real_iter_all_customers():
    """Streams customers page by page. Same dict shape as _real_list_all_customers."""
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        url = f"{store_url}/admin/api/2024-01/customers.json?limit=250"
        total_yielded = 0

        while url:
            response = _get_shopify_session().get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for c in response.json().get('customers', []):
                default_address = c.get('default_address') or {}
                yield {
                    "shopify_id": str(c['id']),
                    "email": c.get('email'),
                    "first_name": c.get('first_name'),
                    "last_name": c.get('last_name'),
                    "phone": c.get('phone') or default_address.get('phone'),
                    "city": default_address.get('city'),
                    "country": default_address.get('country'),
                    "accepts_marketing": bool(c.get('accepts_marketing', False)),
                    "tags": [t.strip() for t in (c.get('tags') or '').split(',') if t.strip()],
                    "total_orders": int(c.get('orders_count', 0) or 0),
                    "total_spent": float(c.get('total_spent', 0) or 0),
                    "shopify_created_at": c.get('created_at'),
                    "updated_at": c.get('updated_at'),
                }
                total_yielded += 1

            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify.sync",
                  f"Shopify customers stream completed — {total_yielded} customers",
                  payload={"count": total_yielded, "kind": "customers_stream"})

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed during customer stream: {str(e)}")
        raise
    
def list_all_orders() -> list[dict]:
    """
    Full orders list from Shopify, paginated. Used by /api/orders/sync.
    """
    if USE_MOCK:
        return []
    return _real_list_all_orders()


def _real_list_all_orders() -> list[dict]:
    """
    GET /admin/api/2024-01/orders.json?status=any&limit=250
    Note: without read_all_orders scope, only last 60 days are returned.
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        all_orders = []
        url = f"{store_url}/admin/api/2024-01/orders.json?status=any&limit=250"

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for o in response.json().get('orders', []):
                customer = o.get('customer') or {}
                line_items = o.get('line_items') or []
                all_orders.append({
                    "shopify_id": str(o.get('id')),
                    "shopify_customer_id": str(customer.get('id')) if customer.get('id') else None,
                    "order_number": str(o.get('order_number') or o.get('name') or ''),
                    "total": float(o.get('total_price', 0) or 0),
                    "currency": o.get('currency', 'KES'),
                    "items_count": sum(int(li.get('quantity', 0) or 0) for li in line_items),
                    "products": [li.get('title', '') for li in line_items if li.get('title')],
                    "financial_status": o.get('financial_status'),
                    "fulfillment_status": o.get('fulfillment_status'),
                    "order_date": o.get('created_at'),
                })

            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify.sync",
                  f"Shopify sync completed — {len(all_orders)} orders updated",
                  payload={"count": len(all_orders), "kind": "orders"})
        return all_orders

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to fetch orders: {str(e)}")
        raise


def iter_all_orders():
    """
    Generator version of list_all_orders. Yields one order at a time as we
    page through Shopify, so callers never need to hold the full list in memory.
    
    Same fields as list_all_orders. Use this for sync loops that process orders
    one-by-one; use list_all_orders only when you actually need the whole list.
    """
    if USE_MOCK:
        return  # No mock data; just yield nothing
    yield from _real_iter_all_orders()


def _real_iter_all_orders():
    """Streams orders page by page. Same shape as _real_list_all_orders."""
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        url = f"{store_url}/admin/api/2024-01/orders.json?status=any&limit=250"
        total_yielded = 0

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for o in response.json().get('orders', []):
                customer = o.get('customer') or {}
                line_items = o.get('line_items') or []
                yield {
                    "shopify_id": str(o.get('id')),
                    "shopify_customer_id": str(customer.get('id')) if customer.get('id') else None,
                    "order_number": str(o.get('order_number') or o.get('name') or ''),
                    "total": float(o.get('total_price', 0) or 0),
                    "currency": o.get('currency', 'KES'),
                    "items_count": sum(int(li.get('quantity', 0) or 0) for li in line_items),
                    "products": [li.get('title', '') for li in line_items if li.get('title')],
                    "financial_status": o.get('financial_status'),
                    "fulfillment_status": o.get('fulfillment_status'),
                    "order_date": o.get('created_at'),
                }
                total_yielded += 1

            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify.sync",
                  f"Shopify orders stream completed — {total_yielded} orders",
                  payload={"count": total_yielded, "kind": "orders_stream"})

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed during order stream: {str(e)}")
        raise


def _real_get_customer_orders(shopify_customer_id: str) -> list[dict]:
    """
    GET /admin/api/2024-01/customers/{id}/orders.json?status=any
    Returns all orders for one customer. Used by the customer detail page
    on-demand (not part of bulk sync).
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        url = f"{store_url}/admin/api/2024-01/customers/{shopify_customer_id}/orders.json?status=any&limit=250"
        all_orders = []

        while url:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            for o in response.json().get('orders', []):
                line_items = o.get('line_items') or []
                all_orders.append({
                    "shopify_id": str(o.get('id')),
                    "shopify_customer_id": shopify_customer_id,
                    "order_number": str(o.get('order_number') or o.get('name') or ''),
                    "total": float(o.get('total_price', 0) or 0),
                    "currency": o.get('currency', 'KES'),
                    "items_count": sum(int(li.get('quantity', 0) or 0) for li in line_items),
                    "products": [li.get('title', '') for li in line_items if li.get('title')],
                    "financial_status": o.get('financial_status'),
                    "fulfillment_status": o.get('fulfillment_status'),
                    "order_date": o.get('created_at'),
                })

            # Pagination via Link header
            link_header = response.headers.get('Link', '')
            url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        url = part.split(';')[0].strip().strip('<>')
                        break

        log_event("info", "integrations.shopify",
                  f"Fetched {len(all_orders)} orders for customer {shopify_customer_id}")
        return all_orders

    except requests.RequestException as e:
        log_event("error", "integrations.shopify",
                  f"Failed to fetch orders for customer {shopify_customer_id}: {str(e)}")
        raise