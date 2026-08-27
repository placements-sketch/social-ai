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
from sqlalchemy.exc import IntegrityError
from app.integrations.shopify import get_product_info, get_stock_level, search_products
from app.integrations.meta import send_instagram_reply, send_whatsapp_reply, send_facebook_reply
from app.integrations.tiktok import send_tiktok_reply
from app.utils.intent import detect_intents, intents_to_label
from app.utils.logger import log_event
from app.handoff import check_handoff

import os
import re

# Sentinel returned when the AI is gated off — useful for tests and
# anyone calling process_message synchronously.
AI_SUPPRESSED = ""

# ── Why a customer got no AI reply ───────────────────────────────────────────
# Every path out of process_message() that does NOT dispatch a reply records
# one of these via _record_no_reply(), on the single log source
# 'services.no_reply_sent'. One query then answers "why wasn't this answered?"
# for any conversation — previously the reasons were spread across five
# different log sources and some paths (exceptions, failed sends) logged
# nothing at all, leaving gaps nobody could explain.
NO_REPLY_DUPLICATE_WEBHOOK     = "duplicate_webhook"

# ── Inbound claim ────────────────────────────────────────────────────────────
# Message ids we have started processing, newest last. Never released: an id is
# unique to one message, so "seen" is permanent and this doubles as a dedupe
# cache. Bounded so a long-running process cannot grow it without limit.
import threading as _threading
from collections import OrderedDict as _OrderedDict

_SEEN_INBOUND = _OrderedDict()
_SEEN_INBOUND_LOCK = _threading.Lock()
_SEEN_INBOUND_MAX = 5000


def _claim_inbound(external_id: str) -> bool:
    """
    True if this thread is the first to claim `external_id`.

    The database check that follows is a read whose matching write lands much
    later, so on its own it cannot stop two concurrent deliveries of the same
    webhook from both proceeding. This makes the claim atomic.
    """
    if not external_id:
        return True                     # nothing to key on; let it through
    with _SEEN_INBOUND_LOCK:
        if external_id in _SEEN_INBOUND:
            return False
        _SEEN_INBOUND[external_id] = None
        while len(_SEEN_INBOUND) > _SEEN_INBOUND_MAX:
            _SEEN_INBOUND.popitem(last=False)
        return True
NO_REPLY_MASTER_SWITCH_OFF     = "ai_master_switch_off"
NO_REPLY_SETTINGS_UNREADABLE   = "settings_unreadable"
NO_REPLY_CHANNEL_DISABLED      = "channel_disabled"
NO_REPLY_CONVERSATION_AI_OFF   = "conversation_ai_off"
NO_REPLY_NOT_A_QUESTION        = "not_a_question"
NO_REPLY_PRAISE                = "praise_no_question"
NO_REPLY_AI_UNAVAILABLE        = "ai_unavailable"
NO_REPLY_IMAGE_UNCONFIRMED     = "image_match_unconfirmed"
NO_REPLY_SUPERSEDED            = "superseded_by_newer_message"
NO_REPLY_DISPATCH_FAILED       = "dispatch_failed"
NO_REPLY_EXCEPTION             = "pipeline_exception"
NO_REPLY_OWN_ACCOUNT           = "authored_by_us"

# Reasons that mean the system worked as designed. Everything else is a fault
# worth surfacing, and is logged at 'error' so it reaches the alerts feed.
NO_REPLY_BY_DESIGN = {
    NO_REPLY_DUPLICATE_WEBHOOK,
    NO_REPLY_MASTER_SWITCH_OFF,
    NO_REPLY_CHANNEL_DISABLED,
    NO_REPLY_CONVERSATION_AI_OFF,
    NO_REPLY_NOT_A_QUESTION,
    NO_REPLY_PRAISE,
    NO_REPLY_SUPERSEDED,
    NO_REPLY_OWN_ACCOUNT,
}

# Human-readable, for the Dashboard. Keep in sync with the constants above.
NO_REPLY_LABELS = {
    NO_REPLY_DUPLICATE_WEBHOOK:   "Duplicate webhook",
    NO_REPLY_MASTER_SWITCH_OFF:   "AI master switch off",
    NO_REPLY_SETTINGS_UNREADABLE: "Settings unreadable",
    NO_REPLY_CHANNEL_DISABLED:    "Channel disabled",
    NO_REPLY_CONVERSATION_AI_OFF: "AI off for this chat",
    NO_REPLY_NOT_A_QUESTION:      "Comment wasn't a question",
    NO_REPLY_AI_UNAVAILABLE:      "AI unavailable — sent to a human",
    NO_REPLY_IMAGE_UNCONFIRMED:   "Photo we couldn't identify — sent to a human",
    NO_REPLY_PRAISE:              "Praise — liked, not replied to",
    NO_REPLY_SUPERSEDED:          "Answered as part of a later message",
    NO_REPLY_DISPATCH_FAILED:     "Send to platform failed",
    NO_REPLY_EXCEPTION:           "Pipeline error",
    NO_REPLY_OWN_ACCOUNT:         "We wrote it ourselves",
}


def _record_no_reply(reason: str, channel: str, user_id: str,
                     conversation_id: int | None = None, detail: str | None = None):
    """
    The one place that records "this inbound got no AI reply, and here's why".

    Faults log at 'error' so they surface in System Alerts; by-design
    suppressions log at 'info' so they don't cry wolf.
    """
    log_event(
        "info" if reason in NO_REPLY_BY_DESIGN else "error",
        "services.no_reply_sent",
        f"No AI reply on [{channel}] for {user_id}: {reason}"
        + (f" — {detail}" if detail else ""),
        payload={
            "reason": reason,
            "channel": channel,
            "user_external_id": user_id,
            "detail": detail,
        },
        conversation_id=conversation_id,
    )

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

def _writeback_products(snaps):
    """
    Upsert live-fetched product snaps into ProductCache so the normal cache
    search can find them — and so the next customer gets a fast cache hit.
    Reuses products.py's shape mapping. Safe to commit here: the placeholder
    outbound isn't created until Step 5a, so nothing critical is pending.
    """
    if not snaps:
        return
    from app import db
    from app.models import ProductCache
    from app.products import _shopify_to_cache_dict
    now = datetime.utcnow()
    try:
        for sp in snaps:
            d = _shopify_to_cache_dict(sp)
            spid = d.get('shopify_product_id')
            if not spid:
                continue
            row = ProductCache.query.filter_by(shopify_product_id=spid).first()
            if row is None:
                row = ProductCache(shopify_product_id=spid)
                db.session.add(row)
            row.name = d['name']
            row.handle = d['handle']
            row.description = d['description']
            row.price = d['price']
            row.variants = d['variants']
            row.variants_detail = d['variants_detail']
            row.images = d['images']
            row.tags = d['tags']
            row.stock_quantity = d['stock_quantity']
            row.inventory_tracked = d['inventory_tracked']
            row.cached_at = now
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log_event("warn", "services.product_writeback_failed",
                  f"Live product write-back failed: {str(e)[:200]}")

# ── Inbound debounce (worker-safe, DB-backed) ─────────────────────────────
# Customers send a photo then a caption (or several quick texts) as SEPARATE
# webhook events; each would otherwise trigger its own reply. We coalesce using
# the messages TABLE as shared state — this works across gunicorn worker
# processes, unlike an in-process buffer (two events can land on different
# workers, which don't share memory).
_DEBOUNCE_SECONDS = 6.0


def process_inbound(message, user_id, channel, external_id=None, media_id=None, image_urls=None):
    """Entry point for inbound DMs. Debounce now lives inside process_message."""
    return process_message(message, user_id, channel,
                           external_id=external_id, media_id=media_id, image_urls=image_urls)


def _has_newer_inbound(inbound_record) -> bool:
    """True if a newer inbound message exists in this conversation (customer kept typing)."""
    try:
        from app.models import Message
        return Message.query.filter(
            Message.conversation_id == inbound_record.conversation_id,
            Message.direction == 'inbound',
            Message.id > inbound_record.id,
        ).first() is not None
    except Exception as e:
        log_event("warn", "services._has_newer_inbound", str(e))
        return False


def _coalesce_recent_inbound(inbound_record):
    """
    Merge every inbound message since the last outbound reply (the current
    unanswered burst) into one (text, image_urls) turn.
    """
    try:
        from app.models import Message
        last_out = (Message.query.filter(
                        Message.conversation_id == inbound_record.conversation_id,
                        Message.direction == 'outbound',
                        Message.sender != 'ai_pending')
                    .order_by(Message.id.desc())
                    .first())
        q = Message.query.filter(
            Message.conversation_id == inbound_record.conversation_id,
            Message.direction == 'inbound',
            Message.id <= inbound_record.id,
        )
        if last_out is not None:
            q = q.filter(Message.id > last_out.id)
        rows = q.order_by(Message.id.asc()).all()

        texts, images = [], []
        for m in rows:
            c = (m.content or '').strip()
            if c and c != '[Sent a photo]':
                texts.append(c)
            for u in (m.image_urls or []):
                if u not in images:
                    images.append(u)
        return ("\n".join(texts).strip() or "[Sent a photo]"), (images or None)
    except Exception as e:
        log_event("warn", "services._coalesce_recent_inbound", str(e))
        return (inbound_record.content, None)

def _burst_already_answered(inbound_record):
    """
    True if a real outbound reply (not our own pending placeholder) already
    exists after this inbound — meaning another thread already answered this
    burst. Catches Meta splitting a photo and its caption across two separate
    webhooks, and retries landing on the second gunicorn worker.
    """
    try:
        from app.models import Message
        return Message.query.filter(
            Message.conversation_id == inbound_record.conversation_id,
            Message.direction == 'outbound',
            Message.sender.in_(('ai', 'human')),
            Message.id > inbound_record.id,
        ).first() is not None
    except Exception as e:
        log_event("warn", "services._burst_already_answered", str(e))
        return False

def _our_account_identifiers() -> tuple[set[str], set[str]]:
    """
    Every id and handle that means "this is us", not a customer.

    Two sources, deliberately. OAuth connections are authoritative — they are
    the accounts Meta actually delivers webhooks for, and they stay correct
    when somebody reconnects a different page. The environment variables are
    kept as a fallback for deployments that predate the OAuth flow, and because
    a missing MetaConnection row must not silently disable the guard.
    """
    ids: set[str] = set()
    handles: set[str] = set()

    try:
        from app.models import MetaConnection
        for conn in MetaConnection.query.filter_by(is_active=True).all():
            # ig_login_user_id is the account's numeric id under Instagram
            # Login, which authorises the IG account directly and leaves
            # page_id and often ig_business_account_id null. Omitting it meant
            # an Instagram-Login connection was recognised only by handle, so a
            # webhook carrying just the numeric sender slipped through as if a
            # customer had written it.
            for value in (conn.ig_business_account_id, conn.page_id,
                          conn.ig_login_user_id):
                if value:
                    ids.add(str(value).strip())
            if conn.ig_username:
                handles.add(conn.ig_username.strip().lower().lstrip('@'))
            if conn.page_name:
                handles.add(conn.page_name.strip().lower().lstrip('@'))
    except Exception as e:
        # Never let a lookup failure open the gate.
        log_event("warn", "services.own_account_lookup_failed", str(e))

    # Environment fallback. Every one of these accepts a comma-separated list,
    # because an account we cannot complete OAuth for has no row in
    # meta_connections and its numeric id is then a hand-maintained string —
    # exactly the kind that drifts. OUR_ACCOUNT_HANDLES is the durable one: a
    # business always knows its own @handle, even when nobody can produce the
    # 17-digit account id.
    id_vars = ("IG_BUSINESS_ACCOUNT_ID", "FB_PAGE_ID", "TIKTOK_ACCOUNT_ID",
               "OUR_ACCOUNT_IDS")
    handle_vars = ("IG_USERNAME", "BUSINESS_HANDLE", "OUR_ACCOUNT_HANDLES")

    for var in id_vars + handle_vars:
        raw = os.getenv(var)
        if not raw:
            continue
        for value in raw.split(','):
            value = value.strip()
            if not value:
                continue
            if var in handle_vars:
                handles.add(value.lower().lstrip('@'))
            else:
                ids.add(value)

    return ids, handles


