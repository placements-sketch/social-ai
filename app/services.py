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
from app.integrations.shopify import get_product_info, get_stock_level, search_products
from app.integrations.meta import send_instagram_reply, send_whatsapp_reply, send_facebook_reply
from app.integrations.tiktok import send_tiktok_reply
from app.utils.intent import detect_intents, intents_to_label
from app.utils.logger import log_event
from app.handoff import check_handoff


# Sentinel returned when the AI is gated off — useful for tests and
# anyone calling process_message synchronously.
AI_SUPPRESSED = ""

def _conversation_history_for_ai(conversation_id: int, limit: int = 8) -> list[dict]:
    """
    Pull the recent message history of a conversation, formatted for Claude's
    messages array. Returns oldest → newest. The current inbound message is
    NOT included — process_message appends it separately.
    
    limit=8 means up to 8 prior turns (4 exchanges). Keeps token usage bounded.
    """
    if not conversation_id:
        return []
    try:
        from app.models import Message
        rows = (Message.query
                .filter_by(conversation_id=conversation_id)
                .filter((Message.sender != 'ai_pending') | (Message.sender.is_(None)))
                .order_by(Message.created_at.desc())
                .limit(limit + 1)
                .all())
        # rows are newest-first; reverse to chronological
        rows = list(reversed(rows))
        # Drop the last one if it's the current inbound (matches by being very recent)
        # Simpler: just transform all and let the caller skip if needed
        history = []
        for m in rows:
            if m.direction == 'inbound':
                history.append({'role': 'user',      'content': m.content})
            elif m.direction == 'outbound':
                history.append({'role': 'assistant', 'content': m.content})
        return history
    except Exception as e:
        log_event("warn", "services._conversation_history_for_ai",
                  f"History fetch failed, replying without context: {e}")
        return []

