"""
app/utils/logger.py
Lightweight logging utility.

Writes to Python's standard logger AND persists to the DB logs table.
DB write is best-effort — a failure here must never crash the pipeline.
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
_logger = logging.getLogger("social_ai")


def log_event(level: str, source: str, message: str,
              payload: dict | None = None,
              conversation_id: int | None = None):
    """
    Log a pipeline event with optional structured context.

    Args:
        level:           'info', 'warning', or 'error'
        source:          Module identifier (e.g. 'services.inbound',
                         'integrations.shopify.sync')
        message:         Human-readable summary
        payload:         Optional dict of structured context
                         (handle, channel, intent, product, etc.)
                         Used by the Dashboard activity feed to build
                         rich, natural-language descriptions.
        conversation_id: Optional FK link to a conversation.
    """
    log_fn = getattr(_logger, level, _logger.info)
    log_fn(f"[{source}] {message}")

    try:
        from app import db
        from app.models import Log
        entry = Log(
            level=level,
            source=source,
            message=message,
            payload=payload,
            conversation_id=conversation_id,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        # Never let logging crash the caller
        pass