def _authored_by_us(user_id: str, channel: str, username: str | None = None) -> bool:
    """
    True when an inbound event was written by our own account.

    Agents answer comments straight from the Instagram app. Those replies come
    back down the webhook in exactly the same shape as a customer's comment —
    same fields, our account as the sender — so without this check they are
    ingested as inbound customer messages. That is how the inbox came to hold a
    conversation whose "customer" is our own handle.

    The danger is not the clutter. It is that the AI treats them as questions to
    answer. An agent's reply ending in a question mark ("...want me to check
    your size?") would have been answered by the AI, publicly, under our own
    post. Worse, the AI's own comment replies arrive back through this same
    webhook: without a guard the AI can answer itself, and each answer produces
    another event to answer. That is a loop with our brand name on it.

    Guarded once here rather than at each webhook, because there are several
    entry points — /webhook/instagram, /webhook/instagram/comments,
    /webhook/facebook/comments, the TikTok routes — and only some of them
    carried the check. A guard that has to be remembered at N call sites is a
    guard that will be missing at one of them.
    """
    if not user_id and not username:
        return False
    ids, handles = _our_account_identifiers()

    candidate = str(user_id or '').strip()
    if candidate and candidate in ids:
        return True

    # Match on the handle too. The numeric account id is the precise signal but
    # a brittle one: it only reaches us through OAuth or a hand-typed
    # environment variable, and when the two disagree the guard silently passes
    # our own comments straight through. Instagram sends `from.username` on
    # every comment event, and a business can always state its own @handle.
    for value in (username, user_id):
        if value and str(value).strip().lower().lstrip('@') in handles:
            return True
    return False


def record_own_platform_reply(message: str, channel: str,
                              external_id: str | None = None,
                              parent_id: str | None = None) -> bool:
    """
    File a reply an agent wrote on the platform itself into the customer's thread.

    Agents answer comments straight from the Instagram app. Those replies used to
    be dropped on the floor: the guard in process_message() stopped the AI
    reacting to them, but the thread in our inbox then showed the customer's
    question with no answer under it, and an agent picking it up later had no way
    to know it had already been handled.

    Meta sends `parent_id` on a comment that replies to another comment. That is
    the customer's original comment, which we stored with its comment id in
    Message.external_id — so the parent points straight at the thread this
    belongs to.

    Returns True when the reply was filed, False when there is nothing to attach
    it to (a fresh top-level comment we posted under our own post belongs to no
    customer conversation, and inventing one would recreate the very problem
    this replaced).
    """
    if not parent_id or not message:
        return False

    from app import db
    from app.models import Message, Conversation

    try:
        # Idempotent: Meta redelivers webhooks, and this must not double-post
        # into the thread.
        if external_id:
            existing = Message.query.filter_by(external_id=external_id).first()
            if existing:
                return True

        parent = Message.query.filter_by(external_id=parent_id).first()
        if not parent:
            # The comment we replied to was never ingested — most likely it
            # predates this integration. Nothing to attach to.
            log_event("info", "services.own_reply_unattached",
                      "Agent replied on-platform to a comment we never ingested",
                      payload={"channel": channel, "parent_id": str(parent_id)[:64]})
            return False

        conversation = Conversation.query.get(parent.conversation_id)
        if not conversation:
            return False

        row = Message(
            conversation_id=conversation.id,
            user_id=parent.user_id,          # still the customer's thread
            channel=channel,
            direction="outbound",
            sender="human",                  # a person wrote it, just not in here
            content=message,
            external_id=external_id,
            media_id=parent.media_id,
            ai_eligible=False,               # the AI was never in a position to send it
        )
        db.session.add(row)

        conversation.last_message = message[:200]
        conversation.last_message_at = datetime.utcnow()

        # A human has visibly taken this thread over on the platform. Leaving the
        # AI armed invites exactly the collision this whole change is about: the
        # agent answers on Instagram, the AI answers again underneath, and the
        # customer gets two different replies in public.
        if conversation.ai_enabled:
            conversation.ai_enabled = False
            log_event("info", "services.ai_off_agent_replied_on_platform",
                      "AI switched off for this conversation — an agent answered "
                      "from the platform app",
                      conversation_id=conversation.id)

        db.session.commit()
        log_event("info", "services.own_reply_recorded",
                  "Filed an agent's on-platform reply into the customer thread",
                  conversation_id=conversation.id)
        return True

    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        log_event("error", "services.own_reply_failed", str(e))
        return False


def process_message(message: str, user_id: str, channel: str, external_id: str | None = None,
                    media_id: str | None = None, image_urls: list | None = None,
                    parent_id: str | None = None, username: str | None = None) -> str:
    """
    Public pipeline entry point — a thin wrapper that guarantees an unanswered
    message is always explainable.

    Every deliberate exit inside _process_message() records its own reason. An
    *undeliberate* one — anything raising past all the inner handlers — used to
    escape with no trace at all, which is exactly the unexplainable gap this
    logging exists to remove. So the last resort is caught here.

    Swallows rather than re-raises: webhook senders retry on a non-200, and a
    retry storm on a message we cannot process helps nobody. The inbound row is
    already saved, so an agent can still answer by hand.
    """
    # Never react to our own writing. Checked before _process_message so that
    # nothing is persisted either — an agent replying from the Instagram app
    # must not create a conversation in which we are the customer.
    if _authored_by_us(user_id, channel, username=username):
        # Not merely ignored — filed into the customer's thread when we can tell
        # which thread it belongs to, so the inbox shows the answer the customer
        # actually received.
        filed = record_own_platform_reply(message, channel,
                                          external_id=external_id,
                                          parent_id=parent_id)
        log_event("info", "services.no_reply_sent",
                  f"Event authored by our own account on {channel} "
                  f"({'filed into the customer thread' if filed else 'no thread to file it under'})",
                  payload={"reason": NO_REPLY_OWN_ACCOUNT,
                           "channel": channel,
                           "sender": str(user_id)[:64],
                           "filed": filed})
        return AI_SUPPRESSED

    try:
        return _process_message(message, user_id, channel, external_id, media_id, image_urls)
    except Exception as e:
        import traceback
        # Resolve the conversation here rather than threading an id out of the
        # inner function. (user_id, channel) already identifies it — the same
        # lookup _save_message does — so a failure can be attributed to the
        # customer it happened to, which is what lets it count against the
        # success rate. Best-effort: a brand-new customer whose very first save
        # failed genuinely has no conversation yet, and NULL is the honest
        # answer there.
        conv_id = None
        try:
            from app.models import Conversation, User
            customer = User.query.filter_by(external_id=user_id, channel=channel).first()
            if customer is not None:
                conv = (Conversation.query
                        .filter_by(user_id=customer.id, channel=channel)
                        .order_by(Conversation.id.desc()).first())
                conv_id = conv.id if conv else None
        except Exception:
            pass

        _record_no_reply(NO_REPLY_EXCEPTION, channel, user_id,
                         conversation_id=conv_id,
                         detail=f"{type(e).__name__}: {e}")
        log_event("error", "services.pipeline_exception",
                  f"Unhandled error processing [{channel}] message from {user_id}: {e}",
                  payload={"channel": channel, "user_external_id": user_id,
                           "traceback": traceback.format_exc()[-2000:]})
        return AI_SUPPRESSED


