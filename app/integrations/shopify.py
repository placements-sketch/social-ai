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
        response = requests.post(token_url, data=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        _SHOPIFY_ACCESS_TOKEN = data.get('access_token')
        if not _SHOPIFY_ACCESS_TOKEN:
            raise ValueError(f"No access_token in Shopify response: {data}")
        
        expires_in = int(data.get('expires_in', 86399))
        _SHOPIFY_TOKEN_EXPIRES_AT = datetime.utcnow() + timedelta(seconds=expires_in)
        log_event("info", "integrations.shopify",
                  f"Access token obtained (expires at {_SHOPIFY_TOKEN_EXPIRES_AT.isoformat()})")
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


# ─────────────────────────────────────────────
# Real Shopify implementation (TODO)
# ─────────────────────────────────────────────

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
        response = requests.get(url, headers=headers, timeout=10)
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
        url = f"{store_url}/admin/api/2024-01/products.json?limit=250"

        while url:
            response = requests.get(url, headers=headers, timeout=30)
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

        log_event("info", "integrations.shopify", f"Fetched {len(all_products)} products from Shopify")
        return all_products

    except requests.RequestException as e:
        log_event("error", "integrations.shopify", f"Failed to fetch catalog: {str(e)}")
        raise