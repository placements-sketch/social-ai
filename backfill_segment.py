"""
backfill_segment.py — one-time script to populate the segment column on
all existing CustomerCache rows. Run once locally + once against Render
after the migration. Then delete this file.
"""

from app import create_app, db
from app.models import CustomerCache
from app.customers import compute_segment, _vip_threshold

app = create_app()
with app.app_context():
    vip_threshold = _vip_threshold()
    print(f"VIP threshold: {vip_threshold}")

    total = CustomerCache.query.count()
    print(f"Total customers to process: {total:,}")

    CHUNK = 1000
    offset = 0
    updated = 0
    while True:
        batch = (CustomerCache.query
                 .order_by(CustomerCache.id.asc())
                 .offset(offset)
                 .limit(CHUNK)
                 .all())
        if not batch:
            break
        for c in batch:
            c.segment = compute_segment(c, vip_threshold)
            updated += 1
        db.session.commit()
        db.session.expunge_all()
        offset += CHUNK
        print(f"Processed {min(offset, total):,} / {total:,}")

    print(f"Done. {updated:,} customer segments computed.")