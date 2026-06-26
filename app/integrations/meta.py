"""
app/integrations/meta.py
Meta Graph API integration — sending replies to Instagram, Facebook, WhatsApp.

Currently implemented:
  - Instagram DM (send_instagram_reply)

Stubbed (logs + no-op):
  - Facebook Messenger (send_facebook_reply)
  - WhatsApp Cloud API  (send_whatsapp_reply)

All functions must NEVER raise — the pipeline keeps running even if the
external API call fails. The reply is already saved to our DB so a human
agent can manually resend.
"""

import os
import requests
from app.utils.logger import log_event

GRAPH_API_VERSION = "v25.0"


def _get_meta_credentials():
    """
    Returns (page_id, page_access_token) — preferring an active MetaConnection
    row in the DB (issued via OAuth), falling back to the legacy env vars
    (FB_PAGE_ID + FB_ACCESS_TOKEN) so existing setups keep working.

    Both can be None if neither source has them. Callers must handle that.
    """
    # 1. Try DB (the OAuth-issued token, what App Review needs us to use)
    try:
        from app import db
        from app.models import MetaConnection
        conn = (MetaConnection.query
                .filter_by(is_active=True)
                .order_by(MetaConnection.connected_at.desc())
                .first())
        if conn and conn.page_id and conn.page_access_token:
            return conn.page_id, conn.page_access_token
    except Exception as e:
        # DB unavailable, table missing, no Flask app context, etc.
        # Don't crash — fall through to env vars.
        log_event("warn", "integrations.meta.creds_db_lookup_failed", str(e))

    # 2. Fall back to env vars (legacy Explorer-token setup)
    return os.getenv("FB_PAGE_ID"), os.getenv("FB_ACCESS_TOKEN")


def _send_url():
    """FB Graph send URL for the configured Page."""
    page_id, _ = _get_meta_credentials()
    if not page_id:
        return None
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/messages"


# ─────────────────────────────────────────────
# Instagram DM — implemented
# ─────────────────────────────────────────────

def send_instagram_reply(recipient_id: str, text: str) -> dict | None:
    """
    Send a DM reply on Instagram via Meta Graph API.

    Args:
        recipient_id: The IG user's Page-Scoped ID (the `sender.id` from the
                      inbound webhook payload).
        text:         The reply text. Max 1000 chars per Meta docs.

    Returns:
        Meta's response dict on success, or None on failure.
    """
    _, token = _get_meta_credentials()
    url = _send_url()
    if not token or not url:
        log_event("error", "integrations.meta.send",
                  "FB_ACCESS_TOKEN or FB_PAGE_ID not set — cannot send reply",
                  payload={"recipient_id": recipient_id})
        return None

    if not text:
        log_event("warning", "integrations.meta.send",
                  "Empty reply text — skipping send",
                  payload={"recipient_id": recipient_id})
        return None

    safe_text = text[:1000]

    payload = {
        "recipient": {"id": recipient_id},
        "message":   {"text": safe_text},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        body_preview = (r.text or "")[:400]

        if r.status_code >= 400:
            print(f"[META SEND FAIL] {r.status_code}: {body_preview}", flush=True)
            log_event("error", "integrations.meta.send",
                      f"Instagram send failed ({r.status_code}): {body_preview[:200]}",
                      payload={
                          "recipient_id": recipient_id,
                          "status": r.status_code,
                          "response": body_preview,
                          "text_preview": safe_text[:120],
                      })
            return None

        data = r.json() if r.text else {}
        log_event("info", "integrations.meta.send",
                  f"Instagram reply sent to {recipient_id}",
                  payload={
                      "recipient_id": recipient_id,
                      "channel": "instagram_dm",
                      "message_id": data.get("message_id"),
                      "text_preview": safe_text[:120],
                  })
        return data

    except requests.RequestException as e:
        log_event("error", "integrations.meta.send",
                  f"Instagram send exception: {e}",
                  payload={
                      "recipient_id": recipient_id,
                      "error": str(e),
                  })
        return None


def send_instagram_comment_reply(comment_id: str, text: str) -> dict | None:
    """
    Reply to an Instagram comment via Meta Graph API.

    Args:
        comment_id: The Meta comment ID we're replying to (the external_id
                    of the inbound message in our DB).
        text:       The reply text.

    Returns:
        Meta's response dict on success (contains new reply's `id`), or
        None on failure. Failures are logged but never raised.
    """
    _, token = _get_meta_credentials()
    if not token:
        log_event("error", "integrations.meta.comment_send",
                  "FB_ACCESS_TOKEN not set — cannot reply to comment",
                  payload={"comment_id": comment_id})
        return None

    if not text:
        log_event("warning", "integrations.meta.comment_send",
                  "Empty reply text — skipping",
                  payload={"comment_id": comment_id})
        return None

    safe_text = text[:1000]
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{comment_id}/replies"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"message": safe_text}

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        body_preview = (r.text or "")[:400]

        if r.status_code >= 400:
            print(f"[META COMMENT SEND FAIL] {r.status_code}: {body_preview}", flush=True)
            log_event("error", "integrations.meta.comment_send",
                      f"Comment reply failed ({r.status_code}): {body_preview[:200]}",
                      payload={
                          "comment_id": comment_id,
                          "status": r.status_code,
                          "response": body_preview,
                          "text_preview": safe_text[:120],
                      })
            return None

        data = r.json() if r.text else {}
        log_event("info", "integrations.meta.comment_send",
                  f"Comment reply posted to {comment_id}",
                  payload={
                      "comment_id": comment_id,
                      "new_reply_id": data.get("id"),
                      "channel": "instagram_comment",
                      "text_preview": safe_text[:120],
                  })
        return data

    except requests.RequestException as e:
        log_event("error", "integrations.meta.comment_send",
                  f"Comment send exception: {e}",
                  payload={"comment_id": comment_id, "error": str(e)})
        return None

# ─────────────────────────────────────────────
# Facebook Messenger — stub (logs + no-op)
# ─────────────────────────────────────────────

def send_facebook_reply(recipient_id: str, message: str) -> None:
    """
    Send a Messenger reply. Currently a stub — reply is logged but not sent.

    To implement:
      POST https://graph.facebook.com/v21.0/me/messages
      Headers: Authorization: Bearer <FB_PAGE_ACCESS_TOKEN>
      Body:    { "recipient": {"id": "<psid>"}, "message": {"text": "..." } }
    """
    log_event("warning", "integrations.meta.send",
              "Facebook send not implemented — reply not delivered",
              payload={
                  "recipient_id": recipient_id,
                  "channel": "facebook_dm",
                  "text_preview": (message or "")[:120],
              })


# ─────────────────────────────────────────────
# WhatsApp — stub (logs + no-op)
# ─────────────────────────────────────────────

def send_whatsapp_reply(phone_number: str, message: str) -> None:
    """
    Send a WhatsApp reply. Currently a stub — reply is logged but not sent.

    To implement:
      POST https://graph.facebook.com/v21.0/<PHONE_NUMBER_ID>/messages
      Headers: Authorization: Bearer <WHATSAPP_TOKEN>
      Body: {
        "messaging_product": "whatsapp",
        "to": "<phone>",
        "type": "text",
        "text": {"body": "<message>"}
      }
    """
    log_event("warning", "integrations.meta.send",
              "WhatsApp send not implemented — reply not delivered",
              payload={
                  "recipient_id": phone_number,
                  "channel": "whatsapp",
                  "text_preview": (message or "")[:120],
              })
    

def unsend_instagram_message(message_id: str) -> bool:
    """
    Unsend (delete) an Instagram message that we previously sent.
    Meta allows this within 24 hours of send.
    Returns True on success, False on failure (logs the reason).
    """
    _, token = _get_meta_credentials()
    if not token:
        log_event("error", "integrations.meta.unsend",
                  "FB_ACCESS_TOKEN not set — cannot unsend",
                  payload={"message_id": message_id})
        return False

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{message_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.delete(url, headers=headers, timeout=10)
        body_preview = (r.text or "")[:300]

        if r.status_code >= 400:
            log_event("error", "integrations.meta.unsend",
                      f"Instagram unsend failed ({r.status_code}): {body_preview[:200]}",
                      payload={
                          "message_id": message_id,
                          "status": r.status_code,
                          "response": body_preview,
                      })
            return False

        log_event("info", "integrations.meta.unsend",
                  f"Unsent IG message {message_id}",
                  payload={"message_id": message_id})
        return True

    except requests.RequestException as e:
        log_event("error", "integrations.meta.unsend",
                  f"Unsend exception: {e}",
                  payload={"message_id": message_id, "error": str(e)})
        return False
    

def delete_instagram_comment(comment_id: str) -> bool:
    """
    Delete an Instagram comment that we previously posted as a reply.
    Returns True on success, False on failure (logs the reason).

    Meta uses the same DELETE pattern for comments as for messages, but
    against the comment's ID rather than a message ID.
    """
    _, token = _get_meta_credentials()
    if not token:
        log_event("error", "integrations.meta.delete_comment",
                  "FB_ACCESS_TOKEN not set — cannot delete comment",
                  payload={"comment_id": comment_id})
        return False

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{comment_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.delete(url, headers=headers, timeout=10)
        body_preview = (r.text or "")[:300]

        if r.status_code >= 400:
            log_event("error", "integrations.meta.delete_comment",
                      f"Instagram comment delete failed ({r.status_code}): {body_preview[:200]}",
                      payload={
                          "comment_id": comment_id,
                          "status": r.status_code,
                          "response": body_preview,
                      })
            return False

        log_event("info", "integrations.meta.delete_comment",
                  f"Deleted IG comment {comment_id}",
                  payload={"comment_id": comment_id})
        return True

    except requests.RequestException as e:
        log_event("error", "integrations.meta.delete_comment",
                  f"Delete comment exception: {e}",
                  payload={"comment_id": comment_id, "error": str(e)})
        return False