from dotenv import load_dotenv
load_dotenv(r"c:\Users\WorkPC\Documents\dev\social-ai-assistant\.env")
import os
os.environ['DATABASE_URL'] = os.environ['External_Database_URL']
from app import create_app, db
app = create_app()
with app.app_context():
    cid = db.session.execute(db.text(
        "select shopify_customer_id from customers_cache where email='pollymkathuri@yahoo.com'")).scalar()
    NON = ("t.title NOT ILIKE '%gift card%' AND t.title NOT ILIKE '%credit note%'"
           " AND t.title NOT ILIKE '%gift bag%' AND t.title NOT ILIKE '%gift voucher%'")
    rows = db.session.execute(db.text(f"""
        WITH items AS (
          SELECT jsonb_array_elements_text(products::jsonb) AS title
          FROM orders_cache WHERE shopify_customer_id = :cid
        ),
        vendors AS (SELECT DISTINCT vendor FROM products_cache WHERE vendor IS NOT NULL AND vendor <> ''),
        matched AS (
          SELECT t.title,
                 (SELECT v.vendor FROM vendors v
                   WHERE t.title ILIKE v.vendor || '%'
                   ORDER BY length(v.vendor) DESC LIMIT 1) AS brand
          FROM items t WHERE t.title <> '' AND {NON}
        )
        SELECT COALESCE(brand,'Other') AS brand, COUNT(*) AS items
        FROM matched GROUP BY 1 ORDER BY items DESC LIMIT 8"""), {'cid': cid}).fetchall()
    for r in rows: print(f"   {r[1]:>5}  {r[0]}")
