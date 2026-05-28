"""
app/services.py
Core message processing pipeline.

Pipeline steps:
  1. Receive message + metadata
  2. Detect ALL intents (a message can have multiple)
  3. Fetch relevant data based on detected intents
  4. Generate AI reply with full context
  5. Send reply back via the correct channel
  6. Persist message to DB
"""

from app.ai.generator import generate_reply
from app.integrations.shopify import get_product_info, get_stock_level
from app.integrations.meta import send_instagram_reply, send_whatsapp_reply, send_facebook_reply
from app.integrations.tiktok import send_tiktok_reply
from app.utils.intent import detect_intents, intents_to_label
from app.utils.logger import log_event


def process_message(message: str, user_id: str, channel: str) -> str:
    """
    Main pipeline entry point. Called by every webhook route.

    Args:
        message: Raw text from the customer.
        user_id: Channel-specific sender ID.
        channel: One of 'instagram_dm', 'instagram_comment', 'whatsapp',
                 'facebook_dm', 'facebook_comment', 'tiktok_dm', 'tiktok_comment'.

    Returns:
        The reply string that was (or will be) sent to the customer.
    """
    log_event("info", "services", f"Inbound [{channel}] from {user_id}: {message[:80]}")

    # ── Step 1: Detect ALL intents in the message ──────────────────────────
    # A single message can contain multiple intents:
    # "Hi, is this available in blue and how much is delivery to Kilimani?"
    # → ["greeting", "stock_inquiry", "product_inquiry", "delivery_inquiry", "price_inquiry"]
    intents = detect_intents(message)
    log_event("info", "services", f"Intents detected: {intents}")

    # ── Step 2: Fetch data for every relevant intent ───────────────────────
    context_data = {}

    # Fetch product + stock from Shopify (single source of truth)
    product_intents = {"product_inquiry", "price_inquiry", "stock_inquiry"}
    if product_intents.intersection(intents):
        product_keyword = _extract_product_keyword(message)
        product_data = get_product_info(product_keyword)
        context_data["product"] = product_data
        context_data["stock"]   = get_stock_level(product_keyword)
        log_event("info", "services", f"Shopify product+stock fetched for keyword: '{product_keyword}'")

    # Flag delivery questions so the AI knows to address them
    if "delivery_inquiry" in intents:
        context_data["delivery_asked"] = True
        # Extract location mention if present (simple approach — improve later)
        context_data["delivery_location"] = _extract_location(message)

    # Flag order status so the AI knows to ask for an order number
    if "order_status" in intents:
        context_data["order_status_asked"] = True

    # ── Step 3: Generate AI reply with full multi-intent context ───────────
    reply = generate_reply(
        message=message,
        intents=intents,
        context_data=context_data,
        channel=channel
    )

    # ── Step 4: Send reply back via the correct channel ────────────────────
    _dispatch_reply(channel=channel, user_id=user_id, reply=reply)

    # ── Step 5: Persist to DB ──────────────────────────────────────────────
    # Store all intents as a pipe-separated string: "stock_inquiry|price_inquiry"
    intent_label = intents_to_label(intents)
    _save_message(user_id=user_id, channel=channel, content=message,
                  intent=intent_label, direction="inbound")
    _save_message(user_id=user_id, channel=channel, content=reply,
                  intent=None, direction="outbound")

    return reply


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _extract_product_keyword(message: str) -> str:
    """
    Pulls the most likely product keyword from the message.
    Simple stopword filter — replace with NER or a product name list later.
    """
    stopwords = {
        "is", "the", "a", "an", "do", "you", "have", "what", "how", "much",
        "in", "stock", "available", "this", "that", "it", "yes", "no",
        "and", "or", "if", "for", "to", "of", "with", "hi", "hello", "hey",
    }
    words = [w.strip("?.,!") for w in message.lower().split()]
    candidates = [w for w in words if w not in stopwords and len(w) > 3]
    return candidates[0] if candidates else message[:30]


def _extract_location(message: str) -> str | None:
    """
    Extracts a Kenyan location mention from the message.
    Simple keyword scan — replace with NER later.
    """
    locations = [
        "nairobi", "mombasa", "kisumu", "nakuru", "kilimani", "westlands",
        "karen", "cbd", "thika", "eldoret", "lavington", "parklands",
        "eastleigh", "south b", "south c", "langata", "ruaka", "kiambu",
        "machakos", "nyeri", "meru", "kisii", "malindi",
    ]
    text = message.lower()
    for loc in locations:
        if loc in text:
            return loc.title()
    return None


def _dispatch_reply(channel: str, user_id: str, reply: str):
    """Routes the outbound reply to the correct channel sender."""
    if channel in ("instagram_dm", "instagram_comment"):
        send_instagram_reply(user_id, reply)
    elif channel == "whatsapp":
        send_whatsapp_reply(user_id, reply)
    elif channel in ("facebook_dm", "facebook_comment"):
        send_facebook_reply(user_id, reply)
    elif channel in ("tiktok_dm", "tiktok_comment"):
        send_tiktok_reply(user_id, reply)
    else:
        log_event("warning", "services", f"Unknown channel '{channel}' — reply not sent")


def _save_message(user_id: str, channel: str, content: str,
                  intent: str | None, direction: str):
    """
    Persists a message record to the database.
    Wrapped in try/except so a DB failure never breaks the response flow.
    """
    try:
        from app import db
        from app.models import Message, User, Conversation

        # Get or create the user record
        user = User.query.filter_by(external_id=user_id, channel=channel).first()
        if not user:
            user = User(external_id=user_id, channel=channel)
            db.session.add(user)
            db.session.flush()

        # Get or create the active conversation for this user+channel
        conversation = Conversation.query.filter_by(
            user_id=user.id, channel=channel, status="active"
        ).first()
        if not conversation:
            conversation = Conversation(user_id=user.id, channel=channel)
            db.session.add(conversation)
            db.session.flush()

        # Update conversation metadata
        if direction == "inbound":
            conversation.last_message = content[:200]
            conversation.last_message_at = __import__("datetime").datetime.utcnow()
            conversation.unread_count = (conversation.unread_count or 0) + 1

        msg = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            channel=channel,
            direction=direction,
            sender="ai" if direction == "outbound" else None,
            content=content,
            intent=intent,
        )
        db.session.add(msg)
        db.session.commit()

    except Exception as e:
        log_event("error", "services._save_message", str(e))
