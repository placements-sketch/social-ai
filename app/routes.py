"""
app/routes.py
Webhook endpoints for all inbound channels.

Endpoints:
  GET  /                                — health check
  GET  /webhook/instagram               — Meta webhook verification challenge
  POST /webhook/instagram               — Instagram DM messages
  POST /webhook/instagram/comments      — Instagram post comments
  GET  /webhook/whatsapp                — Meta webhook verification challenge
  POST /webhook/whatsapp                — WhatsApp messages
  GET  /webhook/facebook                — Meta webhook verification challenge
  POST /webhook/facebook                — Facebook Messenger messages
  POST /webhook/facebook/comments       — Facebook post comments
"""

import hmac
import hashlib
import base64
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, jsonify, current_app
from app.services import process_message, process_inbound

bp = Blueprint("main", __name__)


# ── Shopify webhook worker pool ──────────────────────────────────────────────
# A fixed pool instead of a thread per webhook.
#
# Handlers are mostly waiting on Shopify, not on the database — they now hand
# their connection back before the network call — so the bound here is not about
# connections. It caps two other things: how many threads a delivery burst can
# create, and how many simultaneous calls we aim at Shopify's rate limiter.
# Anything above the cap queues and runs a moment later, which is what we want;
# the alternative was handlers timing out and their updates being lost.
_WEBHOOK_WORKERS = int(os.getenv("SHOPIFY_WEBHOOK_WORKERS", "4"))
_webhook_executor = None
_webhook_lock = threading.Lock()


def _webhook_pool() -> ThreadPoolExecutor:
    """The shared executor, created on first use so import stays cheap."""
    global _webhook_executor
    if _webhook_executor is None:
        with _webhook_lock:
            if _webhook_executor is None:
                _webhook_executor = ThreadPoolExecutor(
                    max_workers=_WEBHOOK_WORKERS,
                    thread_name_prefix="shopify-webhook",
                )
    return _webhook_executor


def _candidate_app_secrets() -> list[tuple[str, str]]:
    """
    Every app secret that may legitimately sign events hitting this endpoint,
    as (label, secret) pairs.

    More than one Meta app points here: the Facebook-Login app
    (META_APP_SECRET) and the Instagram-product app (IG_APP_SECRET). Each
    signs with its OWN secret, so verifying against only one silently 403s
    everything the other sends. META_EXTRA_APP_SECRETS accepts a
    comma-separated list for any additional apps.
    """
    out, seen = [], set()

    def add(label, value):
        if value and value not in seen:
            seen.add(value)
            out.append((label, value))

    add('META_APP_SECRET',
        os.getenv('META_APP_SECRET') or current_app.config.get('META_APP_SECRET'))
    add('IG_APP_SECRET', os.getenv('IG_APP_SECRET'))
    for i, extra in enumerate(os.getenv('META_EXTRA_APP_SECRETS', '').split(',')):
        add(f'META_EXTRA_APP_SECRETS[{i}]', extra.strip())
    return out


def _verify_meta_signature(request, channel_label: str) -> tuple[bool, str | None]:
    """
    Verify the X-Hub-Signature-256 header against the raw request body using
    HMAC-SHA256, trying each configured app secret.

    Returns (ok, error_message). On failure, the caller should return 403
    and the helper has already created a notification + audit row.

    If WEBHOOK_SIGNATURE_REQUIRED is set to '0' / 'false', verification is
    skipped (kill switch for emergency). Default behaviour: enforce.
    """
    required = os.getenv('WEBHOOK_SIGNATURE_REQUIRED', 'true').lower() not in ('0', 'false', 'no')
    if not required:
        return True, None

    candidates = _candidate_app_secrets()
    if not candidates:
        return False, 'No app secret configured — cannot verify signature'

    sig_header = request.headers.get('X-Hub-Signature-256', '')
    if not sig_header.startswith('sha256='):
        return False, 'Missing or malformed X-Hub-Signature-256 header'

    received_sig = sig_header[len('sha256='):]
    raw_body = request.get_data(cache=True)  # cache=True so subsequent get_json() still works

    for label, secret in candidates:
        expected_sig = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(received_sig, expected_sig):
            # Which app signed this tells us which app is actually delivering.
            current_app.logger.info(f"[SIG OK] {channel_label} verified via {label}")
            return True, None

    current_app.logger.warning(
        f"[SIG MISMATCH] {channel_label} received={received_sig[:12]}... "
        f"body_len={len(raw_body)} tried={[l for l, _ in candidates]}"
    )
    return False, 'Signature mismatch'


