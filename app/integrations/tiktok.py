"""
app/integrations/tiktok.py
TikTok integration — DMs and comment replies.

TikTok uses the TikTok for Developers API (Business API).
Webhooks are registered in the TikTok Developer Console.

Current state: MOCK — logs the reply instead of sending.
To activate: implement _real_send_tiktok_reply() and flip USE_MOCK = False.
"""

from app.utils.logger import log_event

USE_MOCK = True  # Flip to False once TikTok credentials are configured


def send_tiktok_reply(recipient_id: str, message: str):
    """
    Sends a reply to a TikTok user (DM or comment reply).

    Args:
        recipient_id: TikTok open_id of the user.
        message:      Text to send.
    """
    if USE_MOCK:
        log_event("info", "integrations.tiktok", f"[MOCK] TikTok reply to {recipient_id}: {message[:80]}")
        return

    _real_send_tiktok_reply(recipient_id, message)


def _real_send_tiktok_reply(recipient_id: str, message: str):
    """
    TODO: Implement TikTok Business API message send.

    TikTok DM endpoint (Business API v2):
      POST https://business-api.tiktok.com/open_api/v1.3/customer_service/conversation/message/send/

    Headers:
      Access-Token: <TIKTOK_ACCESS_TOKEN>
      Content-Type: application/json

    Body:
      {
        "conversation_id": "<conversation_id>",
        "message_type": "TEXT",
        "content": {"text": "<message>"}
      }

    Note: TikTok DMs require the user to have initiated the conversation first.
    Comment replies use a different endpoint:
      POST https://open.tiktokapis.com/v2/comment/reply/

    Steps:
      1. Apply for TikTok for Developers access at developers.tiktok.com
      2. Create an app and request the dm.conversation.write scope
      3. Set TIKTOK_ACCESS_TOKEN and TIKTOK_APP_ID in .env
      4. Implement the POST request below
    """
    raise NotImplementedError("Real TikTok send not yet implemented.")
