"""
app/integrations/shopify.py
Shopify Admin API integration — product metadata AND stock levels.
Shopify is now the single source of truth for all product and inventory data.

Current state: LIVE — USE_MOCK is False; all data comes from the Shopify Admin
API via the _real_* functions. The _mock_* helpers below are inactive, kept
only as a local-dev fallback.

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

class ShopifyCursorInvalidError(Exception):
    """Raised when Shopify rejects a saved pagination cursor as stale/invalid.
    Caller should discard the cursor and restart the sync from page 1."""
    pass

# Module-level session with built-in retry on transient Shopify failures.
# This handles 429 (rate limit), 502/503/504 (Shopify server hiccups),
# and connection errors with exponential backoff.
_shopify_session = None

def _get_shopify_session():
    """Returns a singleton requests.Session configured with retry-with-backoff.

    Retries on:
      - HTTP status codes: 429 (rate limit), 500/502/503/504 (server errors)
      - Connection errors (network blips)
      - ChunkedEncodingError / ProtocolError (mid-stream drops from Shopify)

    Retries: 5 attempts total, waits 2s/4s/8s/16s/32s between them.
    """
    global _shopify_session
    if _shopify_session is None:
        _shopify_session = requests.Session()
        retry = Retry(
            total=5,
            connect=5,         # retry connection failures
            read=5,            # retry read failures (mid-stream drops)
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET', 'POST'],
            raise_on_status=False,
            respect_retry_after_header=True,
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
    return _real_get_product_info(keyword)


def get_stock_level(keyword: str) -> dict:
    """
    Returns stock level for a product from Shopify inventory.
    Shopify is the single source of truth for all inventory data.
    """
    return _real_get_stock_level(keyword)

def list_all_products() -> list[dict]:
    """
    Returns the FULL catalog from Shopify — used by the Products page sync.
    Each dict has the same shape as get_product_info() returns.
    """
    return _real_list_all_products()

# A garment has one name to a customer and another to whoever wrote the product
# title. Filtering on the literal word a photo suggests is worse than no filter
# at all when the two disagree: asked for "trousers", a literal match threw away
# every navy wide-leg PANT in the catalogue and returned army-green trousers
# instead — the right kind of item, entirely the wrong ones, and worse than the
# unfiltered ranking it replaced. Caught by running it against the real
# catalogue rather than reasoning about it.
_TYPE_SYNONYMS = [
    {"trousers", "trouser", "pants", "pant", "slacks", "palazzo", "leggings"},
    {"dress", "dresses", "gown", "frock", "kaftan", "kaftans"},
    {"top", "tops", "blouse", "shirt", "tee", "t-shirt", "tank", "camisole"},
    {"skirt", "skirts"},
    {"jacket", "jackets", "blazer", "coat", "cardigan"},
    {"shoes", "shoe", "heels", "sandals", "mules", "flats", "sneakers", "boots"},
    {"bag", "bags", "purse", "handbag", "clutch", "tote"},
    {"set", "sets", "co-ord", "coord", "two-piece"},
    {"jumpsuit", "jumpsuits", "romper", "playsuit"},
    {"shorts", "short"},
]


def _type_synonyms(word: str) -> set:
    """Every catalogue word that means the same garment as `word`."""
    w = (word or "").strip().lower()
    if not w:
        return set()
    for group in _TYPE_SYNONYMS:
        if w in group:
            return set(group)
    # Unknown type — match it and its singular, rather than nothing.
    return {w, w[:-1]} if w.endswith('s') and len(w) > 3 else {w}


def search_products(keyword, limit: int = 3, must_match: str = None,
                    include_sold_out: bool = False) -> list[dict]:
    """
    Search the local ProductCache. Accepts either:
      - a single keyword string (matches across name/desc/variants/tags), OR
      - a list of keywords (products matching MORE terms rank higher).
    Returns up to `limit` matches, best first.

    `must_match` is a hard filter, not a ranking hint: only products whose name
    or tags contain it are eligible. Used with the garment type read off a
    customer's photo, so a search for a dress cannot return trousers no matter
    how well the other words happen to score. Ranking alone could not do this —
    with thousands of products a strong colour or fabric match on the wrong
    kind of item routinely outranked the right one.

    If the filter matches nothing, returns empty rather than silently widening;
    the caller decides whether to fall back.

    SOLD-OUT PRODUCTS ARE EXCLUDED BY DEFAULT. Recommending something the
    customer cannot buy is worse than saying we don't have it — it produces a
    link, an intent to purchase, and then a dead end. `include_sold_out=True`
    is for callers that need to KNOW an item is sold out rather than offer it:
    the stock automation rules, which exist precisely to answer "is this in
    stock?" and would never fire if the sold-out row were filtered away first.
    """
    if not keyword:
        return []
    # Normalize to a list
    terms = [keyword] if isinstance(keyword, str) else list(keyword)
    terms = [t for t in terms if t and t.strip()]
    if not terms:
        return []

    if not must_match:
        return _cache_search_products(terms, limit=limit, include_sold_out=include_sold_out)

    # Over-fetch, then filter — the ranking still decides the order within the
    # products that are the right kind of thing.
    needles = _type_synonyms(must_match)
    candidates = _cache_search_products(terms, limit=max(limit * 8, 200),
                                        include_sold_out=include_sold_out)
    kept = []
    for p in candidates:
        haystack = ' '.join([
            str(p.get('name') or ''),
            ' '.join(str(t) for t in (p.get('tags') or [])),
        ]).lower()
        if any(n in haystack for n in needles):
            kept.append(p)
        if len(kept) >= limit:
            break
    return kept


def iter_all_order_ids():
    """
    Yield every live order id (str) from Shopify, id-only (?fields=id) so
    payloads stay tiny — for the weekly reconcile. Raises on any page error
    so the caller knows the id set is INCOMPLETE and must skip deletes.
    """
    if USE_MOCK:
        return
    store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    headers = {
        'X-Shopify-Access-Token': _get_shopify_access_token(),
        'Content-Type': 'application/json',
    }
    url = f"{store_url}/admin/api/2024-01/orders.json?status=any&fields=id&limit=250"
    while url:
        response = _get_shopify_session().get(url, headers=headers, timeout=30)
        response.raise_for_status()
        for o in response.json().get('orders', []):
            yield str(o['id'])
        link = response.headers.get('Link', '')
        url = None
        if 'rel="next"' in link:
            for part in link.split(','):
                if 'rel="next"' in part:
                    url = part.split(';')[0].strip().strip('<>')
                    break

def iter_all_customer_ids():
    """Same as iter_all_order_ids, for customers. Raises on any page error."""
    if USE_MOCK:
        return
    store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    headers = {
        'X-Shopify-Access-Token': _get_shopify_access_token(),
        'Content-Type': 'application/json',
    }
    url = f"{store_url}/admin/api/2024-01/customers.json?fields=id&limit=250"
    while url:
        response = _get_shopify_session().get(url, headers=headers, timeout=30)
        response.raise_for_status()
        for c in response.json().get('customers', []):
            yield str(c['id'])
        link = response.headers.get('Link', '')
        url = None
        if 'rel="next"' in link:
            for part in link.split(','):
                if 'rel="next"' in part:
                    url = part.split(';')[0].strip().strip('<>')
                    break


# ─────────────────────────────────────────────
# Real Shopify implementation (LIVE)
# ─────────────────────────────────────────────

#: Colourways of one garment to allow in a result set before moving on to a
#: different product. Two keeps a shade option available without letting one
#: family crowd out every other candidate.
MAX_PER_FAMILY = 2


def _product_family(name: str) -> str:
    """
    The garment behind a variant title. Shopify names these
    "Base Name - Colour / Print", so everything before the first ' - ' is the
    product and the rest is the colourway.
    """
    return (name or '').split(' - ', 1)[0].strip().lower()


def _diversify_by_family(rows, limit: int):
    """
    Trim to `limit`, allowing at most MAX_PER_FAMILY colourways of the same
    garment. Ordering is preserved, so the best-scoring member of each family
    is the one kept. Falls back to filling from the leftovers if diversifying
    leaves the list short.
    """
    picked, spill, seen = [], [], {}
    for row in rows:
        product = row[0]
        fam = _product_family(product.name)
        if seen.get(fam, 0) < MAX_PER_FAMILY:
            seen[fam] = seen.get(fam, 0) + 1
            picked.append(row)
            if len(picked) >= limit:
                return picked
        else:
            spill.append(row)
    # Not enough distinct families to fill the quota — top up in score order
    # rather than returning fewer results than asked for.
    return (picked + spill)[:limit]


def _cache_search_products(terms: list[str], limit: int = 3,
                           include_sold_out: bool = False) -> list[dict]:
    """
    Multi-term ProductCache search. Each term contributes to the score based on
    where it hits (name > variants > tags > description). Products that match
    multiple terms naturally outrank single-term matches.
    """
    try:
        from app.models import ProductCache
        from app import db
        from sqlalchemy import or_, case, cast, String, func

        # Score each ORIGINAL term ONCE (plural/singular collapsed), then sum
        # across terms. Coverage (how many distinct terms a product matches)
        # dominates; field weights (name > variants > tags > description) break
        # ties within a coverage tier. This is what makes "boxer shorts" rank
        # the actual boxer products above generic shorts that match one term.
        like_clauses = []
        coverage_components = []   # +1 per distinct term matched anywhere
        field_components = []      # weighted by where each term hits

        for raw in terms:
            t = raw.lower().strip()
            t_singular = t.rstrip('s') if len(t) > 3 and t.endswith('s') else t
            kws = {t, t_singular}

            name_hit = or_(*[ProductCache.name.ilike(f"%{kw}%") for kw in kws])
            var_hit  = or_(*[cast(ProductCache.variants, String).ilike(f"%{kw}%") for kw in kws])
            tag_hit  = or_(*[cast(ProductCache.tags, String).ilike(f"%{kw}%") for kw in kws])
            desc_hit = or_(*[ProductCache.description.ilike(f"%{kw}%") for kw in kws])
            term_hit = or_(name_hit, var_hit, tag_hit, desc_hit)

            like_clauses.append(term_hit)
            coverage_components.append(case((term_hit, 1), else_=0))
            field_components.append(case((name_hit, 10), else_=0))
            field_components.append(case((var_hit,  5), else_=0))
            field_components.append(case((tag_hit,  4), else_=0))
            field_components.append(case((desc_hit, 2), else_=0))

        if not like_clauses:
            return []

        coverage = coverage_components[0]
        for c in coverage_components[1:]:
            coverage = coverage + c

        field_score = field_components[0]
        for c in field_components[1:]:
            field_score = field_score + c

        # Coverage ×100 so matching every query term always wins; field_score
        # ranks within the same coverage tier.
        score = (coverage * 100 + field_score).label('score')

        # Over-fetch, then thin out colourways. Shopify names variants
        # "Base Name - Colour / Print", and this catalogue runs to 21 colourways
        # of a single garment — so a plain top-N filled with one product family.
        # A real search for "black satin dress" returned 11 shades of the same
        # Vivo satin line, which is fatal for the vision re-ranker: it can only
        # choose from what it's shown, so it confidently picked the nearest
        # member of the wrong family. Diversifying gives it genuinely different
        # garments to compare against.
        #
        # The alphabetical final tie-break made it worse — within one score
        # tier it systematically favours whatever sorts first, so the same
        # brand won every time.
        # SOLD OUT IS NOT A SEARCH RESULT.
        #
        # This was a ranking rule, not a filter — out-of-stock items sorted last
        # but stayed eligible, so when nothing in stock matched well the AI
        # cheerfully recommended something the customer could not buy. That is
        # worse than saying we don't have it: it produces a link, an intent to
        # purchase, and then a dead end, and the customer blames us at the point
        # they were most willing to spend.
        #
        # "Out of stock" means we POSITIVELY KNOW the count is zero. Products
        # Shopify does not track inventory for are always purchasable, so
        # untracked and unknown both stay eligible — filtering on
        # `stock_quantity <= 0` alone would silently delete every untracked
        # product from the assistant's catalogue.
        in_stock = or_(
            ProductCache.inventory_tracked.is_(False),
            ProductCache.stock_quantity.is_(None),
            ProductCache.stock_quantity > 0,
        )

        q = db.session.query(ProductCache, score).filter(or_(*like_clauses))
        if not include_sold_out:
            q = q.filter(in_stock)

        # Ordering differs by purpose. The default list is what gets offered, so
        # nothing sold out is in it at all. A caller that asked for sold-out
        # rows wants to know WHETHER the best match is available — burying them
        # at the bottom would answer the opposite question, and the stock rule
        # reading products[0] would never see one.
        ordering = [] if include_sold_out else [
            (func.coalesce(ProductCache.stock_quantity, 1) == 0).asc()
        ]
        rows = (
            q
            .order_by(
                *ordering,
                score.desc(),
                # Stock level, not name — a well-stocked item is the more
                # useful representative of its family than an alphabetical one.
                func.coalesce(ProductCache.stock_quantity, 1).desc(),
                ProductCache.name.asc(),
            )
            .limit(max(limit * 6, limit))
            .all()
        )

        rows = _diversify_by_family(rows, limit)

        result = []
        for product, _score in rows:
            result.append({
                "shopify_id": product.shopify_product_id,
                "name": product.name,
                "handle": product.handle,
                "description": (product.description or '')[:200],
                "price": str(product.price) if product.price is not None else 'N/A',
                "variants": product.variants or [],
                "variants_detail": product.variants_detail or [],
                "stock_quantity": product.stock_quantity or 0,
                # Needed by the vision re-ranker — without images it can't
                # compare candidates against the customer's photo.
                "images": product.images or [],
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

                variants_detail = [
                    {
                        "shopify_variant_id": str(v.get('id')),
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

                all_products.append({
                    "shopify_id": str(product['id']),
                    "name": product.get('title', 'Unknown'),
                    "handle": product.get('handle') or '',
                    "description": (product.get('body_html') or '')[:200],
                    "price": f"KES {variants[0].get('price', 'N/A')}" if variants else "N/A",
                    "variants": [v.get('title', '') for v in variants],
                    "variants_detail": variants_detail,
                    "images": [img.get('src') for img in (product.get('images') or []) if img.get('src')],
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

def iter_all_products(start_url=None):
    """
    Generator version of list_all_products. Yields one product at a time.
    
    Args:
        start_url: Optional resume URL from a previous interrupted sync.
                   If None, starts from the first page.
    """
    if USE_MOCK:
        return
    yield from _real_iter_all_products(start_url=start_url)


def _real_iter_all_products(start_url=None):
    """Streams products page by page. Same dict shape as _real_list_all_products.
    
    Yields tuples of (product_dict, next_page_url) so callers can persist the
    cursor for resumption. next_page_url is None on the last page.
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()

        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        url = start_url or f"{store_url}/admin/api/2024-01/products.json?limit=250&status=active&published_status=published"
        total_yielded = 0

        while url:
            response = _get_shopify_session().get(url, headers=headers, timeout=30)
            
            # If Shopify says the cursor is stale/invalid, raise a specific error
            # so the caller can discard the cursor and restart.
            if response.status_code in (400, 404, 410):
                body_preview = (response.text or '')[:200]
                raise ShopifyCursorInvalidError(
                    f"Shopify rejected pagination cursor (status {response.status_code}): {body_preview}"
                )
            response.raise_for_status()

            # Compute the next URL BEFORE yielding, so we can pass it to the caller
            link_header = response.headers.get('Link', '')
            next_url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        next_url = part.split(';')[0].strip().strip('<>')
                        break

            for product in response.json().get('products', []):
                variants = product.get('variants') or []
                inventory_tracked = any(v.get('inventory_management') == 'shopify' for v in variants)
                stock_quantity = sum(
                    (v.get('inventory_quantity') or 0) for v in variants
                    if v.get('inventory_management') == 'shopify'
                ) if inventory_tracked else None

                # Structured per-variant details for AI to use
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

                yield ({
                    "shopify_id": str(product['id']),
                    "name": product.get('title', 'Unknown'),
                    "handle": product.get('handle') or '',
                    "description": (product.get('body_html') or '')[:200],
                    "price": f"KES {variants[0].get('price', 'N/A')}" if variants else "N/A",
                    "variants": [v.get('title', '') for v in variants],
                    "variants_detail": variants_detail,
                    "images": [img.get('src') for img in (product.get('images') or []) if img.get('src')],
                    "stock_quantity": stock_quantity,
                    "inventory_tracked": inventory_tracked,
                }, next_url)
                total_yielded += 1

            url = next_url

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