def _reject_bad_signature(channel_label: str, reason: str):
    """
    Common handler when signature verification fails: log, notify admins,
    return 403.
    """
    from app import db
    from app.utils.logger import log_event
    log_event(
        "warning",
        "routes.bad_signature",
        f"Rejected webhook on {channel_label}: {reason}",
        payload={
            "channel": channel_label,
            "reason": reason,
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get('User-Agent', '')[:200],
        },
    )
    from app.notifications import notify_admins
    notify_admins(
        type_='webhook_signature_failed',
        title=f"Rejected unsigned webhook ({channel_label})",
        body=(
            f"A webhook hit {channel_label} that did not match Meta's signature. "
            f"Reason: {reason}. Source: {request.remote_addr}. "
            f"If this is unexpected, rotate your Meta App Secret."
        ),
        severity='urgent',
        resource_type='security',
        coalesce=True,
    )
    db.session.commit()
    return jsonify({'error': 'Invalid signature'}), 403

# ─────────────────────────────────────────────
# Shopify webhooks — freshness layer over the cron delta+reconcile sync
# ─────────────────────────────────────────────

def _verify_shopify_hmac(request) -> tuple[bool, str | None]:
    """
    Verify X-Shopify-Hmac-Sha256: a BASE64 HMAC-SHA256 over the raw body,
    keyed with the Shopify app secret. (Meta uses hex — Shopify uses base64.)
    Honors the WEBHOOK_SIGNATURE_REQUIRED kill switch.
    """
    required = os.getenv('WEBHOOK_SIGNATURE_REQUIRED', 'true').lower() not in ('0', 'false', 'no')
    if not required:
        return True, None

    secret = (os.getenv('SHOPIFY_WEBHOOK_SECRET')
              or os.getenv('SHOPIFY_CLIENT_SECRET')
              or current_app.config.get('SHOPIFY_CLIENT_SECRET'))
    if not secret:
        return False, 'SHOPIFY_CLIENT_SECRET not configured — cannot verify webhook'

    received = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not received:
        return False, 'Missing X-Shopify-Hmac-Sha256 header'

    raw_body = request.get_data(cache=True)  # cache=True so get_json() still works
    digest = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode('utf-8')

    if not hmac.compare_digest(received, expected):
        current_app.logger.warning(
            f"[SHOPIFY SIG MISMATCH] received={received[:12]}... expected={expected[:12]}... "
            f"body_len={len(raw_body)}"
        )
        return False, 'Signature mismatch'

    return True, None