def _process_message(message: str, user_id: str, channel: str, external_id: str | None = None, media_id: str | None = None, image_urls: list | None = None) -> str:
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

        # Claimed atomically BEFORE the database check.
        #
        # The check below is a read, and the matching write happens much later
        # in this function — so with concurrent webhook handling two deliveries
        # of the same event could both read "not seen yet", both pass, and both
        # run the entire pipeline. That is what puts pairs of identical lines in
        # Live Activity: not one event logged twice, but the same event
        # genuinely processed twice, replies and all.
        #
        # Claiming closes that window: whichever thread gets there first owns
        # the id, and the loser stops immediately. The DB check stays as the
        # cross-process and cross-restart backstop.
        if not _claim_inbound(external_id):
            _record_no_reply(NO_REPLY_DUPLICATE_WEBHOOK, channel, user_id,
                             detail=f"concurrent delivery, mid={external_id}")
            return AI_SUPPRESSED

        already_replied = Message.query.filter_by(
            external_id=external_id
        ).first()
        if already_replied:
            # We've already processed this exact webhook. Skip entirely
            # to prevent re-sending the AI reply to the customer.
            _record_no_reply(NO_REPLY_DUPLICATE_WEBHOOK, channel, user_id,
                             conversation_id=already_replied.conversation_id,
                             detail=f"mid={external_id}")
            return AI_SUPPRESSED
        
    # Logged BEFORE the save, deliberately: if _save_message fails we still
    # want a record that the message arrived. The conversation doesn't exist
    # yet at this point, so the row is linked back once it does — see just
    # below. Without that link this was the one feed line you couldn't click
    # through to, which is also the most important one.
    inbound_log = log_event("info", "services.inbound",
              f"Inbound [{channel}] from {user_id}: {message[:80]}",
              payload={
                  "user_external_id": user_id,
                  "channel": channel,
                  "preview": message[:160],
              })

    # A caption-less photo has no text — give it a placeholder so it saves,
    # classifies, and displays cleanly. The real content rides in image_urls.
    if not (message or "").strip() and image_urls:
        message = "[Sent a photo]"

    # ── Step 1: Persist inbound IMMEDIATELY ────────────────────────────────
    # Done first so the human inbox shows the new message even when AI is
    # off. Intent labelling can't happen until after detect_intents below;
    # we'll patch the intent field in a moment.
    inbound_record = _save_message(
        user_id=user_id, channel=channel, content=message,
        intent=None, direction="inbound", external_id=external_id,
        media_id=media_id, image_urls=image_urls,
    )

    # Link the arrival log to the conversation now that we have one. Kept
    # best-effort — a logging detail must never break message handling.
    if inbound_log is not None and inbound_record is not None:
        try:
            from app import db
            inbound_log.conversation_id = inbound_record.conversation_id
            db.session.commit()
        except Exception:
            try:
                from app import db
                db.session.rollback()
            except Exception:
                pass

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
    should_reply, gate_reason = _ai_should_respond(
        channel=channel, user_id=user_id, message=message)
    if not should_reply:
        _record_no_reply(gate_reason, channel, user_id,
                         conversation_id=(inbound_record.conversation_id
                                          if inbound_record else None))
        # The master switch being off means this is human work now — so route
        # it to humans instead of leaving it where nobody can see it.
        #
        # Without this, a message arriving while the switch is off keeps
        # ai_enabled=true and status='active'. The AI will not answer it, the
        # Unclaimed queue cannot see it (that needs status='human_override'),
        # and no agent's inbox lists it (that needs an assignee). It is
        # invisible to every part of the product at once, which is how 13 DMs
        # went unanswered for up to 18 days.
        #
        # Only for the master switch. A disabled channel or a conversation a
        # human already took over are deliberate states that already have an
        # owner; re-routing those would undo somebody's decision.
        if gate_reason == NO_REPLY_MASTER_SWITCH_OFF and inbound_record is not None:
            _route_to_humans_switch_off(inbound_record.conversation_id)
        return AI_SUPPRESSED

    # ── Step 3: Detect ALL intents in the message ──────────────────────────
    # A single message can contain multiple intents:
    # "Hi, is this available in blue and how much is delivery to Kilimani?"
    # → ["greeting", "stock_inquiry", "product_inquiry", "delivery_inquiry", "price_inquiry"]
   # ── Step 3: Classify the message (intents + handoff) via Claude ────────
    # Semantic classification replaces brittle keyword matching — understands
    # meaning, so far fewer "unknown"s, and flags handoff for things no keyword
    # covers (e.g. "get me a human", abuse). Degrades to keywords on any failure.
    # ── Step 2.5: Debounce — coalesce a customer's rapid messages (worker-safe) ─
    # Wait a short quiet window; if a NEWER inbound arrived meanwhile, bow out and
    # let that later event answer the whole burst. Otherwise gather the burst
    # (photo + caption + any quick texts) into one turn. DB-backed → survives
    # across gunicorn workers, unlike an in-memory buffer.
    if inbound_record is not None and not channel.endswith('_comment'):
        import time
        time.sleep(_DEBOUNCE_SECONDS)
        if _has_newer_inbound(inbound_record):
            _record_no_reply(NO_REPLY_SUPERSEDED, channel, user_id,
                             conversation_id=inbound_record.conversation_id,
                             detail="newer message arrived during the quiet window")
            return AI_SUPPRESSED
        message, image_urls = _coalesce_recent_inbound(inbound_record)

    from app.ai.classifier import classify_message
    # Classify the CURRENT message on its own — do NOT feed conversation history.
    # History was poisoning the handoff decision: after a human handled a
    # complaint and AI was re-enabled, the next (benign) message got re-read as a
    # complaint because the old angry turns were still in view, re-escalating
    # every time. The reply generator still gets full history (Step 5b) for
    # context; only the intent/handoff classification is per-message.
    classification = classify_message(message)
    intents = classification["intents"]
    # Carry `degraded` alongside the verdict. check_handoff() has to be able to
    # tell "the AI read this and saw nothing needing a person" from "the AI
    # never ran" — they produce the same {should: False} and mean opposite
    # things. Without it, a classifier outage reads as a clean bill of health
    # and every complaint that week is answered by a bot.
    _llm_handoff = {**classification["handoff"],
                    "degraded": bool(classification.get("degraded"))}

    log_event("info", "services.intents",
              f"Intents detected: {intents}",
              payload={
                  "user_external_id": user_id,
                  "channel": channel,
                  "intents": intents,
                  "handoff_signal": _llm_handoff,
              },
              conversation_id=(inbound_record.conversation_id if inbound_record else None))

    # Update the inbound record's intent now that we know it.
    # Pass the degraded flag through so the row records WHICH reader produced
    # these intents, not just what they were.
    _patch_inbound_intent(inbound_record, intents,
                          degraded=bool(classification.get('degraded')))

    # Link this person to their Shopify record when the message proves who they
    # are. Runs on every inbound because the proof usually arrives mid-thread —
    # a customer types their email to chase an order, and from that moment the
    # conversation can carry their purchase history.
    #
    # Best-effort and silent: it never overwrites an agent's link and a failure
    # must not cost the customer a reply.
    try:
        from app.identity import try_auto_link
        from app.models import User as _User
        _cust = (_User.query.get(inbound_record.user_id)
                 if inbound_record is not None else None)
        if _cust is not None:
            try_auto_link(_cust, message)
    except Exception as e:
        log_event("warn", "services.auto_link_failed", str(e)[:160])

    # ── Step 3.2: Praise gets a like, not a reply ────────────────────────
    # "Love this 😍" wants nothing from us, and answering it under a public
    # post is noise. But leaving it in silence is a wasted moment with someone
    # who just said something nice, so we like it instead.
    #
    # This is the gate that used to be a keyword heuristic at Step 2. It reads
    # the classifier's verdict now, so "obsessed, take my money" is answered
    # (praise AND order_request) while "🔥🔥🔥" is liked (praise alone).
    if channel.endswith('_comment') and _praise_only(classification, message):
        liked, like_err = _like_comment(channel, external_id)
        _mark_ineligible_for_ai(inbound_record)
        _record_no_reply(
            NO_REPLY_PRAISE, channel, user_id,
            conversation_id=(inbound_record.conversation_id
                             if inbound_record else None),
            detail=("liked the comment" if liked
                    else f"like unavailable ({like_err}) — left unanswered"))
        return AI_SUPPRESSED

    # ── Step 3.5: Handoff check — should this conversation go to a human? ──
    handoff = _check_handoff_for_inbound(message, intents, inbound_record, llm_handoff=_llm_handoff)
    if handoff:
        bridging = handoff["bridging_reply"]
        new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=bridging,
                                     comment_external_id=external_id)
        _save_message(user_id=user_id, channel=channel, content=bridging,
                      intent=None, direction="outbound",
                      external_id=new_ext_id)
        return bridging

    # ── Step 3.6: Automation rules (everything except stock triggers) ──────
    # First matching rule wins. Some actions answer the customer outright and
    # short-circuit the AI; others only set a directive the AI step reads.
    # Stock-based rules can't be judged yet — they need the Shopify fetch — so
    # they get their own pass at Step 4.6.
    rule_directives = {}
    for _rule, _action in _match_automation_actions(message, intents, channel):
        outcome = _run_automation_action(
            _rule, _action, channel=channel, user_id=user_id,
            external_id=external_id, inbound_record=inbound_record,
            message=message, intents=intents)
        rule_directives.update(outcome.get('directives') or {})
        reply_text = outcome.get('reply')
        if reply_text:
            new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=reply_text,
                                         comment_external_id=external_id)
            _save_message(user_id=user_id, channel=channel, content=reply_text,
                          intent=None, direction="outbound",
                          external_id=new_ext_id)
            log_event("info", "services.automation_reply",
                      f"Rule '{_rule.name}' answered [{channel}] {user_id}",
                      payload={
                          "user_external_id": user_id,
                          "channel": channel,
                          "intents": intents,
                          "rule_id": _rule.id,
                          "action": (_action or {}).get("type"),
                      },
                      conversation_id=(inbound_record.conversation_id if inbound_record else None))
            return reply_text

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

    # The customer is pointing at one of OUR posts — either commenting on it,
    # or forwarding it into a DM. Either way, fetch the post so the AI can see
    # what "how much is this?" refers to.
    #
    # This used to run for comments only, so a forwarded post in a DM arrived
    # as a bare picture with its caption thrown away.
    post_caption = None
    if media_id:
        from app.integrations.meta import instagram_media_for_ai
        media = instagram_media_for_ai(media_id)
        if media:
            if media.get("image_url") and not image_urls:
                image_urls = [media["image_url"]]
            post_caption = media.get("caption")

    # Stage 2 vision: when the customer sends a photo, identify the product in
    # it and use that as the search phrase. Strongest signal — it handles
    # "is this available?" + a photo, where the text names no product.
    vision_desc = None   # referenced later even when no photo was sent
    vision_attrs = {}    # garment type / colour, used to narrow the catalogue

    # A photo and its caption arrive as two separate webhooks. When this message
    # carries no image but points at something ("i want this, still available?"),
    # the photo it refers to is in the message just before it.
    if (not image_urls
            and inbound_record is not None
            and _is_referential(message)):
        recovered = _find_recent_image_urls(inbound_record.conversation_id)
        if recovered:
            image_urls = recovered
            log_event("info", "services.image_recovered",
                      f"Reusing the photo from the previous message for "
                      f"{str(user_id)[:24]}",
                      payload={"images": len(recovered)},
                      conversation_id=inbound_record.conversation_id)

    # Every product the customer photographed, not just the first.
    #
    # A real conversation on 18 August: four product screenshots back-to-back,
    # then "Hello are these available?". Vision used to read two images and
    # return one description, so the reply covered one item and said nothing
    # about the other three — which reads as a complete answer and is not one.
    vision_items = []
    if image_urls:
        from app.ai.generator import describe_products_in_images, MAX_VISION_IMAGES
        vision_items = describe_products_in_images(image_urls)
        vision_attrs = vision_items[0] if vision_items else {}
        vision_desc = vision_attrs.get("phrase")
        if vision_desc:
            product_keyword = vision_desc
            keyword_source = "image"
        # Say so when we could not look at everything, rather than answering
        # about a subset as though it were the whole.
        if len(image_urls) > MAX_VISION_IMAGES:
            context_data["images_not_examined"] = len(image_urls) - MAX_VISION_IMAGES

    # OUR OWN CAPTION beats guessing from a photo. When the customer references
    # a post we wrote, the caption usually names the garment outright ("Vivo
    # Lani Maxi Dress in Satin — restocked"), whereas vision can only describe
    # what it sees and hope the wording matches a product title. The caption was
    # being passed to the model as background but never used to SEARCH, which
    # is where it actually decides which product gets quoted.
    if post_caption and post_caption.strip():
        product_keyword = post_caption.strip()
        keyword_source = "post_caption"

    if product_keyword is None:
        from_text = None
        if product_intents.intersection(intents):
            from_text = _extract_product_keyword(message)

        # "Is this still available?" / "Can I get this?" carry a product intent
        # but name no product — they point at the photo sent a message earlier.
        #
        # This used to be an elif on ambient intents only, so a referential
        # stock question took the branch above and kept whatever the extractor
        # returned. That extractor has no failure mode: it strips stopwords and
        # hands back the remainder, or the raw message if nothing remains. So
        # "is this still available?" searched the catalogue for "still" and
        # "can I get this?" searched for the whole sentence — both matching an
        # arbitrary product, which the customer then got quoted. The vision
        # result from their photo was one row back in history the entire time.
        referential = _is_referential(message, from_text)

        if (referential or set(intents) <= ambient_intents) and inbound_record is not None:
            remembered = _find_recent_product_keyword(inbound_record.conversation_id)
            if remembered:
                # Keep any colour/size they just added: a photo followed by
                # "do you have this in red?" should search the remembered
                # garment IN RED, not every red item we stock.
                extra = [q for q in _qualifiers_in(message)
                         if q not in remembered.lower()]
                product_keyword = " ".join([remembered] + extra) if extra else remembered
                keyword_source = "history+qualifier" if extra else "history"

        # Nothing remembered — fall back to the text, but only if it is worth
        # searching for. A weak keyword returns arbitrary products, which is
        # worse than returning none and letting the AI ask what they mean.
        if product_keyword is None and from_text is not None:
            if not _message_names_a_product(message):
                log_event("info", "services.keyword_unresolved",
                          f"referential message with no usable keyword: {message[:80]!r}",
                          conversation_id=getattr(inbound_record, "conversation_id", None))
            else:
                product_keyword = from_text
                keyword_source = "current_message"

    if product_keyword:
        # Multi-term search: extract additional terms from the current message
        # so "black dress" matches the Black Wrap Dress better than just any dress.
        # On history-source follows, we only have the carried keyword.
        if keyword_source == "current_message":
            search_terms = _extract_product_keywords(message)
        elif keyword_source == "image":
            # Use BOTH the photo (vision keywords) AND the caption the customer
            # sent with it ("...in orange"), so the search reflects the style in
            # the image and the qualifier in their text.
            search_terms = _extract_product_keywords(product_keyword)
            caption = (message or "").strip()
            if caption and caption != "[Sent a photo]":
                search_terms = search_terms + [
                    t for t in _extract_product_keywords(caption) if t not in search_terms
                ]
        elif keyword_source == "post_caption":
            # Our own caption, plus anything the customer typed alongside it
            # ("do you have this in blue?"). Vision terms come last as backup —
            # if the caption is decorative rather than descriptive, the photo
            # still gets a say.
            search_terms = _extract_product_keywords(product_keyword)
            said = (message or "").strip()
            if said and said != "[Sent a photo]":
                search_terms += [t for t in _extract_product_keywords(said)
                                 if t not in search_terms]
            if vision_desc:
                search_terms += [t for t in _extract_product_keywords(vision_desc)
                                 if t not in search_terms]
        else:
            search_terms = [product_keyword]

        # Image-sourced matches hedge by default — visually similar items are
        # easy to confuse. A successful vision re-rank below clears this.
        context_data['image_only_match'] = (keyword_source == "image")

        # For image matches, pull a WIDER shortlist and let vision pick the real
        # one. Keyword search can't tell a wrap-front palazzo from a plain
        # wide-leg; side-by-side photos can. A caption-sourced search gets the
        # same treatment when we have a picture to compare against.
        _img_verify = (keyword_source in ("image", "post_caption") and bool(image_urls))

        # Narrow by garment TYPE first, then rank — instead of ranking the whole
        # catalogue by keyword overlap and hoping.
        #
        # "colourful dress with fringe" scores poorly against titles a
        # merchandiser wrote, so with 7,000+ products the right item routinely
        # missed the top 12 and vision never got to look at it. The customer
        # then got a wrong product, or an honest "I can't place it" that made
        # the assistant look useless. Filtering on the noun — dress, trousers,
        # shoes — discards everything that is not even the right kind of thing
        # before ranking begins, which is a far better use of the limit.
        #
        # The pool handed to vision is also much wider now (12 -> 40): comparing
        # photos is the step that actually decides, and it was being starved.
        gtype = (vision_attrs.get("type") or "").strip()
        matches = []
        if _img_verify and gtype:
            typed_terms = [gtype] + [t for t in search_terms if t != gtype]
            matches = search_products(typed_terms, limit=40, must_match=gtype)
            if matches:
                log_event("info", "services.image_search_narrowed",
                          f"Narrowed to {len(matches)} '{gtype}' candidates before vision",
                          payload={"type": gtype,
                                   "colour": vision_attrs.get("colour"),
                                   "candidates": len(matches)})

        # No type, or nothing of that type in stock — fall back to plain ranking.
        if not matches:
            matches = search_products(search_terms, limit=(40 if _img_verify else 3))

        if _img_verify and matches:
            from app.ai.generator import verify_product_match
            verdict = verify_product_match(image_urls, matches)
            if verdict is not None:
                idx = verdict.get("index")
                if idx is None:
                    # Nothing in the catalogue is the item in the photo. Say so
                    # — far better than quoting a confident wrong price.
                    context_data['image_match_failed'] = True
                    matches = []

                    # Hand it to a person rather than interrogating the customer.
                    # We looked at their photo against the catalogue and could
                    # not place it; a colleague who knows the collection will
                    # recognise it in seconds. Asking the customer to describe
                    # or go and find our own product puts our job onto them.
                    try:
                        if inbound_record and inbound_record.conversation_id:
                            from app.handoff import _trigger
                            from app.models import Conversation as _C
                            _conv = _C.query.get(inbound_record.conversation_id)
                            if _conv:
                                _trigger(_conv, reason="image_unmatched",
                                         detail="Customer sent a photo we could not "
                                                "match to any product")
                    except Exception as e:
                        # An escalation failure must not cost the customer a
                        # reply — the AI still answers, just without a human.
                        log_event("warning", "services.image_escalation_failed", str(e)[:200])
                else:
                    if verdict.get("confidence") == "high":
                        # Vision confirmed this exact item. Pass ONLY it — leaving
                        # the runners-up in context lets the model talk about a
                        # different product than the one that was verified.
                        matches = [matches[idx]]
                        # `image_match_verified` is still recorded, because it
                        # is the measurement we need: how often vision said
                        # "high" and was right is the entire business case for
                        # replacing keyword search with embeddings.
                        context_data['image_match_verified'] = True
                        # But it no longer clears image_only_match, so a "high
                        # confidence" verdict no longer buys the AI permission
                        # to answer. Confidence here is the model's opinion of
                        # its own guess, formed by comparing the photo against a
                        # shortlist that keyword search may never have put the
                        # right product into. It is confident about the best of
                        # the options it was shown — which is a different claim
                        # from "this is the item", and indistinguishable from it
                        # in the output.
                        #
                        # Every image-only match now goes to a person.
                    else:
                        matches = [matches[idx]] + [m for i, m in enumerate(matches) if i != idx]
            matches = matches[:3]

        # ── A photo we could not positively identify goes to a person ───────
        # `image_only_match` survives to here only when the customer sent a
        # picture, named nothing, and vision did NOT confirm the top candidate.
        # The generator's answer to that was to hedge — no price, no link, no
        # asserting the name. Honest, and still a guess dressed up as help, on
        # exactly the case we know it gets wrong: a wrap-front palazzo and a
        # plain one read identically to keyword search, so the shortlist vision
        # is choosing from may not contain the right item at all.
        #
        # The neighbouring branch already escalates when NOTHING matched. This
        # closes the more dangerous half — something matched, and we cannot
        # tell if it is the right something. Until image embeddings replace the
        # keyword step, a person identifies the garment.
        if matches and context_data.get('image_only_match'):
            _conv_id = getattr(inbound_record, 'conversation_id', None)
            _bridge = None
            try:
                from app.models import Conversation
                from app.handoff import _trigger
                _conv = Conversation.query.get(_conv_id) if _conv_id else None
                if _conv is not None:
                    _bridge = (_trigger(_conv, reason="image_unconfirmed",
                                        detail="Customer sent a photo we could not "
                                               "confidently identify") or {}
                               ).get('bridging_reply')
            except Exception as e:
                log_event("warning", "services.image_unconfirmed_escalation_failed",
                          str(e)[:200], conversation_id=_conv_id)

            if _bridge:
                _ext = _dispatch_reply(channel=channel, user_id=user_id,
                                       reply=_bridge, comment_external_id=external_id)
                _save_message(user_id=user_id, channel=channel, content=_bridge,
                              intent=None, direction="outbound", external_id=_ext)
            _record_no_reply(
                NO_REPLY_IMAGE_UNCONFIRMED, channel, user_id,
                conversation_id=_conv_id,
                detail=(f"best guess was '{(matches[0] or {}).get('name')}' — "
                        f"{'handed to an agent' if _bridge else 'already with an agent'}"))
            return _bridge or AI_SUPPRESSED

        # More than one garment in the photos → look each one up and answer about
        # all of them. `products` is already the list Claude reads, so the reply
        # side needs nothing new; what was missing was ever putting more than one
        # product's matches into it.
        if len(vision_items) > 1:
            extra, seen_ids = [], {(m or {}).get("id") for m in (matches or [])}
            for item in vision_items[1:]:
                phrase = item.get("phrase")
                if not phrase:
                    continue
                try:
                    found = search_products(phrase, limit=2) or []
                except Exception as e:
                    log_event("warn", "services.multi_product_lookup_failed", str(e)[:160])
                    continue
                for m in found:
                    if m and m.get("id") not in seen_ids:
                        seen_ids.add(m.get("id"))
                        extra.append(m)
            if extra:
                matches = (matches or []) + extra
                context_data["multi_product"] = len(vision_items)
                log_event("info", "services.multi_product",
                          f"Customer sent {len(vision_items)} products — answering about "
                          f"{len(matches)} matched items",
                          payload={"asked": [i.get("phrase") for i in vision_items]})

        if matches:
            context_data["products"] = matches              # full list for Claude
            context_data["product"]  = matches[0]           # single best (backwards compat)

            # Attach the size chart for whoever makes this product.
            #
            # Not gated on a "sizing" intent, deliberately. The customer who
            # prompted this typed "can they fit someone with a burst 43 in
            # size?" — a keyword gate looking for "bust" misses it, and the
            # classifier has no sizing intent to key on. The chart is seven
            # short lines; attaching it whenever a product is identified costs
            # very little and means a fit question is always answerable.
            try:
                from app.settings import format_size_chart_for_prompt
                vendors = {(m or {}).get("vendor") for m in matches if (m or {}).get("vendor")}
                primary_vendor = (matches[0] or {}).get("vendor")
                chart = format_size_chart_for_prompt(primary_vendor)
                if chart:
                    context_data["size_chart"] = chart
                    # Different brands size differently, so one chart cannot
                    # cover a reply spanning several of them. Say which it
                    # applies to rather than letting it read as universal.
                    if len(vendors) > 1:
                        context_data["size_chart_vendors"] = sorted(v for v in vendors if v)
            except Exception as e:
                log_event("warn", "services.size_chart_failed", str(e)[:160])
            # A SECOND ranked list that still contains sold-out products.
            #
            # `products` above deliberately excludes them so the AI can never
            # offer something unbuyable. But the shopify_stock automation rules
            # exist precisely to fire when the best match IS sold out — reading
            # them off the filtered list would mean they could never match
            # again, and an "out of stock" rule would go quietly dead.
            # Recommendations and stock questions are different questions.
            context_data["_stock_candidates"] = search_products(
                search_terms, limit=3, include_sold_out=True) or matches

            # Answer "do you have X" from the best AVAILABLE match, not from
            # whichever row happens to rank first.
            #
            # This read matches[0] outright. A customer asked "do you have
            # fuschia dress"; the top-ranked row was a sold-out one, the
            # "Out of Stock" rule fired, and she was told "This item is
            # currently out of stock" — while 14 of the 16 fuschia dresses in
            # the catalogue were in stock, one of them with 56 units.
            #
            # Ranking is by text relevance and knows nothing about inventory,
            # so for anything broader than one exact product — a colour, a
            # style, a category — matches[0] is effectively arbitrary. When the
            # customer names a colour, ANY dress in that colour answers the
            # question, and "out of stock" is only true when every match is.
            #
            # The sold-out row stays the subject when nothing is available, so
            # the out-of-stock rules still fire on a genuinely sold-out product
            # and can still name it.
            _stock_pool = context_data["_stock_candidates"] or matches
            _available = [p for p in _stock_pool if (p.get("stock_quantity") or 0) > 0]
            _stock_pick = _available[0] if _available else _stock_pool[0]
            if _available and _stock_pick is not _stock_pool[0]:
                log_event("info", "services.stock_pick_available",
                          f"Top match '{_stock_pool[0].get('name')}' is sold out; "
                          f"answering from '{_stock_pick.get('name')}' "
                          f"({len(_available)} of {len(_stock_pool)} matches in stock)",
                          conversation_id=(inbound_record.conversation_id
                                           if inbound_record else None))
            context_data["stock"]    = {
                "product_name": _stock_pick.get("name"),
                "quantity":     _stock_pick.get("stock_quantity", 0),
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
            
        elif not context_data.get('image_match_failed'):
            # Cache miss — the product may be new or newly-published since the
            # last 3-hourly sync. Try a live Shopify lookup, write hits back
            # into the cache, then re-run the cache search so ranking + shape
            # are identical to a normal hit.
            from app.integrations.shopify import live_search_products
            live = live_search_products(search_terms, window_days=1, max_pages=2)
            if live:
                _writeback_products(live)
                matches = search_products(search_terms, limit=3)

            if matches:
                context_data["products"] = matches
                context_data["product"]  = matches[0]
                context_data["stock"]    = {
                    "product_name": matches[0].get("name"),
                    "quantity":     matches[0].get("stock_quantity", 0),
                    "unit":         "pcs",
                }
                _patch_inbound_product_keyword(inbound_record, product_keyword)
                log_event("info", "services.shopify_lookup_live",
                          f"Live fallback found {len(matches)} matches for '{product_keyword}'",
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
                          f"No cache or live matches for '{product_keyword}' (source: {keyword_source})",
                          payload={
                              "user_external_id": user_id,
                              "channel": channel,
                              "product_keyword": product_keyword,
                              "keyword_source": keyword_source,
                          },
                          conversation_id=(inbound_record.conversation_id if inbound_record else None))

    # Returns, exchanges and refunds. Intent-driven like delivery, not keyword
    # matched - "it does not fit, can I swap it" contains none of the obvious
    # words and is exactly the message that must reach the policy.
    if "return_request" in intents:
        context_data["returns_asked"] = True

    if "delivery_inquiry" in intents:
        context_data["delivery_asked"] = True
        context_data["delivery_location"] = _extract_location(message)

    # ── Order-status flow (live, never cached) ─────────────────────────────
    # Fires when the message asks about an order, OR when it's a follow-up
    # (contains an email) to a recent order-status ask.
    _os_email = _extract_email(message)
    _os_flow = ("order_status" in intents) or (
        _os_email is not None
        and inbound_record is not None
        and _recent_intent_was_order_status(inbound_record.conversation_id)
    )
    if _os_flow:
        if _os_email:
            context_data["order_status"] = _lookup_order_status(
                _os_email, _extract_name_tokens(message)
            )
        else:
            context_data["order_status_asked"] = True   # ask for full name + email

    # Real-time stock refresh: if customer is asking about stock, verify
    # inventory live from Shopify for the products we're about to recommend.
    products_in_context = context_data.get('products') or []
    if 'stock_inquiry' in intents and products_in_context:
        from app.integrations.shopify import refresh_stock_for_products
        product_ids = [p.get('shopify_id') for p in products_in_context if p.get('shopify_id')]
        fresh = refresh_stock_for_products(product_ids)
        if fresh:
            for p in products_in_context:
                spid = p.get('shopify_id')
                if spid and spid in fresh:
                    p['stock_quantity'] = fresh[spid]['stock_quantity']
                    p['inventory_tracked'] = fresh[spid]['inventory_tracked']
                    p['variants_detail'] = fresh[spid]['variants_detail']
            context_data['products'] = products_in_context
            log_event("info", "services.live_stock_used",
                      f"Used real-time stock for {len(fresh)} products",
                      conversation_id=(inbound_record.conversation_id if inbound_record else None))

    # ── Step 4.6: Stock-triggered automation rules ─────────────────────────
    # Deliberately placed AFTER the live stock refresh above, so an
    # "out of stock" rule is judged on the same number the customer would see
    # on the site rather than whatever the last nightly sync cached.
    for _srule, _saction in _match_automation_actions(
            message, intents, channel,
            products=(context_data.get('_stock_candidates')
                      or context_data.get('products') or []), stock_pass=True):
        s_outcome = _run_automation_action(
            _srule, _saction, channel=channel, user_id=user_id,
            external_id=external_id, inbound_record=inbound_record,
            message=message, intents=intents)
        rule_directives.update(s_outcome.get('directives') or {})
        s_reply = s_outcome.get('reply')
        if s_reply:
            # An out-of-stock rule usually wants to name alternatives, and by
            # this point we have them — so append the ones we found rather than
            # sending a bare "sorry, sold out".
            if (_saction or {}).get('suggest_similar'):
                alts = [p.get('name') for p in (context_data.get('products') or [])[1:3]
                        if p.get('name')]
                if alts:
                    s_reply = f"{s_reply}\n\nYou might also like: {', '.join(alts)}."
            new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=s_reply,
                                         comment_external_id=external_id)
            _save_message(user_id=user_id, channel=channel, content=s_reply,
                          intent=None, direction="outbound",
                          external_id=new_ext_id)
            log_event("info", "services.automation_reply",
                      f"Stock rule '{_srule.name}' answered [{channel}] {user_id}",
                      payload={
                          "user_external_id": user_id,
                          "channel": channel,
                          "rule_id": _srule.id,
                          "action": (_saction or {}).get("type"),
                          "stock_quantity": (context_data.get('products') or [{}])[0].get('stock_quantity'),
                      },
                      conversation_id=(inbound_record.conversation_id if inbound_record else None))
            return s_reply

    # Routing instruction, not context — pull it out before the rest go to the
    # generator, which would otherwise see a stray dict among its flags.
    dm_handoff = rule_directives.pop('_dm_handoff', None)

    # The generator is about to be told it is writing a public comment, because
    # that is the channel the message arrived on — so it writes like one: short,
    # answer only what was asked. But this answer is going into a DM, underneath
    # a public promise that it contains "all the details". A three-word size
    # list does not honour that.
    #
    # This flag is the only thing that tells the generator where its words will
    # actually land. Without it we advertise a full briefing and deliver a
    # comment.
    if dm_handoff:
        context_data['deliver_as_dm'] = True

    # Hand any rule-set directives to the AI step.
    if rule_directives:
        context_data.update(rule_directives)

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

    if post_caption:
        context_data['post_caption'] = post_caption

    ai_result = generate_reply(message, intents, context_data, channel, history=history, image_urls=image_urls)
    reply           = ai_result['reply']
    ai_elapsed_ms   = ai_result['elapsed_ms']
    ai_tokens_used  = ai_result['tokens_used']
    ai_model        = ai_result['model']
    utm_token       = ai_result.get('utm_token')
    product_url     = ai_result.get('product_url')

    # The customer may have sent another message WHILE the AI was generating
    # (vision + catalog search takes seconds). The Step 2.5 check ran before
    # that. Re-check now — if a newer inbound landed, drop this reply and let
    # the newer event answer the whole burst, otherwise we double-answer the
    # same photo with two different guesses.
    if inbound_record is not None and not channel.endswith('_comment'):
        if _has_newer_inbound(inbound_record) or _burst_already_answered(inbound_record):
            if placeholder is not None:
                try:
                    from app import db
                    db.session.delete(placeholder)
                    db.session.commit()
                except Exception:
                    try:
                        from app import db
                        db.session.rollback()
                    except Exception:
                        pass
            _record_no_reply(NO_REPLY_SUPERSEDED, channel, user_id,
                             conversation_id=inbound_record.conversation_id,
                             detail="newer inbound arrived during AI generation")
            return AI_SUPPRESSED

    # ── Step 5c: The AI could not answer — give the customer a person ──────
    # Claude refused, timed out or ran out of credit, so there is no reply to
    # send. We used to send a template built from cached product data, which
    # read like a real answer and was not one: no price, no delivery, no link,
    # and nothing in the inbox marking it as canned.
    #
    # This runs AFTER the superseded check above on purpose. A customer who has
    # already sent a newer message does not need an agent summoned for a turn we
    # are about to discard anyway.
    if ai_result.get('escalate'):
        if placeholder is not None:
            try:
                from app import db
                db.session.delete(placeholder)
                db.session.commit()
            except Exception:
                try:
                    from app import db
                    db.session.rollback()
                except Exception:
                    pass

        bridging = None
        try:
            from app.handoff import escalate_ai_unavailable
            handoff_result = escalate_ai_unavailable(
                conversation_id, failure_reason=ai_result.get('failure_reason'))
            bridging = (handoff_result or {}).get('bridging_reply')
        except Exception as e:
            log_event("error", "services.ai_unavailable_escalation_failed",
                      f"Could not escalate after AI failure: {e}",
                      conversation_id=conversation_id)

        # No bridging line means the thread was already with an agent, so the
        # customer is being looked after by a person right now and does not
        # need to be told twice that someone is coming.
        if bridging:
            bridge_ext_id = _dispatch_reply(channel=channel, user_id=user_id,
                                            reply=bridging,
                                            comment_external_id=external_id)
            _save_message(user_id=user_id, channel=channel, content=bridging,
                          intent=None, direction="outbound",
                          external_id=bridge_ext_id)

        _record_no_reply(
            NO_REPLY_AI_UNAVAILABLE, channel, user_id,
            conversation_id=conversation_id,
            detail=(f"{ai_result.get('failure_reason') or 'generation_failed'}"
                    f" — {'handed to an agent' if bridging else 'already with an agent'}"))
        return bridging or AI_SUPPRESSED

    # ── Step 6: Send reply to the customer IMMEDIATELY (no delay to IG) ────
    # A trigger_dm_flow rule matched back at Step 3.6, so the answer we just
    # generated belongs in a DM rather than under the post. The DM goes first:
    # the public teaser says a DM was sent, and we will not post that claim
    # until it is true. Meta refuses this more often than you would expect —
    # private replies work once per comment and only within 7 days of it — so
    # the failure path answers publicly instead of promising nothing.
    if dm_handoff:
        from app.integrations.meta import send_instagram_private_reply
        dm = send_instagram_private_reply(dm_handoff['comment_id'], reply)
        if dm:
            _save_message(user_id=user_id, channel="instagram_dm",
                          content=reply, intent=None,
                          direction="outbound", external_id=dm.get("id"))
            teaser = dm_handoff['public_reply']
            teaser_ext_id = _dispatch_reply(channel=channel, user_id=user_id,
                                            reply=teaser,
                                            comment_external_id=external_id)
            _save_message(user_id=user_id, channel=channel, content=teaser,
                          intent=None, direction="outbound",
                          external_id=teaser_ext_id)
            log_event("info", "services.automation_reply",
                      f"Rule '{dm_handoff['rule_name']}' moved the answer to a DM",
                      payload={"user_external_id": user_id, "channel": channel,
                               "comment_id": dm_handoff['comment_id'],
                               "action": "trigger_dm_flow"},
                      conversation_id=conversation_id)
            if placeholder is not None:
                try:
                    from app import db
                    db.session.delete(placeholder)
                    db.session.commit()
                except Exception:
                    try:
                        from app import db
                        db.session.rollback()
                    except Exception:
                        pass
            return reply

        # Fall through and answer under the post. The customer still gets their
        # answer; they just get it where they asked. The configured fallback
        # text is only used when it exists — an empty one must not blank out a
        # perfectly good reply.
        reply = dm_handoff.get('public_reply_fallback') or reply
        log_event("warning", "services.automation_reply",
                  f"Rule '{dm_handoff['rule_name']}': Meta refused the DM — "
                  f"answering under the post instead",
                  payload={"user_external_id": user_id, "channel": channel,
                           "comment_id": dm_handoff['comment_id'],
                           "action": "trigger_dm_flow"},
                  conversation_id=conversation_id)

    new_ext_id = _dispatch_reply(channel=channel, user_id=user_id, reply=reply,
                                 comment_external_id=external_id, product_url=product_url)

    # A None here means the send failed (or the channel has no dispatcher yet).
    # This used to log services.ai_reply unconditionally, so a reply that never
    # left the building was recorded — and counted — as answered. The row is
    # still persisted below so an agent can resend by hand; what changes is
    # that we no longer claim the customer heard from us.
    if new_ext_id is None:
        _record_no_reply(NO_REPLY_DISPATCH_FAILED, channel, user_id,
                         conversation_id=conversation_id,
                         detail=f"reply generated but not delivered via {channel}")
    else:
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

    # ── Step 7: Finalize the outbound row IMMEDIATELY ──────────────────────
    # No delay here. While the row sits as 'ai_pending' the coalescer can't
    # see that we just replied, so anything arriving in that window gets
    # answered a second time over the same content.
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

