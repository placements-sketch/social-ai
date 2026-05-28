"""
app/integrations/meta.py
Meta Graph API — sending replies via Instagram and WhatsApp.

Current state: MOCK — logs the reply instead of actually sending it.
To activate: implement the real send functions and flip USE_MOCK = False.
"""

from app.utils.logger import log_event

USE_MOCK = True  # Flip to False once Meta credentials are configured


# ─────────────────────────────────────────────
# Instagram
# ─────────────────────────────────────────────

def send_instagram_reply(recipient_id: str, message: str):
    """
    Sends a reply to an Instagram user (DM or comment reply).

    Args:
        recipient_id: Instagram-scoped user ID (PSID).
        message:      Text to send.
    """
    if USE_MOCK:
        log_event("info", "integrations.meta", f"[MOCK] Instagram reply to {recipient_id}: {message[:80]}")
        return

    _real_send_instagram(recipient_id, message)


def _real_send_instagram(recipient_id: str, message: str):
    """
    TODO: Implement Meta Graph API send message call.

    Endpoint: POST https://graph.facebook.com/v19.0/me/messages
    Headers:  Authorization: Bearer <META_PAGE_ACCESS_TOKEN>
    Body:
      {
        "recipient": {"id": "<recipient_id>"},
        "message":   {"text": "<message>"}
      }

    Steps:
      1. pip install requests
      2. Set META_PAGE_ACCESS_TOKEN in .env
      3. Make POST request with the body above
    """
    raise NotImplementedError("Real Instagram send not yet implemented.")


# ─────────────────────────────────────────────
# WhatsApp
# ─────────────────────────────────────────────

def send_whatsapp_reply(phone_number: str, message: str):
    """
    Sends a reply to a WhatsApp user via Meta Cloud API.

    Args:
        phone_number: Recipient's WhatsApp phone number (e.g. '254712345678').
        message:      Text to send.
    """
    if USE_MOCK:
        log_event("info", "integrations.meta", f"[MOCK] WhatsApp reply to {phone_number}: {message[:80]}")
        return

    _real_send_whatsapp(phone_number, message)


def _real_send_whatsapp(phone_number: str, message: str):
    """
    TODO: Implement Meta Cloud API WhatsApp send message call.

    Endpoint: POST https://graph.facebook.com/v19.0/<WHATSAPP_PHONE_NUMBER_ID>/messages
    Headers:  Authorization: Bearer <META_PAGE_ACCESS_TOKEN>
              Content-Type: application/json
    Body:
      {
        "messaging_product": "whatsapp",
        "to": "<phone_number>",
        "type": "text",
        "text": {"body": "<message>"}
      }

    Steps:
      1. pip install requests
      2. Set META_PAGE_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env
      3. Make POST request with the body above
    """
    raise NotImplementedError("Real WhatsApp send not yet implemented.")


# ─────────────────────────────────────────────
# Facebook Messenger
# ─────────────────────────────────────────────

def send_facebook_reply(recipient_id: str, message: str):
    """
    Sends a reply to a Facebook Messenger user (DM or comment reply).

    Args:
        recipient_id: Facebook-scoped user ID (PSID).
        message:      Text to send.
    """
    if USE_MOCK:
        log_event("info", "integrations.meta", f"[MOCK] Facebook reply to {recipient_id}: {message[:80]}")
        return

    _real_send_facebook(recipient_id, message)


def _real_send_facebook(recipient_id: str, message: str):
    """
    TODO: Implement Meta Graph API Facebook Messenger send message call.
    The endpoint and payload are identical to Instagram — only the
    page access token differs (use your Facebook Page token).

    Endpoint: POST https://graph.facebook.com/v19.0/me/messages
    Headers:  Authorization: Bearer <META_PAGE_ACCESS_TOKEN>
    Body:
      {
        "recipient": {"id": "<recipient_id>"},
        "message":   {"text": "<message>"}
      }
    """
    raise NotImplementedError("Real Facebook Messenger send not yet implemented.")
