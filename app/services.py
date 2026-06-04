"""
app/services.py
Core message processing pipeline.

Pipeline steps:
  1. Receive message + metadata
  2. Persist the inbound message immediately (so a human handler sees it
     even if AI is gated off — the inbox never waits on the AI pipeline)
  3. Gate check: skip AI if the channel is disabled OR the conversation
     has had AI turned off (e.g. by a human takeover)
  4. Detect ALL intents (a message can have multiple)
  5. Fetch relevant data based on detected intents
  6. Generate AI reply with full context
  7. Send reply back via the correct channel
  8. Persist the outbound message
"""

from datetime import datetime, timezone

from app.ai.generator import generate_reply
from app.integrations.shopify import get_product_info, get_stock_level
from app.integrations.meta import send_instagram_reply, send_whatsapp_reply, send_facebook_reply
from app.integrations.tiktok import send_tiktok_reply
from app.utils.intent import detect_intents, intents_to_label
from app.utils.logger import log_event
from app.handoff import check_handoff


# Sentinel returned when the AI is gated off — useful for tests and
# anyone calling process_message synchronously.
AI_SUPPRESSED = ""


def process_message(message: str, user_id: str, channel: str) -> str:
    """
    Main pipeline entry point. Called by every webhook route.

    Args:
        message: Raw text from the customer.
        user_id: Channel-specific sender ID.
        channel: One of 'instagram_dm', 'instagram_comment', 'whatsapp',
                 'facebook_dm', 'facebook_comment', 'tiktok_dm', 'tiktok_comment'.

    Returns:
        The reply string that was sent, or AI_SUPPRESSED ("") if the AI
        was gated off for this conversation/channel.
    """
    log_event("info", "services", f"Inbound [{channel}] from {user_id}: {message[:80]}")

    # ── Step 1: Persist inbound IMMEDIATELY ────────────────────────────────
    # Done first so the human inbox shows the new message even when AI is
    # off. Intent labelling can't happen until after detect_intents below;
    # we'll patch the intent field in a moment.
    inbound_record = _save_message(
        user_id=user_id, channel=channel, content=message,
        intent=None, direction="inbound",
    )

    # ── Step 2: Gate — should the AI respond? ──────────────────────────────
    # Two switches both default to "AI responds" if missing:
    #   - Channel.enabled       (channel-wide kill switch, set on the
    #                            Channels admin page)
    #   - Conversation.ai_enabled (per-thread, flipped when a human takes
    #                              over a specific conversation)
    if not _ai_should_respond(channel=channel, user_id=user_id):
        log_event("info", "services",
                  f"AI suppressed for [{channel}] {user_id} "
                  f"(channel disabled or conversation handed over)")
        return AI_SUPPRESSED

    # ── Step 3: Detect ALL intents in the message ──────────────────────────
    # A single message can contain multiple intents:
    # "Hi, is this available in blue and how much is delivery to Kilimani?"
    # → ["greeting", "stock_inquiry", "product_inquiry", "delivery_inquiry", "price_inquiry"]
    intents = detect_intents(message)
    log_event("info", "services", f"Intents detected: {intents}")

    # Update the inbound record's intent now that we know it.
    _patch_inbound_intent(inbound_record, intents)

    # ── Step 3.5: Handoff check — should this conversation go to a human? ──
    handoff = _check_handoff_for_inbound(message, intents, inbound_record)
    if handoff:
        bridging = handoff["bridging_reply"]
        _dispatch_reply(channel=channel, user_id=user_id, reply=bridging)
        _save_message(user_id=user_id, channel=channel, content=bridging,
                      intent=None, direction="outbound")
        return bridging

    # ── Step 3.6: Template-reply rule check ────────────────────────────────
    # Some automation rules short-circuit the AI with a canned reply
    # (e.g. "Out of stock"). First matching rule wins.
    template = _check_template_rule(message, intents, channel)
    if template:
        _dispatch_reply(channel=channel, user_id=user_id, reply=template)
        _save_message(user_id=user_id, channel=channel, content=template,
                      intent=None, direction="outbound")
        log_event("info", "services", f"Template-rule reply used for [{channel}] {user_id}")
        return template

    # ── Step 4: Fetch data for every relevant intent ───────────────────────
    context_data = {}

    product_intents = {"product_inquiry", "price_inquiry", "stock_inquiry"}
    if product_intents.intersection(intents):
        product_keyword = _extract_product_keyword(message)
        product_data = get_product_info(product_keyword)
        context_data["product"] = product_data
        context_data["stock"]   = get_stock_level(product_keyword)
        log_event("info", "services", f"Shopify product+stock fetched for keyword: '{product_keyword}'")

    if "delivery_inquiry" in intents:
        context_data["delivery_asked"] = True
        context_data["delivery_location"] = _extract_location(message)

    if "order_status" in intents:
        context_data["order_status_asked"] = True

    # ── Step 5: Generate AI reply with full multi-intent context ───────────
    reply = generate_reply(
        message=message,
        intents=intents,
        context_data=context_data,
        channel=channel,
    )

    # ── Step 6: Send reply back via the correct channel ────────────────────
    _dispatch_reply(channel=channel, user_id=user_id, reply=reply)

    # ── Step 7: Persist outbound ──────────────────────────────────────────
    _save_message(
        user_id=user_id, channel=channel, content=reply,
        intent=None, direction="outbound",
    )

    return reply