@bp.route("/webhook/shopify", methods=["POST"])
def shopify_webhook():
    """
    Receives Shopify webhooks (products, orders, customers, inventory).
    Verifies HMAC, then dispatches by X-Shopify-Topic in a background thread so
    we return 200 fast (Shopify retries on non-2xx or >5s).

    This is a FRESHNESS layer only — the cron delta+reconcile sync stays the
    source of truth and backstops anything missed while the instance sleeps.
    """
    ok, err = _verify_shopify_hmac(request)
    if not ok:
        from app.utils.logger import log_event
        log_event("warning", "routes.shopify.bad_signature",
                  f"Rejected Shopify webhook: {err}",
                  payload={"reason": err, "remote_addr": request.remote_addr,
                           "topic": request.headers.get("X-Shopify-Topic")})
        return jsonify({'error': 'Invalid signature'}), 401

    topic = request.headers.get("X-Shopify-Topic", "")
    data = request.get_json(silent=True) or {}

    app_obj = current_app._get_current_object()

    def _process():
        with app_obj.app_context():
            try:
                from app.shopify_webhooks import dispatch_shopify_webhook
                dispatch_shopify_webhook(topic, data)
            except Exception as e:
                app_obj.logger.error(f"[Shopify webhook bg] {topic} error: {e}")

    # Queued onto a small fixed pool, not a fresh thread per webhook.
    #
    # This used to be `threading.Thread(...).start()` with nothing bounding it.
    # Shopify delivers in bursts — a bulk product edit fires many webhooks at
    # once — so an unbounded spawn put more concurrent handlers in flight than
    # this worker has database connections (pool_size 4 + overflow 1 = 5). They
    # queued on the pool, waited the full 30s pool_timeout and failed, which is
    # the "QueuePool limit of size 4 overflow 1 reached" run in the logs. Each
    # failure is a dropped Shopify update, so the product cache silently drifts.
    #
    # Bounded below the connection count on purpose: web requests need
    # connections too, and a webhook that waits a second in a queue is fine
    # where one that times out is data loss. Shopify still gets its 200 now.
    _webhook_pool().submit(_process)
    return jsonify({"status": "accepted", "topic": topic}), 200

# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────

@bp.route("/")
def home():
    return jsonify({"status": "Social AI Assistant is running"}), 200


# ─────────────────────────────────────────────
# Shared Meta webhook verification helper
# Meta sends a GET with hub.challenge when you register a webhook URL.
# ─────────────────────────────────────────────

def _verify_meta_webhook(request):
    """
    Responds to Meta's webhook verification challenge.
    Returns the hub.challenge value if the verify token matches, else 403.
    """
    verify_token = current_app.config["META_VERIFY_TOKEN"]
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        return str(challenge), 200
    return jsonify({"error": "Verification failed"}), 403


# ─────────────────────────────────────────────
# Instagram DM webhook
# ─────────────────────────────────────────────

@bp.route("/webhook/instagram", methods=["GET"])
def instagram_verify():
    """Meta calls this GET to verify the webhook URL is live."""
    return _verify_meta_webhook(request)