def process_message(message: str, user_id: str, channel: str, external_id: str | None = None, media_id: str | None = None) -> str:
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
    # ── Dispatch idempotency ──
    # Meta sometimes retries webhooks if we're slow to return 200, causing
    # duplicate AI replies to land in the customer's IG inbox even when the
    # DB dedupe stops duplicate rows. Track which mids we've already 
    # dispatched a reply for, in-process.
    if external_id:
        from app import db
        from app.models import Message
        already_replied = Message.query.filter_by(
            external_id=external_id
        ).first()
        if already_replied:
            # We've already processed this exact webhook. Skip entirely
            # to prevent re-sending the AI reply to the customer.
            log_event("info", "services.duplicate_webhook",
                      f"Duplicate webhook for mid={external_id} — skipping",
                      payload={
                          "external_id": external_id,
                          "user_external_id": user_id,
                          "channel": channel,
                      })
            return AI_SUPPRESSED
        
    log_event("info", "services.inbound",
              f"Inbound [{channel}] from {user_id}: {message[:80]}",
              payload={
                  "user_external_id": user_id,
                  "channel": channel,
                  "preview": message[:160],
              })

    # ── Step 1: Persist inbound IMMEDIATELY ────────────────────────────────
    # Done first so the human inbox shows the new message even when AI is
    # off. Intent labelling can't happen until after detect_intents below;
    # we'll patch the intent field in a moment.
    inbound_record = _save_message(
        user_id=user_id, channel=channel, content=message,
        intent=None, direction="inbound", external_id=external_id,
        media_id=media_id,
    )

    # ── Step 1.5: Notify the assigned agent of new inbound (if any) ────────
    # If this conversation is assigned to someone AND the AI isn't going to
    # auto-reply (or even if it is — the agent still needs to know), ping them.
    # Coalesced so 5 rapid messages from the same customer = 1 notification.
    _notify_assigned_agent_of_inbound(inbound_record, message)

    # ── Step 2: Gate — should the AI respond? ──────────────────────────────
    # Two switches both default to "AI responds" if missing:
    #   - Channel.enabled       (channel-wide kill switch, set on the
    #                            Channels admin page)
    #   - Conversation.ai_enabled (per-thread, flipped when a human takes
    #                              over a specific conversation)
    if not _ai_should_respond(channel=channel, user_id=user_id, message=message):
        reason = (
            "not_a_question"
            if channel.endswith("_comment")
            else "channel_disabled_or_handed_over"
        )
        log_event("info", "services.ai_suppressed",
                  f"AI suppressed for [{channel}] {user_id}: {reason}",
                  payload={
                      "user_external_id": user_id,
                      "channel": channel,
                      "reason": reason,
                  },
                  conversation_id=(inbound_record.conversation_id if inbound_record else None))
        return AI_SUPPRESSED

    # ── Step 3: Detect ALL intents in the message ──────────────────────────
    # A single message can contain multiple intents:
    # "Hi, is this available in blue and how much is delivery to Kilimani?"
    # → ["greeting", "stock_inquiry", "product_inquiry", "delivery_inquiry", "price_inquiry"]
    intents = detect_intents(message)
    log_event("info", "services.intents",
              f"Intents detected: {intents}",
              payload={
                  "user_external_id": user_id,
                  "channel": channel,
                  "intents": intents,
              },
              conversation_id=(inbound_record.conversation_id if inbound_record else None))

    # Update the inbound record's intent now that we know it.
    _patch_inbound_intent(inbound_record, intents)

    # ── Step 3.5: Handoff check — should this conversation go to a human? ──
    handoff = _check_handoff_for_inbound(message, intents, inbound_record)
    if handoff:
        bridging = handoff["bridging_reply"]
        new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=bridging,
                                     comment_external_id=external_id)
        _save_message(user_id=user_id, channel=channel, content=bridging,
                      intent=None, direction="outbound",
                      external_id=new_ext_id)
        return bridging

    # ── Step 3.6: Template-reply rule check ────────────────────────────────
    # Some automation rules short-circuit the AI with a canned reply
    # (e.g. "Out of stock"). First matching rule wins.
    template = _check_template_rule(message, intents, channel)
    if template:
        new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=template,
                                     comment_external_id=external_id)
        _save_message(user_id=user_id, channel=channel, content=template,
                      intent=None, direction="outbound",
                      external_id=new_ext_id)
        log_event("info", "services.template_reply",
                  f"Template-rule reply used for [{channel}] {user_id}",
                  payload={
                      "user_external_id": user_id,
                      "channel": channel,
                      "intents": intents,
                  },
                  conversation_id=(inbound_record.conversation_id if inbound_record else None))
        return template

    # ── Step 4: Fetch data for every relevant intent ───────────────────────
    context_data = {}

    product_intents = {"product_inquiry", "price_inquiry", "stock_inquiry"}
    ambient_intents = {"greeting", "unknown"}

    # Decide where to source the product keyword from:
    #   1. Current message has a product intent → extract from current
    #   2. Current message is purely ambient (greeting / unknown) AND
    #      conversation has recent product context → reuse from history
    #   3. Otherwise (e.g. customer pivoted to a delivery/order question) →
    #      no product fetch — that question gets its own context handling
    product_keyword = None
    keyword_source = None

    if product_intents.intersection(intents):
        product_keyword = _extract_product_keyword(message)
        keyword_source = "current_message"
    elif inbound_record is not None and set(intents) <= ambient_intents:
        product_keyword = _find_recent_product_keyword(inbound_record.conversation_id)
        if product_keyword:
            keyword_source = "history"

    if product_keyword:
        # Multi-term search: extract additional terms from the current message
        # so "black dress" matches the Black Wrap Dress better than just any dress.
        # On history-source follows, we only have the carried keyword.
        if keyword_source == "current_message":
            search_terms = _extract_product_keywords(message)
        else:
            search_terms = [product_keyword]

        matches = search_products(search_terms, limit=3)

        if matches:
            context_data["products"] = matches              # full list for Claude
            context_data["product"]  = matches[0]           # single best (backwards compat)
            context_data["stock"]    = {
                "product_name": matches[0].get("name"),
                "quantity":     matches[0].get("stock_quantity", 0),
                "unit":         "pcs",
            }
            _patch_inbound_product_keyword(inbound_record, product_keyword)

            log_event("info", "services.shopify_lookup",
                      f"Found {len(matches)} matches for '{product_keyword}' (source: {keyword_source})",
                      payload={
                          "user_external_id": user_id,
                          "channel": channel,
                          "product_keyword": product_keyword,
                          "keyword_source": keyword_source,
                          "match_count": len(matches),
                          "match_names": [p.get("name") for p in matches],
                      },
                      conversation_id=(inbound_record.conversation_id if inbound_record else None))
        else:
            log_event("info", "services.shopify_lookup_empty",
                      f"No cache matches for '{product_keyword}' (source: {keyword_source})",
                      payload={
                          "user_external_id": user_id,
                          "channel": channel,
                          "product_keyword": product_keyword,
                          "keyword_source": keyword_source,
                      },
                      conversation_id=(inbound_record.conversation_id if inbound_record else None))

    if "delivery_inquiry" in intents:
        context_data["delivery_asked"] = True
        context_data["delivery_location"] = _extract_location(message)

    if "order_status" in intents:
        context_data["order_status_asked"] = True

    # ── Step 5a: Create placeholder outbound message FIRST (two-phase) ─────
    # We need message_id available BEFORE the AI runs so we can build UTM
    # URLs (which include conversation_id + message_id) into the context.
    placeholder, conversation_id, _user_row_id = _create_placeholder_outbound(
        user_id=user_id, channel=channel,
    )
    if placeholder is None:
        # Fall back to conversation-only tracking; still generate a reply
        conversation_id = inbound_record.conversation_id if inbound_record else None

    # ── Step 5b: Generate AI reply with conv_id + msg_id available ─────────
    history = []
    if inbound_record is not None:
        history = _conversation_history_for_ai(inbound_record.conversation_id, limit=8)
        if history and history[-1].get('content') == message:
            history = history[:-1]

    # Enrich context with the IDs so the generator can build UTM URLs
    context_data['_utm_conversation_id'] = conversation_id
    context_data['_utm_message_id'] = placeholder.id if placeholder else None

    ai_result = generate_reply(message, intents, context_data, channel, history=history)
    reply           = ai_result['reply']
    ai_elapsed_ms   = ai_result['elapsed_ms']
    ai_tokens_used  = ai_result['tokens_used']
    ai_model        = ai_result['model']
    utm_token       = ai_result.get('utm_token')
    product_url     = ai_result.get('product_url')

    # ── Step 6: Send reply to the customer IMMEDIATELY (no delay to IG) ────
    new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=reply,
                                 comment_external_id=external_id)

    log_event("info", "services.ai_reply",
              f"AI replied via {channel} to {user_id}",
              payload={
                  "user_external_id": user_id,
                  "channel": channel,
                  "intents": intents,
                  "reply_preview": reply[:160],
                  "utm_token": utm_token,
              },
              conversation_id=conversation_id)

    # ── Step 7: Brief delay before finalizing the outbound (dashboard order) ─
    import time
    time.sleep(5)
    _finalize_outbound_message(
        placeholder=placeholder,
        content=reply,
        ai_response_time_ms=ai_elapsed_ms,
        ai_tokens_used=ai_tokens_used,
        ai_model=ai_model,
        external_id=new_ext_id,
        utm_token=utm_token,
        product_url=product_url,
    )

    return reply