def _channel_allows_ai(channel: str) -> bool:
    """
    Is the AI permitted to answer on this channel at all?

    One definition, used by BOTH the live gate and the analytics eligibility
    snapshot. Those were two hand-written copies of the same rule, with a
    comment in one telling the reader to keep it in step with the other — the
    arrangement that let the inbox filters and the customer totals drift apart
    elsewhere in this codebase.

    A channel with no row is treated as ALLOWED, which is the historical
    behaviour and is kept deliberately: rows are created when a channel is
    configured, and a webhook arriving for a channel we have never configured
    should not be silently swallowed. It is logged instead, so "no row" is
    visible rather than an invisible default.
    """
    try:
        from app.models import Channel
        ch = Channel.query.filter_by(channel=channel).first()
        if ch is None:
            log_event("warn", "services.channel_not_configured",
                      f"No channel row for {channel} — treating the AI as allowed",
                      payload={"channel": channel})
            return True
        return bool(ch.enabled)
    except Exception as e:
        # Unreadable configuration means the AI stays quiet, matching the way
        # the master switch fails closed.
        log_event("error", "services.channel_lookup_failed", str(e),
                  payload={"channel": channel})
        return False


def _route_to_humans_switch_off(conversation_id):
    """
    Hand a conversation to the human queue because the AI master switch is off.

    Mirrors what settings.ai_handover(action='queue') does to the existing
    backlog, so a conversation that arrives during a pause ends up in the same
    place as one that was already open when the switch was flipped. Without
    that symmetry the handover only ever rescues a snapshot and everything
    arriving afterwards leaks.

    ai_auto_paused_at is the reversibility marker: 'restore' hands back exactly
    the set carrying it when the AI comes back on. Claiming or replying clears
    it, so a thread a human has picked up is never taken back from them.

    Best-effort. A customer's message must still be recorded and visible even
    if this bookkeeping fails, so nothing here is allowed to raise.
    """
    if not conversation_id:
        return
    try:
        from app import db
        from app.models import Conversation
        conv = Conversation.query.get(conversation_id)
        if conv is None or conv.status == 'resolved':
            return
        # Already human-held? Leave it exactly as it is.
        if conv.assigned_to is not None or conv.status == 'human_override':
            return

        now = datetime.utcnow()
        conv.ai_enabled = False
        conv.ai_auto_paused_at = now
        if conv.ai_disabled_at is None:
            conv.ai_disabled_at = now
        conv.status = 'human_override'
        db.session.commit()
        log_event("info", "services.routed_to_humans_switch_off",
                  f"AI master switch off — conversation {conv.id} queued for agents",
                  conversation_id=conv.id)
    except Exception as e:
        db.session.rollback()
        log_event("error", "services.route_to_humans_failed", str(e))


