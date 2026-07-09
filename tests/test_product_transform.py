from app.shopify_webhooks import _raw_product_to_snap


def _product(**over):
    base = {
        "id": 111,
        "title": "Tan Mules",
        "handle": "tan-mules",
        "body_html": "<p>Lovely</p>",
        "tags": "shoes, summer, new",
        "variants": [
            {"id": 1, "title": "S", "price": "2500", "inventory_management": "shopify", "inventory_quantity": 3},
            {"id": 2, "title": "M", "price": "2500", "inventory_management": "shopify", "inventory_quantity": 5},
        ],
        "images": [{"src": "https://cdn/img1.jpg"}, {"src": "https://cdn/img2.jpg"}],
    }
    base.update(over)
    return base


def test_stock_sums_tracked_variants():
    snap = _raw_product_to_snap(_product())
    assert snap["stock_quantity"] == 8
    assert snap["inventory_tracked"] is True


def test_untracked_product_reports_none_stock():
    p = _product(variants=[
        {"id": 1, "title": "OS", "price": "2500", "inventory_management": None, "inventory_quantity": None},
    ])
    snap = _raw_product_to_snap(p)
    assert snap["stock_quantity"] is None
    assert snap["inventory_tracked"] is False


def test_images_extracted_in_order():
    snap = _raw_product_to_snap(_product())
    assert snap["images"] == ["https://cdn/img1.jpg", "https://cdn/img2.jpg"]


def test_tags_parsed_from_csv_string():
    snap = _raw_product_to_snap(_product())
    assert snap["tags"] == ["shoes", "summer", "new"]


def test_variants_detail_carries_key_fields():
    snap = _raw_product_to_snap(_product())
    assert len(snap["variants_detail"]) == 2
    first = snap["variants_detail"][0]
    assert first["title"] == "S"
    assert first["inventory_quantity"] == 3


def test_missing_id_still_produces_snap():
    snap = _raw_product_to_snap({"title": "X", "variants": []})
    assert snap["name"] == "X"
    assert snap["stock_quantity"] is None