def iter_all_customers(start_url=None, updated_at_min=None):
    """
    Generator version of list_all_customers. Yields (customer_dict, next_url) tuples.
    """
    if USE_MOCK:
        return
    yield from _real_iter_all_customers(start_url=start_url, updated_at_min=updated_at_min)


def _real_iter_all_customers(start_url=None, updated_at_min=None):
    """Streams customers page by page. Same shape as _real_list_all_customers.
    
    Yields (customer_dict, next_url) — next_url is None on the last page.
    """
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        from urllib.parse import quote
        if start_url:
            url = start_url
        else:
            url = f"{store_url}/admin/api/2024-01/customers.json?limit=250"
            if updated_at_min:
                url += f"&updated_at_min={quote(updated_at_min)}"
        total_yielded = 0

        while url:
            response = _get_shopify_session().get(url, headers=headers, timeout=30)
            
            if response.status_code in (400, 404, 410):
                body_preview = (response.text or '')[:200]
                raise ShopifyCursorInvalidError(
                    f"Shopify rejected pagination cursor (status {response.status_code}): {body_preview}"
                )
            response.raise_for_status()

            link_header = response.headers.get('Link', '')
            next_url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        next_url = part.split(';')[0].strip().strip('<>')
                        break

            for c in response.json().get('customers', []):
                default_address = c.get('default_address') or {}
                yield ({
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
                }, next_url)
                total_yielded += 1

            url = next_url

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