# ─────────────────────────────────────────────
# Gate helpers
# ─────────────────────────────────────────────

def _ai_should_respond(channel: str, user_id: str, message: str | None = None) -> bool:
    """
    Returns True iff:
      - the channel is enabled (or no Channel row exists — fail open), AND
      - the conversation has ai_enabled (or no conversation exists yet — fail open), AND
      - for *_comment channels: the message looks like a question

    The question-gate exists because comments are PUBLIC. We don't want
    the bot replying to "love this!" or pure emoji praise on a post.
    DMs reply to everything (private 1:1, expected behavior).
    """
    try:
        from app.models import Channel, Conversation, User
        from app.utils.intent import is_question

        ch = Channel.query.filter_by(channel=channel).first()
        if ch is not None and not ch.enabled:
            return False

        customer = User.query.filter_by(external_id=user_id, channel=channel).first()
        if customer is None:
            # Brand new customer — apply the comment gate but still allow DMs
            if channel.endswith("_comment") and message is not None:
                return is_question(message)
            return True

        conv = (
            Conversation.query
            .filter_by(user_id=customer.id, channel=channel)
            .order_by(Conversation.id.desc())
            .first()
        )
        if conv is None:
            if channel.endswith("_comment") and message is not None:
                return is_question(message)
            return True

        if not bool(conv.ai_enabled):
            return False

        # Final gate: for comments, must be a question
        if channel.endswith("_comment") and message is not None:
            return is_question(message)

        return True

    except Exception as e:
        log_event("error", "services._ai_should_respond", str(e))
        return True