@bp.route("/webhook/instagram", methods=["POST"])
def instagram_webhook():
    """
    Receives Instagram DM events from Meta. Processes ALL events in the
    payload (Meta may batch multiple messages in a single webhook).

    Supports both:
      Shape 1 (legacy): entry[].messaging[]
      Shape 2 (v25):    entry[].changes[].value where field=messages
    """
    ok, err = _verify_meta_signature(request, 'instagram_dm')
    if not ok:
        return _reject_bad_signature('instagram_dm', err)

    data = request.get_json(silent=True) or {}
    # Every other webhook handler logs its raw payload; this one didn't, so
    # dropped events left no trace at all. Keep the shape visible — read
    # receipts and echoes look identical to a lost DM from the access log.
    current_app.logger.info(f"[IG webhook] payload: {data}")

    # Both the `instagram` and `page` webhook objects are registered against
    # THIS callback URL, and Facebook Messenger events use the same
    # entry[].messaging[] shape Instagram DMs do. Without branching on
    # `object`, every Messenger DM to the Page was stored as an Instagram DM —
    # wrong channel, wrong icon, and it polluted per-channel analytics.
    #
    # Tells, if you ever need to identify one by hand: object=page, recipient
    # is the Page id, and the mid starts with "m_" (Instagram mids are base64
    # beginning "aWdfZAG").
    obj = (data.get("object") or "instagram").lower()
    is_page = obj == "page"
    dm_channel = "facebook_dm" if is_page else "instagram_dm"
    comment_channel = "facebook_comment" if is_page else "instagram_comment"

    events = []          # DM events
    comment_events = []  # comment events

    try:
        for entry in (data.get("entry") or []):

            # Build the set of "our own" IDs to filter out — webhook fires
            # for outbound messages too, and we must NOT process them as
            # if a customer sent them.
            import os
            our_ids = {x for x in (
                os.getenv("IG_BUSINESS_ACCOUNT_ID"),
                os.getenv("FB_PAGE_ID"),
            ) if x}

            # Shape 1: messaging[]
            for messaging in (entry.get("messaging") or []):
                msg = messaging.get("message") or {}
                # Skip echoes of our own outbound messages
                if msg.get("is_echo"):
                    continue
                text = msg.get("text")
                sender_id = (messaging.get("sender") or {}).get("id")
                if sender_id in our_ids:
                    continue

                # A forwarded post/reel/story is NOT type "image" — it arrives
                # as "share" (or ig_reel / story_mention), so the old
                # image-only filter dropped it and the AI never saw what the
                # customer sent. Pull a usable image URL out of those too.
                image_urls = []
                # When the customer forwards one of OUR posts, keep the post's
                # media id as well as its picture. Our own caption normally
                # names the exact product ("Vivo Lani Maxi Dress in Satin"),
                # which pins it down far better than asking vision to guess the
                # garment from a photo. Previously only image_url survived and
                # the caption was discarded.
                shared_post_id = None
                for a in (msg.get("attachments") or []):
                    payload = a.get("payload") or {}
                    atype = a.get("type")
                    if atype == "image":
                        u = payload.get("url")
                    elif atype in ("ig_post", "share", "ig_reel", "story_mention"):
                        u = payload.get("image_url") or payload.get("thumbnail_url")
                        post_mid = payload.get("ig_post_media_id")
                        if post_mid and not shared_post_id:
                            shared_post_id = post_mid
                        if not u and post_mid:
                            try:
                                from app.integrations.meta import fetch_instagram_media
                                media = fetch_instagram_media(post_mid)
                                if media and media.get("image_url"):
                                    u = media["image_url"]
                            except Exception as e:
                                current_app.logger.warning(
                                    f"[IG webhook] could not resolve ig_post {post_mid}: {e}"
                                )
                        if not u:
                            u = payload.get("url")
                    elif atype == "video":
                        u = payload.get("thumbnail_url") or payload.get("image_url")
                    else:
                        u = None
                    if atype and atype != "image":
                        current_app.logger.info(
                            f"[IG webhook] non-image attachment type={atype} "
                            f"payload_keys={list(payload.keys())} picked={bool(u)}"
                        )
                    if u and u not in image_urls:
                        image_urls.append(u)
                mid = msg.get("mid")
                if sender_id and (text or image_urls):
                    events.append((sender_id, text or "", mid, image_urls, shared_post_id, entry.get("id")))

            # Shape 2: changes[] with field=messages
            for change in (entry.get("changes") or []):
                if change.get("field") != "messages":
                    continue
                value = change.get("value") or {}
                msg = value.get("message") or {}
                if msg.get("is_echo"):
                    continue
                text = msg.get("text")
                sender_id = (value.get("sender") or {}).get("id")
                if sender_id in our_ids:
                    continue
                # A forwarded post/reel/story is NOT type "image" — it arrives
                # as "share" (or ig_reel / story_mention), so the old
                # image-only filter dropped it and the AI never saw what the
                # customer sent. Pull a usable image URL out of those too.
                image_urls = []
                shared_post_id = None    # see the note on the other shape above
                for a in (msg.get("attachments") or []):
                    payload = a.get("payload") or {}
                    atype = a.get("type")
                    if atype == "image":
                        u = payload.get("url")
                    elif atype in ("ig_post", "share", "ig_reel", "story_mention"):
                        u = payload.get("image_url") or payload.get("thumbnail_url")
                        post_mid = payload.get("ig_post_media_id")
                        if post_mid and not shared_post_id:
                            shared_post_id = post_mid
                        if not u and post_mid:
                            try:
                                from app.integrations.meta import fetch_instagram_media
                                media = fetch_instagram_media(post_mid)
                                if media and media.get("image_url"):
                                    u = media["image_url"]
                            except Exception as e:
                                current_app.logger.warning(
                                    f"[IG webhook] could not resolve ig_post {post_mid}: {e}"
                                )
                        if not u:
                            u = payload.get("url")
                    elif atype == "video":
                        u = payload.get("thumbnail_url") or payload.get("image_url")
                    else:
                        u = None
                    if atype and atype != "image":
                        current_app.logger.info(
                            f"[IG webhook] non-image attachment type={atype} "
                            f"payload_keys={list(payload.keys())} picked={bool(u)}"
                        )
                    if u and u not in image_urls:
                        image_urls.append(u)
                mid = msg.get("mid")
                if sender_id and (text or image_urls):
                    events.append((sender_id, text or "", mid, image_urls, shared_post_id, entry.get("id")))

            # Shape 3: changes[] with field=comments  →  IG comment events
            for change in (entry.get("changes") or []):
                if change.get("field") != "comments":
                    continue
                value = change.get("value") or {}
                comment_id = value.get("id")
                text = value.get("text")
                from_user = value.get("from") or {}
                sender_id = from_user.get("id")
                username = from_user.get("username")
                # Our own comments are no longer dropped here. They are passed
                # to the pipeline like any other event, where _authored_by_us()
                # stops the AI reacting and record_own_platform_reply() files
                # them into the customer's thread. Dropping them at the door
                # meant an agent's reply written in the Instagram app never
                # appeared in our inbox at all, so the thread showed a question
                # with no answer under it.
                #
                # parent_id is what makes that possible: on a reply to another
                # comment Meta sends the id of the comment being replied to,
                # which is the customer's original comment.
                parent_id = value.get("parent_id")
                media_id = (value.get("media") or {}).get("id")
                if sender_id and text and comment_id:
                    comment_events.append((sender_id, text, comment_id, username,
                                           media_id, parent_id))

    except Exception as e:
        current_app.logger.error(f"[IG webhook] parse error: {e}")
        return jsonify({"error": "bad payload"}), 400

    if not events and not comment_events:
        return jsonify({"status": "ignored", "reason": "no text content or sender"}), 200

    # ─────────────────────────────────────────────────────────────
    # Return 200 to Meta IMMEDIATELY, process in background thread.
    # Meta retries webhooks that take >5s. The 2s sleep + AI generation
    # + DB writes were pushing us past that, causing duplicate sends.
    # By returning 200 fast, Meta never retries → no duplicates.
    # ─────────────────────────────────────────────────────────────
    import threading
    app_obj = current_app._get_current_object()

    def process_in_background():
        with app_obj.app_context():
            # Process DM events.
            # Meta can batch a photo AND its caption into ONE payload. Handled
            # sequentially, the first event would finish (and reply) before the
            # second was even saved, so the debounce couldn't see it → two
            # replies to one turn. So: persist all but the last event per
            # sender, then run the pipeline only on the last — its coalesce
            # step merges the saved ones into a single turn.
            from collections import OrderedDict
            _grouped = OrderedDict()
            for _ev in events:
                _grouped.setdefault(_ev[0], []).append(_ev)

            for sender_id, _sender_events in _grouped.items():
                if len(_sender_events) > 1:
                    from app.services import _save_message
                    for (_sid, _txt, _mid, _imgs, _post, _acct) in _sender_events[:-1]:
                        try:
                            _save_message(
                                user_id=sender_id, channel=dm_channel,
                                content=((_txt or "").strip() or "[Sent a photo]"),
                                intent=None, direction="inbound",
                                external_id=_mid, image_urls=_imgs,
                            )
                        except Exception:
                            pass
                _sid, message_text, mid, image_urls, shared_post_id, account_id = _sender_events[-1]
                try:
                    process_inbound(
                        message=message_text,
                        user_id=sender_id,
                        channel=dm_channel,
                        external_id=mid,
                        media_id=shared_post_id,   # our post, if they forwarded one
                        image_urls=image_urls,
                    )
                    # Remember WHICH of our accounts this arrived on, so the
                    # reply goes back out from the same one. Without it a
                    # second connected account would be answered with the
                    # wrong credentials — a guaranteed 403.
                    try:
                        from app.services import stamp_conversation_account
                        stamp_conversation_account(sender_id, dm_channel, account_id)
                    except Exception:
                        pass
                    # DM webhooks carry only the numeric IGSID, so resolve the
                    # username via the Graph API and cache it — once per customer.
                    # Instagram only: a Messenger PSID is not an IGSID and the
                    # lookup would just fail.
                    try:
                        from app import db
                        from app.models import User
                        user_row = None if is_page else User.query.filter_by(
                            external_id=sender_id, channel=dm_channel).first()
                        if user_row and (not user_row.name or user_row.name == sender_id):
                            from app.integrations.meta import fetch_instagram_username
                            profile = fetch_instagram_username(sender_id)
                            if profile:
                                uname = profile.get("username") or profile.get("name")
                                if uname:
                                    user_row.name = uname
                                    if profile.get("profile_pic") and not user_row.avatar_url:
                                        user_row.avatar_url = profile.get("profile_pic")
                                    db.session.commit()
                    except Exception:
                        pass
                except Exception as e:
                    app_obj.logger.error(f"[IG webhook bg] DM process error for {sender_id}: {e}")

            # Process Comment events
            for (sender_id, comment_text, comment_id, username, media_id,
                 parent_id) in comment_events:
                try:
                    process_message(
                        message=comment_text,
                        user_id=sender_id,
                        channel=comment_channel,
                        external_id=comment_id,
                        media_id=media_id,
                        parent_id=parent_id,
                        username=username,
                    )
                    # Patch the username on the User row so the UI shows the
                    # handle instead of the numeric ID.
                    if username:
                        try:
                            from app import db
                            from app.models import User
                            user_row = User.query.filter_by(
                                external_id=sender_id, channel=comment_channel
                            ).first()
                            if user_row and user_row.name != username:
                                user_row.name = username
                                db.session.commit()
                        except Exception:
                            pass
                except Exception as e:
                    app_obj.logger.error(f"[IG webhook bg] Comment process error for {sender_id}: {e}")

    threading.Thread(target=process_in_background, daemon=True).start()

    return jsonify({
        "status": "accepted",
        "dm_count": len(events),
        "comment_count": len(comment_events),
    }), 200