def iter_all_orders(start_url=None, updated_at_min=None):
    """
    Generator version of list_all_orders. Yields (order_dict, next_url) tuples.

    Args:
        start_url: Optional resume URL from a previous interrupted sync.
        updated_at_min: Optional ISO-8601 string. When set (and start_url is
                        None), only orders changed at/after this time are
                        fetched — this is the delta sync.
    """
    if USE_MOCK:
        return
    yield from _real_iter_all_orders(start_url=start_url, updated_at_min=updated_at_min)


def _real_iter_all_orders(start_url=None, updated_at_min=None):
    """Streams orders page by page.

    Yields (order_dict, next_url) — next_url is None on the last page.
    """
    try:
        from urllib.parse import quote

        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        # Build the first-page URL. updated_at_min is ONLY applied here, never
        # on subsequent pages or resumes — see note below.
        if start_url:
            url = start_url
        else:
            url = f"{store_url}/admin/api/2024-01/orders.json?status=any&limit=250"
            if updated_at_min:
                url += f"&updated_at_min={quote(updated_at_min)}"

        total_yielded = 0

        while url:
            response = _get_shopify_session().get(url, headers=headers, timeout=30)
            
            # Detect invalid/stale pagination cursor
            if response.status_code in (400, 404, 410):
                body_preview = (response.text or '')[:200]
                raise ShopifyCursorInvalidError(
                    f"Shopify rejected pagination cursor (status {response.status_code}): {body_preview}"
                )
            response.raise_for_status()

            # Compute next_url BEFORE yielding, so callers can persist it per row
            link_header = response.headers.get('Link', '')
            next_url = None
            if 'rel="next"' in link_header:
                for part in link_header.split(','):
                    if 'rel="next"' in part:
                        next_url = part.split(';')[0].strip().strip('<>')
                        break

            for o in response.json().get('orders', []):
                customer = o.get('customer') or {}
                line_items = o.get('line_items') or []
                yield ({
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
                }, next_url)
                total_yielded += 1

            url = next_url

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