def _ai_should_respond(channel: str, user_id: str, message: str | None = None):
    """
    Decide whether the AI answers this message.

    Returns (should_respond, reason). `reason` is None when the answer is yes,
    and otherwise one of the NO_REPLY_* constants — it is what makes an
    unanswered conversation explainable after the fact. This used to return a
    bare bool, and the caller re-derived a coarse two-value reason from the
    channel name, which collapsed five distinct causes into "not_a_question"
    or "channel_disabled_or_handed_over".

    Says yes iff:
      - the global master switch is on, AND
      - the channel is enabled (or no Channel row exists — fail open), AND
      - the conversation has ai_enabled (or no conversation exists yet — fail open), AND
      - for *_comment channels: the message looks like a question

    The question-gate exists because comments are PUBLIC. We don't want
    the bot replying to "love this!" or pure emoji praise on a post.
    DMs reply to everything (private 1:1, expected behavior).
    """
    # Global kill switch. Deliberately FAILS CLOSED: if the setting can't be
    # read we stay silent rather than risk auto-replying to real customers
    # while the platform is meant to be manual-only.
    try:
        from app.settings import get_section
        if not get_section("ai").get("enabled", True):
            return False, NO_REPLY_MASTER_SWITCH_OFF
    except Exception as e:
        log_event("error", "services.ai_switch_unreadable",
                  f"Could not read AI master switch, staying silent: {e}")
        return False, NO_REPLY_SETTINGS_UNREADABLE

    def _comment_gate(is_q_input):
        """
        Comments used to have to LOOK like a question to get past here, judged
        by is_question() — a list of question words and stock phrases. It threw
        away real customers for phrasing: "need this in a 38" and "obsessed,
        take my money" contain no question word and asked for plenty.

        The judgement moved to Step 3.2, one step later, where the classifier
        has actually read the message. The trade is one Haiku call per public
        comment, including the ones we end up not answering. That is the price
        of deciding on meaning instead of vocabulary, and it is small.

        is_question() has not been deleted — Step 3.2 still falls back to it if
        the classifier is unavailable, because a degraded classifier must not
        silently turn into "reply to everything" on a public post.
        """
        return True, None

    try:
        from app.models import Channel, Conversation, User

        if not _channel_allows_ai(channel):
            return False, NO_REPLY_CHANNEL_DISABLED

        customer = User.query.filter_by(external_id=user_id, channel=channel).first()
        if customer is None:
            # Brand new customer — apply the comment gate but still allow DMs
            return _comment_gate(message)

        conv = (
            Conversation.query
            .filter_by(user_id=customer.id, channel=channel)
            .order_by(Conversation.id.desc())
            .first()
        )
        if conv is None:
            return _comment_gate(message)

        if not bool(conv.ai_enabled):
            return False, NO_REPLY_CONVERSATION_AI_OFF

        return _comment_gate(message)

    except Exception as e:
        # Fails OPEN here on purpose: a DB hiccup shouldn't silence the AI for
        # a customer who is waiting. The gate above fails closed because a
        # deliberate kill switch is a stronger signal than a transient error.
        log_event("error", "services._ai_should_respond", str(e))
        return True, None