# ─────────────────────────────────────────────
# Gate helpers
# ─────────────────────────────────────────────

def _ai_should_respond(channel: str, user_id: str) -> bool:
    """
    Returns True iff:
      - the channel is enabled (or no Channel row exists — fail open), AND
      - the conversation has ai_enabled (or no conversation exists yet — fail open).

    Both checks fail open so a brand new customer on a brand new channel
    still gets an AI reply (the common case). Disabling is opt-in.
    """
    try:
        from app.models import Channel, Conversation, User

        ch = Channel.query.filter_by(channel=channel).first()
        if ch is not None and not ch.enabled:
            return False

        # We only know the conversation if the customer already exists.
        customer = User.query.filter_by(external_id=user_id, channel=channel).first()
        if customer is None:
            return True  # brand new customer, AI engages

        # Find the most recent active conversation for this customer.
        # (Mirrors _save_message's lookup so we're consistent.)
        # Find the customer's most recent conversation on this channel,
        # regardless of status (mirrors _save_message's lookup).
        conv = (
            Conversation.query
            .filter_by(user_id=customer.id, channel=channel)
            .order_by(Conversation.id.desc())
            .first()
        )
        if conv is None:
            return True  # no active conversation — engage

        return bool(conv.ai_enabled)
    except Exception as e:
        # Never let a DB hiccup silence the AI — fail open and log.
        log_event("error", "services._ai_should_respond", str(e))
        return True


# ─────────────────────────────────────────────
# Internal helpers (extraction)
# ─────────────────────────────────────────────

def _extract_product_keyword(message: str) -> str:
    """Pulls the most likely product keyword from the message."""
    stopwords = {
        "is", "the", "a", "an", "do", "you", "have", "what", "how", "much",
        "in", "stock", "available", "this", "that", "it", "yes", "no",
        "and", "or", "if", "for", "to", "of", "with", "hi", "hello", "hey",
    }
    words = [w.strip("?.,!") for w in message.lower().split()]
    candidates = [w for w in words if w not in stopwords and len(w) > 3]
    return candidates[0] if candidates else message[:30]


def _extract_location(message: str) -> str | None:
    """Extracts a Kenyan location mention from the message."""
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


# ─────────────────────────────────────────────
# Internal helpers (persistence)
# ─────────────────────────────────────────────