def refresh_stock_for_products(shopify_product_ids: list[str]) -> dict:
    """
    Live-fetch fresh stock quantities for a small set of products from Shopify.
    Called when the customer is asking about stock and cache staleness matters.
    
    Args:
        shopify_product_ids: List of Shopify product IDs (as strings).
    
    Returns:
        Dict of {shopify_product_id: {"stock_quantity": int|None, "variants_detail": [...]}}.
        Products that fail to fetch are simply omitted — caller falls back to cache.
    """
    if not shopify_product_ids or USE_MOCK:
        return {}

    result = {}
    try:
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        access_token = _get_shopify_access_token()
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json',
        }

        # Shopify supports bulk lookup: /products.json?ids=1,2,3
        ids_param = ','.join(str(pid) for pid in shopify_product_ids[:20])  # cap at 20 for URL length
        url = f"{store_url}/admin/api/2024-01/products.json?ids={ids_param}"

        response = _get_shopify_session().get(url, headers=headers, timeout=10)
        response.raise_for_status()

        for product in response.json().get('products', []):
            spid = str(product.get('id'))
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

            result[spid] = {
                "stock_quantity": stock_quantity,
                "inventory_tracked": inventory_tracked,
                "variants_detail": variants_detail,
            }

        log_event("info", "integrations.shopify.live_stock",
                  f"Refreshed live stock for {len(result)} products",
                  payload={"requested": len(shopify_product_ids), "returned": len(result)})
        return result

    except Exception as e:
        log_event("warn", "integrations.shopify.live_stock_failed",
                  f"Live stock refresh failed, falling back to cache: {str(e)[:200]}")
        return {}
    

