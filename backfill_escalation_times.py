"""
backfill_escalation_times.py — one-time script.

Adds conversations.escalated_at / ai_disabled_at (idempotent DDL) and fills
them for rows that predate the columns.

Why: analytics used to count "Escalated" as conversations whose
last_message_at fell in the window AND which had a handoff_reason. That
counts conversations *touched* in the window that had *ever* escalated, so a
single June escalation recounted in July, August and every window the thread
stayed alive in. Counting the event needs the event's timestamp.

Source of truth, best first:
  1. the handoff.triggered log row for that conversation — a real timestamp
  2. conversations.updated_at — approximate. The handoff was the last thing
     to touch many of these rows, but not provably so; any later edit moved
     it. Rows filled this way are reported separately so the approximation
     is visible rather than silent.

Run once locally and once against production, then delete this file.
"""

from sqlalchemy import text

from app import create_app, db
from app.models import Conversation, Log

DDL = [
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMP",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ai_disabled_at TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS ix_conversations_escalated_at "
    "ON conversations (escalated_at)",
    "CREATE INDEX IF NOT EXISTS ix_conversations_ai_disabled_at "
    "ON conversations (ai_disabled_at)",
]

app = create_app()
with app.app_context():
    for stmt in DDL:
        db.session.execute(text(stmt))
    db.session.commit()
    print("Columns and indexes are in place.")

    # ── escalated_at: conversations the AI handed off ────────────────────
    escalated = Conversation.query.filter(
        Conversation.handoff_reason.isnot(None),
        Conversation.escalated_at.is_(None),
    ).all()
    print(f"\nEscalated conversations needing a timestamp: {len(escalated)}")

    # One query for every handoff log, earliest first, so .get() below picks
    # the FIRST handoff per conversation rather than issuing N queries.
    log_times = {}
    for row in (Log.query
                .filter(Log.source == 'handoff.triggered')
                .filter(Log.conversation_id.isnot(None))
                .order_by(Log.created_at.desc())):
        log_times[row.conversation_id] = row.created_at   # last write wins = earliest

    from_log, from_updated = 0, 0
    for conv in escalated:
        ts = log_times.get(conv.id)
        if ts is not None:
            from_log += 1
        else:
            ts = conv.updated_at or conv.last_message_at or conv.created_at
            from_updated += 1
        conv.escalated_at = ts
        # An escalation always switches the AI off, so this is the same moment.
        if conv.ai_disabled_at is None:
            conv.ai_disabled_at = ts

    # ── ai_disabled_at: AI switched off WITHOUT an escalation ────────────
    # A human took the thread over by hand. There's no log for it, so
    # updated_at is the only signal available.
    overridden = Conversation.query.filter(
        Conversation.ai_enabled.is_(False),
        Conversation.handoff_reason.is_(None),
        Conversation.ai_disabled_at.is_(None),
    ).all()
    for conv in overridden:
        conv.ai_disabled_at = conv.updated_at or conv.last_message_at or conv.created_at

    db.session.commit()

    print(f"  escalated_at from handoff.triggered logs : {from_log}")
    print(f"  escalated_at approximated from updated_at: {from_updated}")
    print(f"  ai_disabled_at set for manual overrides  : {len(overridden)}")
    if from_updated:
        print(f"\n  NOTE: {from_updated} escalation time(s) are approximate — no log row "
              f"exists for them.\n        Windows before today may be off by a day or two.")
    print("\nDone.")