def _save_message(user_id: str, channel: str, content: str,
                  intent: str | None, direction: str):
    """
    Persist a message and return the Message row (or None on failure).
    Creates the User and Conversation if they don't exist yet.
    """
    try:
        from app import db
        from app.models import Message, User, Conversation

        user = User.query.filter_by(external_id=user_id, channel=channel).first()
        if not user:
            user = User(external_id=user_id, channel=channel)
            db.session.add(user)
            db.session.flush()

        # Find the customer's most recent conversation on this channel,
        # regardless of status. A new conversation is only created for a
        # genuinely new customer — changing status (e.g. active →
        # human_override) must NOT fork the thread.
        conversation = (
            Conversation.query
            .filter_by(user_id=user.id, channel=channel)
            .order_by(Conversation.id.desc())
            .first()
        )
        if not conversation:
            conversation = Conversation(user_id=user.id, channel=channel)
            db.session.add(conversation)
            db.session.flush()

        if direction == "inbound":
            conversation.last_message = content[:200]
            conversation.last_message_at = datetime.utcnow()
            conversation.unread_count = (conversation.unread_count or 0) + 1
        elif direction == "outbound":
            conversation.last_message = content[:200]
            conversation.last_message_at = datetime.utcnow()

        msg = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            channel=channel,
            direction=direction,
            sender=("ai" if direction == "outbound" else None),
            content=content,
            intent=intent,
        )
        db.session.add(msg)
        db.session.commit()
        return msg

    except Exception as e:
        log_event("error", "services._save_message", str(e))
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return None


def _patch_inbound_intent(inbound_record, intents):
    """Once intents are detected, write the label onto the inbound row."""
    if inbound_record is None or not intents:
        return
    try:
        from app import db
        inbound_record.intent = intents_to_label(intents)
        db.session.commit()
    except Exception as e:
        log_event("error", "services._patch_inbound_intent", str(e))


def _check_handoff_for_inbound(message, intents, inbound_record):
    """
    Resolve the conversation from the freshly-persisted inbound message
    and run the handoff check against it. Returns the handoff dict, or None.
    """
    if inbound_record is None:
        return None
    try:
        from app.models import Conversation
        conv = Conversation.query.get(inbound_record.conversation_id)
        if conv is None:
            return None
        return check_handoff(message, intents, conv)
    except Exception as e:
        log_event("error", "services._check_handoff_for_inbound", str(e))
        return None 
    
def _check_template_rule(message, intents, channel):
    """
    Look for an enabled AutomationRule whose action_config.type is
    'reply_template' and whose trigger matches this message.

    Returns the template string to send, or None if no rule applies.

    Match logic mirrors handoff.py: keyword rules match if any keyword is
    in the message; intent rules match if the intent is in `intents`;
    channel rules match if the channel is in the rule's `channels` list.
    Rules are evaluated in sort_order (lowest first) — first match wins.
    """
    try:
        from app.models import AutomationRule

        text = (message or "").lower()
        rules = (AutomationRule.query
                 .filter_by(enabled=True)
                 .order_by(AutomationRule.sort_order.asc(), AutomationRule.id.asc())
                 .all())

        for rule in rules:
            ac = rule.action_config or {}
            if ac.get("type") != "reply_template":
                continue
            template = ac.get("template")
            if not template:
                continue

            tc = rule.trigger_config or {}
            ttype = tc.get("type")

            # Optional channel scope on any rule
            allowed_channels = tc.get("channels")
            if allowed_channels and channel not in allowed_channels:
                continue

            matched = False
            if ttype == "keyword":
                keywords = [k.lower() for k in (tc.get("keywords") or [])]
                matched = any(k in text for k in keywords)
            elif ttype == "intent":
                target = tc.get("intent")
                matched = target in (intents or [])
            elif ttype == "always":
                matched = True
            elif ttype == "channel":
                matched = channel in (tc.get("channels") or [])
            # Note: shopify_stock triggers (e.g. "stock = 0") aren't handled
            # here — they need product context, which requires the Shopify
            # fetch we haven't done yet at this step. That will come in the
            # real-Claude milestone where the full execution engine lives.

            if matched:
                return template

        return None
    except Exception as e:
        log_event("error", "services._check_template_rule", str(e))
        return None