# ─────────────────────────────────────────────
# Internal helpers (extraction)
# ─────────────────────────────────────────────

MAX_ORDER_STATUS_ORDERS = 1  # how many recent orders to summarise

_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
_NAME_FILLER = {
    'my', 'name', 'is', 'im', "i'm", 'the', 'email', 'mail', 'e-mail',
    'and', 'order', 'number', 'its', "it's", 'here', 'hi', 'hello', 'hey',
    'please', 'thanks', 'thank', 'you', 'for', 'an', 'a', 'this',
}


def _extract_email(message: str):
    """First email address in the message, lowercased, or None."""
    if not message:
        return None
    m = _EMAIL_RE.search(message)
    return m.group(0).strip().lower() if m else None


def _extract_name_tokens(message: str) -> list[str]:
    """
    Candidate name words: alphabetic tokens minus the email and common filler.
    Order-independent — used only to check whether any token matches the
    Shopify customer's first or last name.
    """
    if not message:
        return []
    tokens = []
    for raw in re.split(r'[\s,;:]+', message):
        w = raw.strip("?.!,()[]'\"").strip()
        if not w or '@' in w:
            continue
        if not w.replace('-', '').replace("'", '').isalpha():
            continue
        if len(w) < 2 or w.lower() in _NAME_FILLER:
            continue
        tokens.append(w)
    return tokens


def _recent_intent_was_order_status(conversation_id: int, max_lookback: int = 5) -> bool:
    """
    True if a recent inbound message carried the order_status intent — lets a
    bare "Jane, jane@x.com" follow-up be recognised as the continuation of an
    order-status flow. Intents are stored pipe-joined on Message.intent.
    """
    if not conversation_id:
        return False
    try:
        from app.models import Message
        rows = (Message.query
                .filter_by(conversation_id=conversation_id, direction='inbound')
                .order_by(Message.created_at.desc())
                .limit(max_lookback)
                .all())
        return any(m.intent and 'order_status' in m.intent for m in rows)
    except Exception as e:
        log_event("warn", "services._recent_intent_was_order_status", str(e))
        return False


def _lookup_order_status(email: str, name_tokens: list[str]) -> dict:
    """
    Live order-status lookup (never cached). Returns one of:
      {'state': 'no_account'}
      {'state': 'name_mismatch'}
      {'state': 'no_orders', 'customer_name': str}
      {'state': 'found',     'customer_name': str, 'orders': [...]}
    Name check is forgiving: first OR last name must appear among the tokens.
    """
    from app.integrations.shopify import find_customer_by_email, get_customer_orders

    customer = find_customer_by_email(email)
    if not customer:
        return {'state': 'no_account'}

    first = (customer.get('first_name') or '').strip().lower()
    last  = (customer.get('last_name')  or '').strip().lower()
    provided = {t.lower() for t in (name_tokens or [])}
    name_ok = bool(provided) and ((first and first in provided) or (last and last in provided))
    if not name_ok:
        return {'state': 'name_mismatch'}

    full_name = ' '.join(p for p in (customer.get('first_name'), customer.get('last_name')) if p).strip()
    orders = get_customer_orders(customer['shopify_id'])
    if not orders:
        return {'state': 'no_orders', 'customer_name': full_name}

    orders_sorted = sorted(orders, key=lambda o: o.get('order_date') or '', reverse=True)
    return {
        'state': 'found',
        'customer_name': full_name,
        'orders': orders_sorted[:MAX_ORDER_STATUS_ORDERS],
    }

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
        # Marketing filler, mostly from our own post captions. "restocked"
        # scored above the garment's actual name under length-ordering.
        "new", "sale", "shop", "now", "out", "link", "bio", "order", "get",
        "just", "back", "only", "left", "swipe", "tap", "click", "here",
        "dm", "price", "ksh", "kes", "off", "today", "limited",
    }
    words = [w.strip("?.,!\"'()[]—–-") for w in message.lower().split()]
    candidates = [w for w in words if w and w not in stopwords and len(w) >= 3]
    # Dedupe while preserving order
    seen = set()
    unique = []
    for w in candidates:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    if len(unique) <= max_terms:
        return unique

    # More candidates than slots, so the choice matters. Rank by how RARE each
    # word is among product names rather than by length: length is a terrible
    # proxy for distinctiveness — in "Vivo Lani Maxi Dress In Satin, restocked"
    # it picked "restocked" (9 chars, matches 0 products) over "lani" (4 chars,
    # matches 33). Rarity puts the words that actually identify a garment first.
    # One query for all terms; only runs when we have to discard something.
    try:
        from app import db          # not imported at module level in this file
        from app.models import ProductCache
        from sqlalchemy import func, case
        cols = [func.count(case((ProductCache.name.ilike(f"%{w}%"), 1))) for w in unique]
        counts = list(db.session.query(*cols).one())
        scored = list(zip(unique, counts))
        # A word in no product name at all is noise, not a rare gem — drop it,
        # unless that would leave us with nothing to search on.
        present = [(w, n) for w, n in scored if n > 0]
        if present:
            present.sort(key=lambda wn: wn[1])          # rarest first
            return [w for w, _ in present[:max_terms]]
    except Exception as e:
        log_event("warn", "services.keyword_rarity_failed", str(e)[:160])

    unique.sort(key=len, reverse=True)                  # fallback: old behaviour
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

def _product_card_for_url(product_url: str | None) -> dict | None:
    """Resolve a storefront product URL to card fields (title/subtitle/image/url), or None."""
    if not product_url:
        return None
    try:
        after = product_url.split('/products/', 1)
        if len(after) < 2:
            return None
        handle = after[1].split('?', 1)[0].strip('/').strip()
        if not handle:
            return None
        from app.models import ProductCache
        row = ProductCache.query.filter_by(handle=handle).first()
        if not row or not row.images:
            return None
        first = row.images[0]
        image = first if isinstance(first, str) and first.startswith('http') else None
        if not image:
            return None

        subtitle = None
        p = row.price
        if p is not None:
            if isinstance(p, str):
                subtitle = p.strip() or None                 # already formatted e.g. "KES 2500"
            else:
                try:
                    subtitle = f"KES {int(round(float(p))):,}"
                except Exception:
                    subtitle = None

        return {"title": row.name or "Shop Zetu", "subtitle": subtitle, "image": image, "url": product_url}
    except Exception as e:
        log_event("warn", "services.product_card_lookup_failed", str(e)[:200])
    return None

def _account_for(user_id: str, channel: str) -> str | None:
    """
    The business account id that owns this customer's conversation — stamped
    from the webhook's entry[].id when the message arrived.

    None when unknown (older rows predating the column), in which case the
    credential lookup falls back to the single active connection, preserving
    the previous single-account behaviour.
    """
    try:
        from app.models import User, Conversation
        u = User.query.filter_by(external_id=user_id, channel=channel).first()
        if not u:
            return None
        conv = (Conversation.query
                .filter_by(user_id=u.id, channel=channel)
                .order_by(Conversation.updated_at.desc())
                .first())
        return conv.business_account_id if conv else None
    except Exception:
        return None


def stamp_conversation_account(user_id: str, channel: str, account_id: str | None) -> None:
    """
    Record which of our accounts received a message, so replies later go back
    out from the same one. Idempotent and best-effort — never raises into the
    webhook path.
    """
    if not account_id:
        return
    try:
        from app import db
        from app.models import User, Conversation
        u = User.query.filter_by(external_id=user_id, channel=channel).first()
        if not u:
            return
        conv = (Conversation.query
                .filter_by(user_id=u.id, channel=channel)
                .order_by(Conversation.updated_at.desc())
                .first())
        if conv and conv.business_account_id != str(account_id):
            conv.business_account_id = str(account_id)
            db.session.commit()
    except Exception as e:
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        log_event("warn", "services.stamp_account_failed", str(e))


# Channels _dispatch_reply can actually deliver on. Everything else below is a
# stub that logs and returns None — the reply is stored, the customer never sees
# it. That is the MVP scope: Instagram DMs and Instagram comments.
#
# Declared here, beside the implementation it describes, and imported by
# app/channels.py so a channel we cannot answer on cannot be switched on. A
# channel being enabled means inbound is accepted, and accepting messages we are
# structurally unable to reply to is worse than not listening at all.
SENDABLE_CHANNELS = frozenset({'instagram_dm', 'instagram_comment'})