# ─────────────────────────────────────────────
# Internal helpers (extraction)
# ─────────────────────────────────────────────

def _extract_product_keywords(message: str, max_terms: int = 4) -> list[str]:
    """
    Extract multiple product-relevant terms (3+ chars, non-stopword) ordered
    longest-first. Returns up to `max_terms` — passed to search_products
    so each query can match e.g. "black" AND "dress" together rather than
    picking one and missing the other.
    """
    stopwords = {
        "is", "the", "a", "an", "do", "you", "have", "what", "how", "much",
        "in", "stock", "available", "this", "that", "it", "yes", "no",
        "and", "or", "if", "for", "to", "of", "with", "hi", "hello", "hey",
        "any", "show", "me", "got", "we", "us", "some", "more", "please",
        "can", "could", "would", "will", "want", "need", "looking", "find",
    }
    words = [w.strip("?.,!") for w in message.lower().split()]
    candidates = [w for w in words if w and w not in stopwords and len(w) >= 3]
    # Dedupe while preserving order, then sort by length desc
    seen = set()
    unique = []
    for w in candidates:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    unique.sort(key=len, reverse=True)
    return unique[:max_terms]


# Keep the old single-keyword extractor as a thin wrapper for any callers
# (and for the legacy product_keyword DB column, which is still a single string).
def _extract_product_keyword(message: str) -> str:
    terms = _extract_product_keywords(message)
    return terms[0] if terms else message[:30]

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