# ─────────────────────────────────────────────
# Instagram Comments webhook
# ─────────────────────────────────────────────

@bp.route("/webhook/instagram/comments", methods=["POST"])
def instagram_comments_webhook():
    """
    Receives Instagram comment events.
    Supports v25 `changes[].value` shape used by the modern IG Webhooks API.
    """
    ok, err = _verify_meta_signature(request, 'instagram_comment')
    if not ok:
        return _reject_bad_signature('instagram_comment', err)

    data = request.get_json(silent=True) or {}
    current_app.logger.info(f"[IG comments webhook] payload: {data}")

    sender_id = None
    message_text = None
    comment_id = None
    media_id = None
    parent_id = None
    username = None

    try:
        for entry in (data.get("entry") or []):
            for change in (entry.get("changes") or []):
                if change.get("field") not in ("comments", "live_comments"):
                    continue
                value = change.get("value") or {}
                sender_id = (value.get("from") or {}).get("id")
                message_text = value.get("text", "")
                # Carried through so this route behaves like the main webhook.
                # It used to pass only the text and the sender, so a comment
                # arriving here got no idempotency key, no post context, and no
                # parent — meaning an agent's on-platform reply could not be
                # filed into the customer's thread and a redelivery would be
                # saved twice. Which of the two routes Meta uses should not
                # change what happens to the comment.
                comment_id = value.get("id")
                media_id = (value.get("media") or {}).get("id")
                parent_id = value.get("parent_id")
                username = (value.get("from") or {}).get("username")
                if sender_id and message_text:
                    break
            if sender_id and message_text:
                break
    except Exception as e:
        current_app.logger.error(f"[IG comments webhook] parse error: {e}")
        return jsonify({"error": "bad payload"}), 400

    if not sender_id or not message_text:
        return jsonify({"status": "ignored", "reason": "no text content or sender"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="instagram_comment",
        external_id=comment_id,
        media_id=media_id,
        parent_id=parent_id,
        username=username,
    )

    return jsonify({"reply": reply}), 200

# ─────────────────────────────────────────────
# WhatsApp webhook (placeholder — wire up later)
# ─────────────────────────────────────────────

@bp.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_verify():
    """Meta calls this GET to verify the WhatsApp webhook URL."""
    return _verify_meta_webhook(request)


@bp.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """
    Receives WhatsApp message events from Meta Cloud API.
    Payload shape (simplified):
      { "entry": [{ "changes": [{ "value": { "messages": [{ "from": "...", "text": {"body": "..."} }] } }] }] }

    TODO: Wire up send_whatsapp_reply() once WhatsApp credentials are configured.
    """
    ok, err = _verify_meta_signature(request, 'whatsapp')
    if not ok:
        return _reject_bad_signature('whatsapp', err)

    data = request.get_json(silent=True) or {}

    try:
        message_obj = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender_id = message_obj["from"]          # WhatsApp phone number
        message_text = message_obj["text"]["body"]
    except (KeyError, IndexError):
        return jsonify({"error": "Invalid payload structure"}), 400

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="whatsapp"
    )

    # TODO: call send_whatsapp_reply(sender_id, reply) here
    return jsonify({"reply": reply}), 200