def _dispatch_reply(channel: str, user_id: str, reply: str, product_url: str | None = None, **kwargs) -> str | None:
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

    # Shadow mode.
    #
    # Everything upstream has already happened — the message was classified,
    # products were looked up, Claude wrote an answer, and the outbound row is
    # saved. Only the handover to the channel API is skipped, so the reply is
    # readable in the conversation exactly as the customer would have received
    # it, and the customer receives nothing.
    #
    # Returning None is the same thing a failed send returns, which is
    # deliberate: the caller leaves external_id NULL and the thread renders the
    # existing "Not delivered" badge. A held reply that looked delivered would
    # be worse than not having the mode at all.
    #
    # Only the assistant is held. A human pressing send has read the thread and
    # decided to answer; silently swallowing that would strand the customer.
    if not kwargs.get('human_agent'):
        try:
            from app.settings import get_section
            if get_section("ai").get("dry_run", False):
                log_event("info", "services.dispatch.dry_run",
                          f"DRY RUN — reply withheld from {channel}, saved to the "
                          f"conversation only",
                          payload={"channel": channel, "recipient": user_id,
                                   "text_preview": reply[:160]})
                return None
        except Exception as e:
            # Unreadable settings must not silently start sending to real
            # customers while someone believes shadow mode is on. Fail closed.
            log_event("error", "services.dispatch.dry_run_unreadable",
                      f"Could not read ai.dry_run, withholding send to be safe: {e}")
            return None

    if channel == "instagram_dm":
        from app.integrations.meta import send_instagram_reply, send_instagram_card
        # Which of OUR accounts the customer messaged decides which credentials
        # to reply with. Sending from the wrong account fails outright — the
        # token can only message people who messaged THAT account.
        account_id = _account_for(user_id, channel)
        # Text reply first (Claude's natural wording), then a product card
        # beneath it. Card is best-effort — no cached image → text-only.
        # human_agent arrives from messages.send_reply when a PERSON is
        # answering and the 24-hour standard window has already closed. The AI
        # path never sets it — tagging automated messages as human agent replies
        # is a policy violation.
        resp = send_instagram_reply(recipient_id=user_id, text=reply,
                                    account_id=account_id,
                                    human_agent=bool(kwargs.get('human_agent')))
        msg_id = (resp or {}).get("message_id")
        card = _product_card_for_url(product_url)
        if card:
            send_instagram_card(
                recipient_id=user_id,
                title=card["title"],
                subtitle=card["subtitle"],
                image_url=card["image"],
                button_url=card["url"],
            )
        return msg_id
    
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
                  ai_tokens_used=None, ai_model=None, image_urls=None):
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

        # Find the customer's most recent OPEN conversation on this channel.
        # Changing status (active → human_override) must NOT fork the thread,
        # so only a resolved conversation ends it.
        #
        # Why resolved is excluded: a customer who buys a dress in July and
        # comes back for trousers in September is having two conversations,
        # not one. Appending to the closed one also broke it outright — the
        # message landed in a conversation still marked 'resolved', and every
        # alert and queue filters those out, so the customer became invisible.
        # Resolving is an explicit "this is finished"; a reply after it starts
        # something new. Same model as any helpdesk.
        conversation = (
            Conversation.query
            .filter_by(user_id=user.id, channel=channel)
            .filter(Conversation.status != 'resolved')
            .order_by(Conversation.id.desc())
            .first()
        )

        # Nothing open — but if we resolved this customer only moments ago, the
        # resolve was premature rather than the start of a new enquiry. Re-open
        # it instead of forking, so the agent sees one continuous thread rather
        # than the same person appearing twice in the inbox.
        #
        # Beyond the window it still forks, deliberately: someone who bought a
        # dress in July and returns for trousers in September is having two
        # conversations, and appending to the closed one is worse than a fork —
        # the message would sit in a thread still marked resolved, which every
        # alert and queue filters out, so the customer would be invisible.
        if conversation is None:
            try:
                from app.settings import get_section
                window = int(get_section("conversations")
                             .get("reopen_resolved_within_hours", 24))
            except Exception:
                window = 24
            if window > 0:
                from datetime import timedelta
                cutoff = datetime.utcnow() - timedelta(hours=window)
                recent = (Conversation.query
                          .filter_by(user_id=user.id, channel=channel,
                                     status='resolved')
                          .filter(Conversation.resolved_at.isnot(None))
                          .filter(Conversation.resolved_at >= cutoff)
                          .order_by(Conversation.resolved_at.desc())
                          .first())
                if recent is not None:
                    recent.status = 'active'
                    # The resolution stamps have to go with the status. Leaving
                    # them set produced a conversation that was active but still
                    # carried resolved_at, and the per-agent "resolved in window"
                    # metric counts that column.
                    recent.resolved_at = None
                    recent.resolved_by = None
                    conversation = recent
                    log_event("info", "services.conversation_reopened",
                              "Customer replied soon after resolve — re-opened "
                              "rather than starting a new conversation",
                              conversation_id=recent.id)

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

        # Snapshot AI-eligibility NOW. Analytics used to join the live
        # conversation.ai_enabled flag, so switching AI off today silently
        # rewrote yesterday's figures. Freezing it here makes history stable.
        #
        # This must mirror every gate in _ai_should_respond(), because a
        # message the AI was never allowed to answer must not count against
        # it: the global master switch, the per-channel toggle, the
        # per-conversation toggle, and — on comment channels only — the
        # question gate. Missing the master switch meant that with AI globally
        # off, every inbound message was still recorded as "eligible" and then
        # scored as an AI failure. Missing the question gate did the same to
        # public comments: "Love this 😍" is deliberately left unanswered
        # because comments are public and we don't reply to praise, yet it
        # counted as a conversation the AI failed to answer.
        #
        # The praise decision now belongs to the classifier at Step 3.2, which
        # has not run yet — this row has to exist before anything can read it.
        # is_question() therefore survives here as a first guess, and Step 3.2
        # corrects it via _mark_ineligible_for_ai() once the AI has actually
        # read the message. The two disagree in one direction only: a comment
        # this heuristic waves through and the classifier then judges to be
        # praise. That correction is written before the pipeline returns, so
        # nothing downstream reads the guess.
        ai_eligible = None
        if direction == "inbound":
            try:
                from app.models import Channel
                from app.settings import get_section
                from app.utils.intent import is_question
                global_ok  = bool(get_section("ai").get("enabled", True))
                channel_ok = _channel_allows_ai(channel)
                # is_question() is a pure function of the text, so it can be
                # evaluated here even though the real gate runs later.
                question_ok = (is_question(content or "")
                               if channel.endswith("_comment") else True)
                ai_eligible = (global_ok and channel_ok
                               and bool(conversation.ai_enabled) and question_ok)
            except Exception:
                # Same reasoning as the gate: unreadable settings mean the AI
                # stays silent, so this message was never its to answer.
                ai_eligible = False

        msg = Message(
            conversation_id=conversation.id,
            user_id=user.id,
            channel=channel,
            direction=direction,
            ai_eligible=ai_eligible,
            sender=("ai" if direction == "outbound" else None),
            content=content,
            intent=intent,
            external_id=external_id,
            media_id=media_id,
            ai_response_time_ms=ai_response_time_ms,
            ai_tokens_used=ai_tokens_used,
            ai_model=ai_model,
            image_urls=(image_urls or None),
        )
        db.session.add(msg)
        db.session.commit()
        return msg

    except IntegrityError:
        # Lost a race on messages.external_id — another worker saved this exact
        # message between our idempotency check above and this commit. Meta
        # retries deliveries and Gunicorn runs several workers, so two of them
        # genuinely can be inside this function for the same message at once;
        # the check-then-insert above cannot close that window and the unique
        # index is what actually does (see Step 24 in PRODUCTION_CHANGES.md).
        #
        # This is a SUCCESS, not a failure: the message is stored, which is all
        # the caller wanted. Returning None here would have the caller treat a
        # correctly de-duplicated webhook as a save failure and log an error
        # about it — noise that looks exactly like the bug we just fixed.
        db.session.rollback()
        existing = None
        if external_id:
            from app.models import Message
            existing = Message.query.filter_by(external_id=external_id).first()
        log_event("info", "services._save_message.duplicate",
                  f"Message {external_id} was already saved by another worker")
        return existing

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

        # If this reply recommended a product, store its card image so the
        # dashboard thread shows the same picture the customer saw on Instagram.
        if product_url:
            try:
                card = _product_card_for_url(product_url)
                if card and card.get("image"):
                    placeholder.image_urls = [card["image"]]
            except Exception:
                pass

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
    

def _praise_only(classification, message):
    """
    True when the customer asked for nothing — a compliment, a reaction, an
    emoji, a friend tagged.

    Judged on the classifier's intents, so it turns on meaning rather than
    vocabulary. Praise alongside anything else is NOT praise-only: "obsessed!
    does it come in navy?" still gets answered, because there is a real
    question sitting inside the compliment.

    If the classifier degraded to the keyword fallback it never saw the
    message, and its intents carry no opinion about praise at all — everything
    unrecognised lands in "unknown", which would read here as "not praise" and
    make the bot answer every "🔥🔥🔥" on a public post. So the old heuristic
    stands in for exactly that case. Under-replying on a public post is the
    cheaper mistake.
    """
    from app.ai.classifier import NON_ACTIONABLE_INTENTS

    if classification.get('degraded'):
        from app.utils.intent import is_question
        return not is_question(message or '')

    intents = classification.get('intents') or []
    return bool(intents) and all(i in NON_ACTIONABLE_INTENTS for i in intents)


def _like_comment(channel, comment_external_id):
    """
    Acknowledge a comment we are deliberately not replying to.

    Returns (liked, error). Best-effort by design: whether Meta lets this
    account like a comment depends on how the Instagram account was connected,
    and a refusal here just returns us to the behaviour we had before — the
    comment goes unanswered, which is what it was going to be anyway.
    """
    if not comment_external_id or channel != 'instagram_comment':
        return False, 'unsupported channel'
    try:
        from app.integrations.meta import like_instagram_comment
        return like_instagram_comment(comment_external_id)
    except Exception as e:
        log_event("warning", "services._like_comment", str(e)[:200])
        return False, str(e)[:160]


def _mark_ineligible_for_ai(inbound_record):
    """
    Take a praise comment back out of the AI's scorecard.

    _save_message snapshots `ai_eligible` when the row is written, which is
    before the classifier has run — at that point all it can do is guess from
    the text. Now that the AI has actually read the message and we have chosen
    not to reply, correct the snapshot. Without this, every "love this 😍"
    counts as a conversation the AI failed to answer and the failure rate
    climbs with the store's popularity.
    """
    if inbound_record is None:
        return
    try:
        from app import db
        inbound_record.ai_eligible = False
        db.session.commit()
    except Exception as e:
        log_event("error", "services._mark_ineligible_for_ai", str(e)[:200])
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass


def _patch_inbound_intent(inbound_record, intents, degraded=False):
    """Once intents are detected, write the label onto the inbound row.

    `degraded` records WHICH reader produced them. classify_message returns the
    same shape whether the classifier ran or the keyword fallback did, so
    without this the inbox panel headed "What the AI made of this" presents a
    word match as the assistant's reading — which is what it has been doing
    since the credit ran out.
    """
    if inbound_record is None or not intents:
        return
    try:
        from app import db
        inbound_record.intent = intents_to_label(intents)
        inbound_record.intent_source = 'keywords' if degraded else 'classifier'
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


# Words that point at something without naming it. A message built only out of
# these is REFERENTIAL: it refers to something already on screen — nearly always
# the photo the customer sent a moment earlier, or the product we just quoted.
# One list, used to build BOTH the pattern below and the weak-word set, because
# a word that POINTS AT something cannot simultaneously NAME something. Keeping
# them separate let "these" and "ones" count as product names: "are these still
# available?" extracted ['are','these','still'], two of which were not in the
# weak list, so the message was judged to name a product, the referential path
# never ran, and no product context was loaded at all. The AI then had nothing
# to talk about and asked the customer to describe our own stock.
_REFERENTIAL_WORDS = (
    "this", "that", "these", "those", "it", "them", "they", "same", "above",
    "pic", "picture", "photo", "image", "one", "ones",
)

_REFERENTIAL_RE = re.compile(
    r"\b(" + "|".join(_REFERENTIAL_WORDS) + r")\b",
    re.I,
)

# Answers and filler. A reply can be pure grammar — "nope", "no that's not it" —
# and still be about the thing on screen. None of these can be a garment.
_ANSWER_WORDS = {
    "no", "nope", "nah", "not", "yes", "yeah", "yep", "yup", "ok", "okay",
    "thanks", "thank", "the", "are", "is", "am", "was", "were", "be",
    "thats", "its", "im", "dont", "doesnt", "isnt", "wasnt",
}

# Colours and sizes qualify a product but cannot BE one. "red" alone matches
# every red item in the catalogue; paired with a remembered keyword it narrows.
_QUALIFIER_WORDS = {
    "black", "white", "red", "blue", "navy", "green", "pink", "purple", "yellow",
    "orange", "brown", "beige", "cream", "grey", "gray", "gold", "silver",
    "maroon", "teal", "lilac", "nude", "khaki",
    "small", "medium", "large", "xl", "xxl", "xs", "petite", "plus",
}

# Residue the keyword extractor hands back when the message names no product:
# it strips stopwords and returns whatever survives, so "is this still
# available?" yields "still".
_WEAK_KEYWORDS = {
    "still", "available", "availability", "much", "cost", "price", "get", "have",
    "want", "need", "buy", "order", "send", "one", "some", "any", "please",
    "stock", "left", "size", "sizes", "colour", "color", "colours", "colors",
}


def _keyword_is_weak(kw: str | None) -> bool:
    """
    True when a keyword cannot identify a product on its own.

    _extract_product_keyword never fails loudly — when it finds nothing it
    returns message[:30], i.e. the raw question. Searching the catalogue for
    "Can I get this?" or "still" returns arbitrary matches, which is how a
    customer asking about a photo ended up being quoted an unrelated garment.
    """
    if not kw:
        return True
    t = kw.strip().lower().strip("?.!,")
    if not t:
        return True
    if "?" in kw:                      # extractor echoed the whole question back
        return True
    words = t.split()
    if len(words) == 1:
        return t in _WEAK_KEYWORDS or t in _QUALIFIER_WORDS
    # Multi-word but every word is filler/qualifier — still not a product.
    return all(w in _WEAK_KEYWORDS or w in _QUALIFIER_WORDS for w in words)


