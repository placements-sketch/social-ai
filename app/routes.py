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
    Receives Instagram DM events from Meta.
    Payload shape (simplified):
      { "entry": [{ "messaging": [{ "sender": {"id": "..."}, "message": {"text": "..."} }] }] }
    """
    data = request.get_json(silent=True) or {}

    # Extract the first message from the payload
    try:
        entry = data.get("entry", [])[0]
        messaging_list = entry.get("messaging", [])

        if not messaging_list:
            return jsonify({"status": "ignored", "reason": "no messaging"}), 200

        messaging = messaging_list[0]

        sender_id = messaging.get("sender", {}).get("id")
        message_text = messaging.get("message", {}).get("text")

        if not sender_id or not message_text:
            return jsonify({"status": "ignored"}), 200

    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"error": "bad payload"}), 400
    if not message_text:
        # Could be a reaction, sticker, etc. — ignore for now
        return jsonify({"status": "ignored", "reason": "no text content"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="instagram_dm"
    )

    return jsonify({"reply": reply}), 200


# ─────────────────────────────────────────────
# Instagram Comments webhook
# ─────────────────────────────────────────────

@bp.route("/webhook/instagram/comments", methods=["POST"])
def instagram_comments_webhook():
    """
    Receives Instagram comment events.
    Payload shape (simplified):
      { "entry": [{ "changes": [{ "value": { "from": {"id": "..."}, "text": "..." } }] }] }
    """
    data = request.get_json(silent=True) or {}

    try:
        change = data["entry"][0]["changes"][0]["value"]
        sender_id = change["from"]["id"]
        message_text = change.get("text", "")
    except (KeyError, IndexError):
        return jsonify({"error": "Invalid payload structure"}), 400

    if not message_text:
        return jsonify({"status": "ignored", "reason": "no text content"}), 200

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
    Payload shape is identical to Instagram DMs — both use the
    Messenger Platform format via Meta Graph API.

    Shape (simplified):
      { "entry": [{ "messaging": [{ "sender": {"id": "..."}, "message": {"text": "..."} }] }] }
    """
    data = request.get_json(silent=True) or {}

    try:
        messaging = data["entry"][0]["messaging"][0]
        sender_id = messaging["sender"]["id"]
        message_text = messaging["message"].get("text", "")
    except (KeyError, IndexError):
        return jsonify({"error": "Invalid payload structure"}), 400

    if not message_text:
        return jsonify({"status": "ignored", "reason": "no text content"}), 200

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
    Payload shape (simplified):
      { "entry": [{ "changes": [{ "value": { "from": {"id": "..."}, "message": "..." } }] }] }
    """
    data = request.get_json(silent=True) or {}

    try:
        change = data["entry"][0]["changes"][0]["value"]
        sender_id = change["from"]["id"]
        message_text = change.get("message", "")
    except (KeyError, IndexError):
        return jsonify({"error": "Invalid payload structure"}), 400

    if not message_text:
        return jsonify({"status": "ignored", "reason": "no text content"}), 200

    reply = process_message(
        message=message_text,
        user_id=sender_id,
        channel="facebook_comment"
    )

    # TODO: call send_facebook_reply(sender_id, reply) here
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