# ─────────────────────────────────────────────
# Facebook Messenger webhook
# ─────────────────────────────────────────────

@bp.route("/webhook/facebook", methods=["GET"])
def facebook_verify():
    """Meta calls this GET to verify the Facebook webhook URL."""
    return _verify_meta_webhook(request)


@bp.route("/webhook/facebook", methods=["POST"])
def facebook_webhook():
    """
    Receives Facebook Messenger message events.
    
    Supports both:
      Shape 1 (legacy): entry[].messaging[]
      Shape 2 (v25):    entry[].changes[].value with field=messages
    """
    ok, err = _verify_meta_signature(request, 'facebook_dm')
    if not ok:
        return _reject_bad_signature('facebook_dm', err)

    data = request.get_json(silent=True) or {}
    current_app.logger.info(f"[FB webhook] payload: {data}")

    sender_id = None
    message_text = None

    try:
        for entry in (data.get("entry") or []):
            # Shape 1: messaging[]
            for messaging in (entry.get("messaging") or []):
                sender_id = messaging.get("sender", {}).get("id")
                message_text = messaging.get("message", {}).get("text")
                if sender_id and message_text:
                    break
            if sender_id and message_text:
                break

            # Shape 2: changes[] with field=messages
            for change in (entry.get("changes") or []):
                if change.get("field") != "messages":
                    continue
                value = change.get("value") or {}
                sender_id = value.get("sender", {}).get("id")
                message_text = value.get("message", {}).get("text")
                if sender_id and message_text:
                    break
            if sender_id and message_text:
                break
    except Exception as e:
        current_app.logger.error(f"[FB webhook] parse error: {e}")
        return jsonify({"error": "bad payload"}), 400

    if not sender_id or not message_text:
        return jsonify({"status": "ignored", "reason": "no text content or sender"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="facebook_dm"
    )

    # TODO: call send_facebook_reply(sender_id, reply) here
    return jsonify({"reply": reply}), 200


@bp.route("/webhook/facebook/comments", methods=["POST"])
def facebook_comments_webhook():
    """
    Receives Facebook post comment events.
    v25 shape: entry[].changes[].value with field=feed (and item=comment) OR field=comments.
    Older payloads used `message`; newer ones use `text`. Handle both.
    """
    ok, err = _verify_meta_signature(request, 'facebook_comment')
    if not ok:
        return _reject_bad_signature('facebook_comment', err)

    data = request.get_json(silent=True) or {}
    current_app.logger.info(f"[FB comments webhook] payload: {data}")

    sender_id = None
    message_text = None

    try:
        for entry in (data.get("entry") or []):
            for change in (entry.get("changes") or []):
                # Accept both "feed" (legacy) and "comments" (newer)
                if change.get("field") not in ("feed", "comments"):
                    continue
                value = change.get("value") or {}
                # Only care about comments (skip likes, reactions, etc.)
                if value.get("item") and value.get("item") != "comment":
                    continue
                sender_id = (value.get("from") or {}).get("id")
                # Try both keys — Meta uses inconsistent naming
                message_text = value.get("message") or value.get("text") or ""
                if sender_id and message_text:
                    break
            if sender_id and message_text:
                break
    except Exception as e:
        current_app.logger.error(f"[FB comments webhook] parse error: {e}")
        return jsonify({"error": "bad payload"}), 400

    if not sender_id or not message_text:
        return jsonify({"status": "ignored", "reason": "no text content or sender"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="facebook_comment"
    )

    return jsonify({"reply": reply}), 200

# ─────────────────────────────────────────────
# TikTok webhooks
# ─────────────────────────────────────────────

@bp.route("/webhook/tiktok", methods=["GET"])
def tiktok_verify():
    """
    TikTok webhook verification.
    TikTok sends a GET with a challenge parameter — echo it back to verify.
    """
    challenge = request.args.get("challenge", "")
    if challenge:
        return challenge, 200
    return jsonify({"error": "No challenge provided"}), 400


@bp.route("/webhook/tiktok", methods=["POST"])
def tiktok_dm_webhook():
    """
    Receives TikTok DM (direct message) events.

    TikTok Business API payload shape (simplified):
      {
        "event": "direct_message",
        "data": {
          "sender": {"open_id": "..."},
          "message": {"text": "..."}
        }
      }
    """
    data = request.get_json(silent=True) or {}

    try:
        sender_id    = data["data"]["sender"]["open_id"]
        message_text = data["data"]["message"].get("text", "")
    except (KeyError, TypeError):
        return jsonify({"error": "Invalid payload structure"}), 400

    if not message_text:
        return jsonify({"status": "ignored", "reason": "no text content"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="tiktok_dm"
    )

    # TODO: call send_tiktok_reply(sender_id, reply) here
    return jsonify({"reply": reply}), 200


@bp.route("/webhook/tiktok/comments", methods=["POST"])
def tiktok_comments_webhook():
    """
    Receives TikTok video comment events.

    TikTok comment payload shape (simplified):
      {
        "event": "comment",
        "data": {
          "user": {"open_id": "..."},
          "comment": {"text": "..."}
        }
      }
    """
    data = request.get_json(silent=True) or {}

    try:
        sender_id    = data["data"]["user"]["open_id"]
        message_text = data["data"]["comment"].get("text", "")
    except (KeyError, TypeError):
        return jsonify({"error": "Invalid payload structure"}), 400

    if not message_text:
        return jsonify({"status": "ignored", "reason": "no text content"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="tiktok_comment"
    )

    # TODO: call send_tiktok_reply(sender_id, reply) here
    return jsonify({"reply": reply}), 200