def _message_names_a_product(text: str | None) -> bool:
    """
    True when the message contains at least one word that could BE a product.

    Judged on the full extracted term list, not just the top-ranked term.
    _extract_product_keyword ranks by catalogue rarity, so "do you have the
    navy wide leg trousers?" hands back "navy" — a colour. Judging weakness on
    that single word would throw away a message that plainly names trousers.
    The full list ('navy', 'wide', 'leg', 'trousers') settles it, and it
    separates cleanly from the referential cases, which yield nothing but
    filler: 'is this still available?' -> ['still'], 'can I get this?' -> [].
    """
    if not text or not text.strip():
        return False
    for term in _extract_product_keywords(text):
        t = term.strip().lower()
        if (t
                and t not in _QUALIFIER_WORDS
                and t not in _WEAK_KEYWORDS
                # Pointing words and bare answers are never product names.
                and t not in _REFERENTIAL_WORDS
                and t not in _ANSWER_WORDS):
            return True
    return False


def _is_referential(text: str | None, extracted: str | None = None) -> bool:
    """
    True when the customer is pointing at something they haven't named.

    Covers the common two-message pattern: a bare photo, then "is this still
    available?" — the second message carries the intent but none of the subject.
    """
    if not text or not text.strip():
        return True                     # image-only message names nothing

    # Naming a product is what makes a message self-contained.
    if _message_names_a_product(text):
        return False

    # It names nothing. Requiring an explicit pointing word on top of that was
    # too strict: "nope" and "what is the price" name no product and contain no
    # pronoun, yet neither can be about anything except what is already on
    # screen. Treating them as fresh subjects dropped the product context and
    # left the assistant asking the customer what they were talking about.
    return True


def _qualifiers_in(text: str | None) -> list[str]:
    """Colour/size words in the message, to narrow a remembered keyword."""
    if not text:
        return []
    seen = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in _QUALIFIER_WORDS and w not in seen:
            seen.append(w)
    return seen


def _find_recent_image_urls(conversation_id: int, max_lookback: int = 4) -> list:
    """
    The most recent photo the customer sent in this conversation.

    Instagram delivers a photo and its caption as SEPARATE messages, so the
    common pattern is a bare image followed a second later by "i want this,
    still available?". That second webhook carries no image, and looking only at
    the current message the assistant answered "I don't see a product link or
    image attached to your message" — to someone who had just sent a photo.

    Looking back a few messages recovers it. Capped tightly: an image from
    further back is probably a different item, and re-answering about the wrong
    photo is worse than admitting we can't see one.
    """
    if not conversation_id:
        return []
    try:
        from app.models import Message
        rows = (Message.query
                .filter_by(conversation_id=conversation_id, direction='inbound')
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(max_lookback).all())
        for m in rows:
            if m.image_urls:
                return list(m.image_urls)
    except Exception as e:
        log_event("warning", "services.image_lookback_failed", str(e)[:160])
    return []


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
   
# Triggers that can only be judged once we know which product the customer is
# asking about. Rules are therefore evaluated in two passes: everything else
# before the Shopify fetch (so a canned reply can short-circuit early and stay
# fast), these immediately after it.
#
# The set itself lives in app/automation.py, which also uses it to work out
# whether one rule shadows another — the same split, decided in one place.
from app.automation import STOCK_TRIGGER_TYPES as _STOCK_TRIGGERS


def _stock_condition_met(tc: dict, products: list) -> bool:
    """
    Evaluate a `shopify_stock` trigger against the products we matched.

    trigger_config: {"type": "shopify_stock", "condition": "eq"|"lte"|"lt"|
                     "gte"|"gt", "value": 0}

    Judged on the BEST match (the product the reply is actually going to talk
    about), not "any product in the list" — with three candidates returned, an
    any() would fire an out-of-stock rule because the third-best alternative
    happened to be sold out.
    """
    if not products:
        return False
    try:
        qty = int((products[0] or {}).get("stock_quantity") or 0)
    except (TypeError, ValueError):
        return False

    # A malformed threshold must not fire. Defaulting it to 0 meant
    # {"condition": "eq", "value": "zero"} matched every sold-out product and
    # sent a customer-facing reply off the back of a broken config.
    try:
        target = int(tc.get("value", 0))
    except (TypeError, ValueError):
        log_event("warning", "services.stock_rule_config",
                  f"shopify_stock rule has a non-numeric value {tc.get('value')!r} — not firing")
        return False

    cond = (tc.get("condition") or "eq").lower()
    return {
        "eq":  qty == target,
        "lte": qty <= target,
        "lt":  qty < target,
        "gte": qty >= target,
        "gt":  qty > target,
    }.get(cond, False)


def _match_automation_actions(message, intents, channel, products=None,
                              stock_pass=False):
    """
    Every rule that applies to this message, in sort_order, as
    [(rule, action_config), ...].

    "First match wins" only applies to actions that ANSWER the customer. You
    cannot send two canned replies to one message, so the first such rule wins
    and evaluation stops there. Actions that merely shape the reply the
    assistant is going to write anyway — include_price — send nothing, so they
    accumulate and evaluation continues past them.

    Treating those as terminal meant an include_price rule near the top quietly
    disabled every rule below it: ask about a sold-out item and you'd get the
    price mentioned but never the out-of-stock reply.

    So this returns any leading run of directive rules, plus the first terminal
    rule if one matches.

    `stock_pass` selects which half of the rules to consider:
      False → every trigger except shopify_stock (runs before the Shopify fetch)
      True  → shopify_stock only (runs after it, with `products` available)

    This used to be _check_template_rule, which returned a template string and
    ignored any rule whose action wasn't reply_template — five of the seven
    action types the API accepts had no executor at all, so well-formed rules
    sat in the UI marked Enabled and silently did nothing. It now returns the
    matched action so the caller can carry out whichever one it is.
    """
    try:
        from app.models import AutomationRule
        from app.automation import is_terminal_action

        matched_rules = []
        text = (message or "").lower()
        rules = (AutomationRule.query
                 .filter_by(enabled=True)
                 .order_by(AutomationRule.sort_order.asc(), AutomationRule.id.asc())
                 .all())

        for rule in rules:
            ac = rule.action_config or {}
            tc = rule.trigger_config or {}
            ttype = tc.get("type")

            # Only look at the half of the rules this pass is responsible for.
            if stock_pass != (ttype in _STOCK_TRIGGERS):
                continue

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
            elif ttype == "shopify_stock":
                matched = _stock_condition_met(tc, products or [])

            if matched:
                matched_rules.append((rule, ac))
                if is_terminal_action(ac.get("type")):
                    break        # this one answers the customer — nothing below it applies

        return matched_rules
    except Exception as e:
        log_event("error", "services._match_automation_actions", str(e))
        return []


# What we ask for when a rule fires the order-details action. The action is
# named ask_order_number, but _lookup_order_status() finds orders by email plus
# name tokens — it has no way to search by order number, and most customers
# don't have one to hand. Asking for a number would collect something we cannot
# use and leave the customer thinking they'd been helped. An admin who really
# wants different wording sets action_config.prompt_text.
_DEFAULT_ORDER_DETAILS_ASK = (
    "Happy to check that for you — could you share the full name and email "
    "address used on the order? I'll look it up right away."
)


def _run_automation_action(rule, action, *, channel, user_id, external_id,
                           inbound_record, message, intents):
    """
    Carry out a matched rule's action.

    Returns {'reply': str|None, 'directives': dict}.
      reply      — text that was sent; the pipeline stops here (the customer
                   has been answered, so generating an AI reply on top would
                   double-message them).
      directives — flags handed to the AI step for actions that shape the
                   reply rather than replacing it.

    Every action is best-effort: a failure is logged and downgraded to "no
    reply", which falls through to the normal AI path. A broken rule must never
    cost the customer their answer.
    """
    atype = (action or {}).get("type")
    conv_id = inbound_record.conversation_id if inbound_record else None
    out = {'reply': None, 'directives': {}}

    def _log(detail, level="info"):
        log_event(level, "services.automation_action",
                  f"Rule '{rule.name}' -> {atype}: {detail}",
                  payload={"rule_id": rule.id, "action": atype,
                           "channel": channel, "user_external_id": user_id,
                           "intents": intents},
                  conversation_id=conv_id)

    try:
        # ── Canned reply, replaces the AI ────────────────────────────────
        if atype == "reply_template":
            template = action.get("template")
            if not template:
                _log("no template text configured — falling through to the AI", "warning")
                return out
            out['reply'] = template

        # ── Ask for what we need to find the order ───────────────────────
        elif atype == "ask_order_number":
            out['reply'] = action.get("prompt_text") or _DEFAULT_ORDER_DETAILS_ASK

        # ── Public comment reply + open a DM ─────────────────────────────
        elif atype == "trigger_dm_flow":
            # This action used to answer here and stop the pipeline, which meant
            # the DM could only ever be a static string from action_config. The
            # public reply promised "all the details" and the DM then opened
            # with "what would you like to know?" — we had just been told, in
            # the comment, and we throw it away to ask again.
            #
            # The details do not exist yet at this point in the pipeline: the
            # Shopify match, the price and the stock level are all fetched at
            # Step 4, below. So instead of answering, hand the pipeline a
            # directive and let the AI generate its real answer as normal. Step
            # 6 then routes that answer into the DM and posts the teaser
            # publicly. Same two messages, except the DM is worth opening.
            if not external_id:
                _log("no comment id on the inbound message — cannot open a DM", "warning")
                return out

            out['directives']['_dm_handoff'] = {
                'comment_id': external_id,
                'public_reply': action.get("public_reply") or "Just sent you a DM!",
                # Only used if Meta refuses the DM. Saying "check your DMs" when
                # no DM exists is worse than simply answering in the open, so
                # the fallback is to publish the AI's answer as a comment.
                'public_reply_fallback': action.get("public_reply_fallback"),
                'rule_name': rule.name,
            }
            _log("deferred to Step 6 — the AI's answer becomes the DM")

        # ── Shape the AI's reply rather than replacing it ────────────────
        elif atype == "include_price":
            out['directives']['force_include_price'] = True
            _log("AI instructed to state the price explicitly")

        # ── Deliberate no-op ─────────────────────────────────────────────
        elif atype == "normal_reply":
            # Reaching here matters even though nothing happens: rules are
            # first-match-wins, so this rule having matched means no LATER rule
            # is consulted. That is the whole point of it — an admin can put a
            # normal_reply rule above a broad canned-reply rule to carve out an
            # exception where the AI answers properly instead.
            _log("matched — suppressing later rules, AI replies normally")

        # ── Escalations are owned by handoff.py (Step 3.5, earlier) ──────
        elif atype in ("human_escalate", "notify_agent"):
            _log("escalation action — already handled at the handoff step")

        else:
            _log("unknown action type — ignored", "warning")

    except Exception as e:
        log_event("error", "services._run_automation_action",
                  f"Rule '{getattr(rule, 'name', '?')}' action {atype} failed: {e}",
                  payload={"rule_id": getattr(rule, 'id', None), "action": atype},
                  conversation_id=conv_id)
        return {'reply': None, 'directives': {}}

    return out
    

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

        handle = conv.user.handle if conv.user else 'a customer'
        channel_label = conv.channel.replace('_', ' ')
        preview = (message_text or '')[:120]

        # Higher severity if AI is off (because the agent really needs to reply
        # themselves) vs on (because AI will at least keep things moving).
        # Always info. This used to be urgent whenever the conversation had
        # AI switched off — sound reasoning per-conversation, and it inverted
        # the moment the GLOBAL kill switch went on, because then every chat
        # has ai_enabled false and every inbound message is urgent-red. A
        # signal that is always on carries nothing.
        #
        # A customer writing in is also not an error. Urgent styling wins an
        # AlertOctagon on a red field, which is the vocabulary of something
        # being broken; using it for the thing the product exists for teaches
        # agents that red means 'probably nothing'.
        #
        # The genuinely urgent case — nobody picking a conversation up — is
        # already owned by unclaimed_alert_minutes, which measures whether
        # anyone responded rather than guessing from a toggle.
        sev = 'info'

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

def _check_handoff_for_inbound(message, intents, inbound_record, llm_handoff=None):
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
        return check_handoff(message, intents, conv, llm_handoff=llm_handoff)
    except Exception as e:
        log_event("error", "services._check_handoff_for_inbound", str(e))
        return None