def live_search_products(terms, window_days=1, limit=250, max_pages=2):
    """
    Live fallback for a cache MISS: fetch products updated in the last
    `window_days` (active/published only) and keyword-filter them locally.

    Covers the one gap the 3-hourly full products sync can leave: a product
    created OR newly-published/edited since the last run. Returns snap dicts
    in the same shape the sync produces, so the caller can upsert them into
    the cache and re-run the normal cache search. Returns [] on no match/error.
    """
    if not terms or USE_MOCK:
        return []
    try:
        from datetime import datetime, timedelta, timezone
        from urllib.parse import quote

        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        headers = {
            'X-Shopify-Access-Token': _get_shopify_access_token(),
            'Content-Type': 'application/json',
        }

        updated_min = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        # Filters go on the FIRST page only; the Link header carries them forward.
        url = (f"{store_url}/admin/api/2024-01/products.json"
               f"?limit=250&status=active&published_status=published"
               f"&updated_at_min={quote(updated_min)}")

        # Lowercase needles + singular fallback, mirroring the cache search.
        needles = set()
        for t in terms:
            t = (t or '').strip().lower()
            if len(t) < 3:
                continue
            needles.add(t)
            if len(t) > 3 and t.endswith('s'):
                needles.add(t[:-1])
        if not needles:
            return []

        matches = []
        pages = 0
        while url and pages < max_pages:  # safety cap
            response = _get_shopify_session().get(url, headers=headers, timeout=15)
            response.raise_for_status()

            for product in response.json().get('products', []):
                variants = product.get('variants') or []
                tags = [s.strip() for s in (product.get('tags') or '').split(',') if s.strip()]

                haystack = ' '.join([
                    product.get('title', ''),
                    product.get('body_html', '') or '',
                    ' '.join(v.get('title', '') for v in variants),
                    ' '.join(tags),
                ]).lower()
                if not any(n in haystack for n in needles):
                    continue

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

                matches.append({
                    "shopify_id": str(product['id']),
                    "name": product.get('title', 'Unknown'),
                    "handle": product.get('handle') or '',
                    "description": (product.get('body_html') or '')[:200],
                    "price": f"KES {variants[0].get('price', 'N/A')}" if variants else "N/A",
                    "variants": [v.get('title', '') for v in variants],
                    "variants_detail": variants_detail,
                    "stock_quantity": stock_quantity,
                    "inventory_tracked": inventory_tracked,
                    "tags": tags,
                })
                if len(matches) >= limit:
                    break

            next_url = None
            link = response.headers.get('Link', '')
            if 'rel="next"' in link:
                for part in link.split(','):
                    if 'rel="next"' in part:
                        next_url = part.split(';')[0].strip().strip('<>')
                        break
            url = next_url
            pages += 1
            if len(matches) >= limit:
                break

        log_event("info", "integrations.shopify.live_fallback",
                  f"Live product fallback for {terms}: {len(matches)} match(es)",
                  payload={"terms": terms, "matches": [m["name"] for m in matches[:10]]})
        return matches

    except Exception as e:
        log_event("warn", "integrations.shopify.live_fallback_failed",
                  f"Live product fallback failed for {terms}: {str(e)[:200]}")
        return []
    
