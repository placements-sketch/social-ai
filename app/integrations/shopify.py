"""
app/integrations/shopify.py
Shopify Admin API integration — product metadata AND stock levels.
Shopify is now the single source of truth for all product and inventory data.

Current state: MOCK — returns hardcoded data.
To activate: implement the _real_* functions and flip USE_MOCK = False.
"""

import os
from app.utils.logger import log_event

USE_MOCK = True  # Flip to False once Shopify credentials are configured


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
    Shopify is the source of truth — Odoo is no longer used.
    """
    if USE_MOCK:
        product = _mock_get_product_info(keyword)
        return {
            "product_name": product.get("name", keyword),
            "quantity": product.get("stock_quantity", 0),
            "unit": "pcs",
        }
    return _real_get_stock_level(keyword)


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
    TODO: Implement Shopify Admin REST API call.

    Endpoint: GET /admin/api/2024-01/products.json?title=<keyword>
    Docs: https://shopify.dev/docs/api/admin-rest/2024-01/resources/product

    Steps:
      1. pip install requests
      2. Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN in .env
      3. Make authenticated GET request
      4. Parse and return product dict including inventory_quantity
    """
    raise NotImplementedError("Real Shopify integration not yet implemented.")


def _real_get_stock_level(keyword: str) -> dict:
    """
    TODO: Fetch inventory levels from Shopify.

    Endpoint: GET /admin/api/2024-01/inventory_levels.json
    Or use the product variants endpoint which includes inventory_quantity.
    """
    raise NotImplementedError("Real Shopify stock fetch not yet implemented.")