def _dispatch_reply(channel: str, user_id: str, reply: str, **kwargs) -> str | None:
    """
    Send the reply back to the customer through the right channel API.
    Returns Meta's new message/comment ID on success, None on failure.
    The caller persists this on the outbound Message row so edit/delete
    can later reach Meta's API.
    """
    """
    Send the reply back to the customer through the right channel API.

    Channels:
      - instagram_dm      → Meta Graph API (implemented)
      - facebook_dm       → Meta Graph API (TODO)
      - whatsapp          → Meta WhatsApp Cloud API (TODO)
      - tiktok_dm         → TikTok Business API (TODO)
      - *_comment         → reply lands as a comment (TODO, different endpoint)

    Failures here MUST NOT crash the pipeline. The reply is already saved
    to our DB so a human agent can manually resend if dispatch fails.
    """
    if not reply:
        return None

    if channel == "instagram_dm":
        from app.integrations.meta import send_instagram_reply
        resp = send_instagram_reply(recipient_id=user_id, text=reply)
        return (resp or {}).get("message_id")

    if channel == "facebook_dm":
        # TODO: facebook send API — same shape but different endpoint
        log_event("warning", "services.dispatch",
                  f"Facebook send not implemented — reply saved to DB only",
                  payload={"channel": channel, "user_external_id": user_id})
        return

    if channel == "whatsapp":
        # TODO: WhatsApp Cloud API
        log_event("warning", "services.dispatch",
                  f"WhatsApp send not implemented — reply saved to DB only",
                  payload={"channel": channel, "user_external_id": user_id})
        return

    if channel in ("tiktok_dm", "tiktok_comment"):
        log_event("warning", "services.dispatch",
                  f"TikTok send not implemented — reply saved to DB only",
                  payload={"channel": channel, "user_external_id": user_id})
        return

    if channel == "instagram_comment":
        # For IG comments, user_id passed in is actually the commenter's
        # external_id, but to reply we need the COMMENT_ID we're replying to.
        # The caller (services.process_message or messages.send_reply) passes
        # it via the `comment_external_id` kwarg.
        from app.integrations.meta import send_instagram_comment_reply
        comment_external_id = kwargs.get("comment_external_id")
        if not comment_external_id:
            log_event("error", "services.dispatch",
                      "Missing comment_external_id for instagram_comment dispatch",
                      payload={"channel": channel, "user_external_id": user_id})
            return None
        resp = send_instagram_comment_reply(comment_id=comment_external_id, text=reply)
        # Meta returns {"id": "<new_comment_id>"} for successful comment replies
        return (resp or {}).get("id")

    if channel == "facebook_comment":
        log_event("warning", "services.dispatch",
                  f"Facebook comment reply not implemented — reply saved to DB only",
                  payload={"channel": channel, "user_external_id": user_id})
        return

    log_event("warning", "services.dispatch",
              f"Unknown channel '{channel}' — cannot dispatch reply",
              payload={"channel": channel, "user_external_id": user_id})


# ─────────────────────────────────────────────
# Internal helpers (persistence)
# ─────────────────────────────────────────────

def _save_message(user_id, channel, content, intent, direction,
                  external_id=None, media_id=None,
                  ai_response_time_ms=None,
                  ai_tokens_used=None, ai_model=None):
    """
    Persist a message and return the Message row (or None on failure).
    Creates the User and Conversation if they don't exist yet.
    """
    try:
        from app import db
        from app.models import Message, User, Conversation

        # Idempotency: if this Meta message ID is already saved, return it.
        if external_id:
            existing = Message.query.filter_by(external_id=external_id).first()
            if existing:
                return existing

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
            external_id=external_id,
            media_id=media_id,
            ai_response_time_ms=ai_response_time_ms,
            ai_tokens_used=ai_tokens_used,
            ai_model=ai_model,
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

def _create_placeholder_outbound(user_id, channel):
    """
    Two-phase message creation, Phase 1: create the outbound row IMMEDIATELY
    so we have a message_id available before the AI runs. This lets us build
    UTM URLs (which need message_id) at context-build time.
    
    Returns the (Message row, conversation_id, user_row_id) tuple, or (None, None, None) on failure.
    
    The row is marked sender='ai_pending' so the dashboard filters it out
    until finalize_outbound_message() updates it with real content.
    """
    try:
        from app import db
        from app.models import Message, User, Conversation

        user = User.query.filter_by(external_id=user_id, channel=channel).first()
        if not user:
            user = User(external_id=user_id, channel=channel)
            db.session.add(user)
            db.session.flush()

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

        placeholder = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            channel=channel,
            direction="outbound",
            sender="ai_pending",   # ← dashboard filters this out
            content="",
            intent=None,
        )
        db.session.add(placeholder)
        db.session.commit()
        return placeholder, conversation.id, user.id

    except Exception as e:
        log_event("error", "services._create_placeholder_outbound", str(e))
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return None, None, None