def find_customer_by_email(email: str) -> dict | None:
    """
    Live lookup: find a Shopify customer by exact email, for real-time
    order-status verification. Never cached.
    GET /admin/api/2024-01/customers/search.json?query=email:{email}
    Returns {shopify_id, email, first_name, last_name} on an exact email
    match, else None. Requires read_customers scope (already granted).
    """
    if not email or USE_MOCK:
        return None
    try:
        from urllib.parse import quote
        target = email.strip().lower()
        store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
        headers = {
            'X-Shopify-Access-Token': _get_shopify_access_token(),
            'Content-Type': 'application/json',
        }
        url = (f"{store_url}/admin/api/2024-01/customers/search.json"
               f"?query={quote('email:' + target)}&limit=5")
        response = _get_shopify_session().get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # search can be fuzzy — require an EXACT email match before returning
        for c in response.json().get('customers', []):
            if (c.get('email') or '').strip().lower() == target:
                return {
                    "shopify_id": str(c.get('id')),
                    "email": c.get('email'),
                    "first_name": c.get('first_name') or '',
                    "last_name": c.get('last_name') or '',
                }
        return None
    except Exception as e:
        log_event("warn", "integrations.shopify.customer_search_failed",
                  f"Customer email lookup failed: {str(e)[:200]}")
        return None

