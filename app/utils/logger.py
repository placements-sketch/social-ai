"""
app/utils/logger.py
Lightweight logging utility.

Writes to Python's standard logger AND persists to the DB logs table.
DB write is best-effort — a failure here must never crash the pipeline.
"""

import logging

# Standard Python logger (outputs to console / file handler)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
_logger = logging.getLogger("social_ai")


def log_event(level: str, source: str, message: str):
    """
    Log a pipeline event.

    Args:
        level:   'info', 'warning', or 'error'
        source:  Module or function name (e.g. 'services', 'integrations.shopify')
        message: Human-readable description of the event
    """
    # 1. Write to standard logger
    log_fn = getattr(_logger, level, _logger.info)
    log_fn(f"[{source}] {message}")

    # 2. Persist to DB (best-effort)
    try:
        from app import db
        from app.models import Log
        entry = Log(level=level, source=source, message=message)
        db.session.add(entry)
        db.session.commit()
    except Exception:
        # Never let a logging failure propagate
        pass
