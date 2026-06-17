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
from flask import Blueprint, request, jsonify, current_app
from app.services import process_message

bp = Blueprint("main", __name__)


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
    import json
    data = request.get_json(silent=True) or {}
    current_app.logger.warning(
    f"[IG WEBHOOK HIT] headers={dict(request.headers)}"
    )
    current_app.logger.info(f"[IG webhook RAW] {json.dumps(data, indent=2)}")

    events = []          # DM events
    comment_events = []  # IG comment events

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

                mid = msg.get("mid")
                if sender_id and text:
                    events.append((sender_id, text, mid))

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
                mid = msg.get("mid")
                if sender_id and text:
                    events.append((sender_id, text, mid))

            # Shape 3: changes[] with field=comments  →  IG comment events
            for change in (entry.get("changes") or []):
                if change.get("field") != "comments":
                    continue
                value = change.get("value") or {}
                comment_id = value.get("id")
                text = value.get("text")
                from_user = value.get("from") or {}
                sender_id = from_user.get("id")
                # Skip if it's our own comment (a previous reply we sent)
                if sender_id in our_ids:
                    continue
                if sender_id and text and comment_id:
                    # We piggyback the existing (sender_id, text, mid) tuple
                    # by using comment_id as the "mid". The channel string in
                    # process_message tells services.py how to route.
                    comment_events.append((sender_id, text, comment_id))

    except Exception as e:
        current_app.logger.error(f"[IG webhook] parse error: {e}")
        return jsonify({"error": "bad payload"}), 400

    if not events and not comment_events:
        return jsonify({"status": "ignored", "reason": "no text content or sender"}), 200

    replies = []

    # Process DM events
    for sender_id, message_text, mid in events:
        try:
            reply = process_message(
                message=message_text,
                user_id=sender_id,
                channel="instagram_dm",
                external_id=mid,
            )
            replies.append({"sender_id": sender_id, "reply": reply, "type": "dm"})
        except Exception as e:
            current_app.logger.error(f"[IG webhook] DM process error for {sender_id}: {e}")
            replies.append({"sender_id": sender_id, "error": str(e), "type": "dm"})

    # Process Comment events
    for sender_id, comment_text, comment_id in comment_events:
        try:
            reply = process_message(
                message=comment_text,
                user_id=sender_id,
                channel="instagram_comment",
                external_id=comment_id,
            )
            replies.append({"sender_id": sender_id, "reply": reply, "type": "comment"})
        except Exception as e:
            current_app.logger.error(f"[IG webhook] Comment process error for {sender_id}: {e}")
            replies.append({"sender_id": sender_id, "error": str(e), "type": "comment"})

    return jsonify({
        "processed": len(replies),
        "results": replies,
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
    data = request.get_json(silent=True) or {}
    current_app.logger.info(f"[IG comments webhook] payload: {data}")

    sender_id = None
    message_text = None

    try:
        for entry in (data.get("entry") or []):
            for change in (entry.get("changes") or []):
                if change.get("field") not in ("comments", "live_comments"):
                    continue
                value = change.get("value") or {}
                sender_id = (value.get("from") or {}).get("id")
                message_text = value.get("text", "")
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
        channel="instagram_comment"
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