def _finalize_outbound_message(placeholder, content, ai_response_time_ms=None,
                                ai_tokens_used=None, ai_model=None,
                                external_id=None, utm_token=None, product_url=None):
    """
    Two-phase message creation, Phase 2: fill in the real content on the
    placeholder created earlier. Flips sender from 'ai_pending' to 'ai' so
    the dashboard now displays it. Also updates the conversation's last_message
    fields so the inbox preview shows the reply.
    
    Safe to call even if placeholder is None (falls back to logging).
    """
    if placeholder is None:
        log_event("warn", "services._finalize_outbound_message",
                  "No placeholder to finalize — outbound message will not be persisted")
        return None
    
    try:
        from app import db
        from app.models import Conversation

        placeholder.content = content
        placeholder.sender = "ai"
        placeholder.external_id = external_id
        placeholder.ai_response_time_ms = ai_response_time_ms
        placeholder.ai_tokens_used = ai_tokens_used
        placeholder.ai_model = ai_model
        placeholder.utm_token = utm_token
        placeholder.product_url = product_url

        # Update conversation preview fields
        conv = Conversation.query.get(placeholder.conversation_id)
        if conv is not None:
            conv.last_message = content[:200]
            conv.last_message_at = datetime.utcnow()

        db.session.commit()
        return placeholder

    except Exception as e:
        log_event("error", "services._finalize_outbound_message", str(e))
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

def _patch_inbound_product_keyword(inbound_record, product_keyword: str):
    """
    Write the extracted product keyword onto the inbound row. Used so future
    messages in the same conversation can find what was being discussed.
    """
    if inbound_record is None or not product_keyword:
        return
    try:
        from app import db
        inbound_record.product_keyword = product_keyword
        db.session.commit()
    except Exception as e:
        log_event("error", "services._patch_inbound_product_keyword", str(e))


def _find_recent_product_keyword(conversation_id: int, max_lookback: int = 5) -> str | None:
    """
    Look back through the conversation's recent inbound messages for the most
    recent product keyword. Returns None if nothing relevant in history.
    
    max_lookback caps how far we look — past 5 messages is probably stale context.
    """
    if not conversation_id:
        return None
    try:
        from app.models import Message
        rows = (Message.query
                .filter_by(conversation_id=conversation_id, direction='inbound')
                .order_by(Message.created_at.desc())
                .limit(max_lookback)
                .all())
        for m in rows:
            if m.product_keyword:
                return m.product_keyword
        return None
    except Exception as e:
        log_event("warn", "services._find_recent_product_keyword", str(e))
        return None


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
    

def _notify_assigned_agent_of_inbound(inbound_record, message_text):
    """
    If this conversation is assigned to an agent, notify them of the new
    inbound message. Coalesced so rapid-fire messages don't spam.

    Failures are swallowed — the main pipeline must not break because of
    a notification problem.
    """
    if inbound_record is None:
        return
    try:
        from app import db
        from app.models import Conversation
        from app.notifications import create_notification

        conv = Conversation.query.get(inbound_record.conversation_id)
        if conv is None or conv.assigned_to is None:
            return  # not assigned to anyone — nothing to do

        handle = conv.user.external_id if conv.user else 'a customer'
        channel_label = conv.channel.replace('_', ' ')
        preview = (message_text or '')[:120]

        # Higher severity if AI is off (because the agent really needs to reply
        # themselves) vs on (because AI will at least keep things moving).
        sev = 'urgent' if not conv.ai_enabled else 'info'

        create_notification(
            user_id=conv.assigned_to,
            type_='new_inbound_on_my_conversation',
            title=f"New message from {handle}",
            body=f"{channel_label}: \"{preview}\"",
            severity=sev,
            resource_type='conversation',
            resource_id=conv.id,
            actor_id=None,  # customer-triggered, not staff
            coalesce=True,
        )
        db.session.commit()
    except Exception as e:
        log_event("error", "services._notify_assigned_agent_of_inbound", str(e))
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass