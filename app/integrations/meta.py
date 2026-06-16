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

def _send_url():
    """FB Graph send URL for the configured Page."""
    page_id = os.getenv("FB_PAGE_ID")
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
    token = os.getenv("FB_ACCESS_TOKEN")
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