def iter_orders_for_attribution(updated_at_min=None):
    """
    Yield lightweight order dicts for conversion attribution — crucially
    includes `landing_site`, the URL that carries our UTM token (the main
    orders sync doesn't store it). Field-limited to keep payloads small.
    Yields {id, order_number, total, tax, currency, order_date, landing_site}.

    `tax` is Shopify's own total_tax for the order. We record it so attributed
    revenue can be reported net of tax EXACTLY, per order, instead of dividing
    every total by a flat 1.16 and hoping every order was taxed at the Kenyan
    rate. total_price already includes tax, so net = total - tax regardless of
    how line prices are quoted.

    Raises on any page error (caller should treat a failed run as incomplete).
    """
    if USE_MOCK:
        return
    from urllib.parse import quote
    store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    headers = {
        'X-Shopify-Access-Token': _get_shopify_access_token(),
        'Content-Type': 'application/json',
    }
    fields = "id,name,total_price,total_tax,currency,created_at,landing_site"
    url = f"{store_url}/admin/api/2024-01/orders.json?status=any&fields={fields}&limit=250"
    if updated_at_min:
        url += f"&updated_at_min={quote(updated_at_min)}"
    while url:
        response = _get_shopify_session().get(url, headers=headers, timeout=30)
        response.raise_for_status()
        for o in response.json().get('orders', []):
            yield {
                "id": str(o.get('id')),
                "order_number": o.get('name'),
                "total": o.get('total_price'),
                "tax": o.get('total_tax'),
                "currency": o.get('currency'),
                "order_date": o.get('created_at'),
                "landing_site": o.get('landing_site'),
            }
        link = response.headers.get('Link', '')
        url = None
        if 'rel="next"' in link:
            for part in link.split(','):
                if 'rel="next"' in part:
                    url = part.split(';')[0].strip().strip('<>')
                    break


SHOPIFY_WEBHOOK_TOPICS = [
    "products/create", "products/update", "products/delete",
    "orders/create", "orders/updated",
    "customers/create", "customers/update",
    "inventory_levels/update",
]


def list_shopify_webhooks() -> list[dict]:
    """GET the store's current webhook subscriptions."""
    store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    access_token = _get_shopify_access_token()
    headers = {'X-Shopify-Access-Token': access_token, 'Content-Type': 'application/json'}
    r = _get_shopify_session().get(f"{store_url}/admin/api/2024-01/webhooks.json?limit=250",
                                   headers=headers, timeout=15)
    r.raise_for_status()
    return r.json().get('webhooks', [])


def register_shopify_webhooks(base_url: str) -> dict:
    """
    Idempotently register every topic pointing at {base_url}/webhook/shopify.
    Skips topics already registered for that address. Returns a summary.
    """
    address = f"{base_url.rstrip('/')}/webhook/shopify"
    store_url = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    access_token = _get_shopify_access_token()
    headers = {'X-Shopify-Access-Token': access_token, 'Content-Type': 'application/json'}

    existing_set = {(w.get('topic'), w.get('address')) for w in list_shopify_webhooks()}

    created, skipped, errors = [], [], []
    for topic in SHOPIFY_WEBHOOK_TOPICS:
        if (topic, address) in existing_set:
            skipped.append(topic)
            continue
        try:
            r = _get_shopify_session().post(
                f"{store_url}/admin/api/2024-01/webhooks.json",
                headers=headers,
                json={"webhook": {"topic": topic, "address": address, "format": "json"}},
                timeout=15,
            )
            if r.status_code in (200, 201):
                created.append(topic)
            else:
                errors.append({"topic": topic, "status": r.status_code, "detail": (r.text or '')[:200]})
        except Exception as e:
            errors.append({"topic": topic, "error": str(e)[:200]})

    log_event("info", "integrations.shopify.webhooks_register",
              f"Registered {len(created)}, {len(skipped)} already present",
              payload={"created": created, "skipped": skipped, "errors": errors, "address": address})
    return {"address": address, "created": created, "already_registered": skipped, "errors": errors}