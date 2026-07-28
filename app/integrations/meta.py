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


# Cached Page token derived from the delegated USER token. Page tokens don't
# expire while the parent user token is valid, so one exchange per process.
_delegated_cache = {"page_id": None, "token": None}


def _delegated_enabled() -> bool:
    return os.getenv("META_USE_DELEGATED", "false").lower() in ("1", "true", "yes")


def _get_delegated_credentials():
    """
    Bridge credentials borrowed from an app that already holds Advanced Access
    for instagram_manage_messages.

    Our own app receives `comments` webhooks fine, but Meta withholds all DM
    data from it until App Review grants Advanced Access — no webhooks, and
    /conversations returns (#200). A delegated token from an approved app on
    the same Page lets DMs flow in the meantime via polling.

    TEMPORARY. Remove once our own app is approved: unset META_USE_DELEGATED.

    Returns (page_id, page_access_token), or (None, None) when disabled or
    misconfigured, so callers fall through to our own credentials.
    """
    if not _delegated_enabled():
        return None, None

    user_token = os.getenv("META_DELEGATED_USER_TOKEN")
    page_id = os.getenv("META_DELEGATED_PAGE_ID") or os.getenv("FB_PAGE_ID")
    if not user_token or not page_id:
        log_event("warn", "integrations.meta.delegated_misconfigured",
                  "META_USE_DELEGATED is on but token/page_id missing")
        return None, None

    if _delegated_cache["page_id"] == page_id and _delegated_cache["token"]:
        return page_id, _delegated_cache["token"]

    # Exchange the USER token for this Page's token.
    try:
        r = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}",
            params={"fields": "access_token", "access_token": user_token},
            timeout=15,
        )
        token = (r.json() or {}).get("access_token")
    except requests.RequestException as e:
        log_event("error", "integrations.meta.delegated_exchange_failed", str(e))
        return None, None

    if not token:
        log_event("error", "integrations.meta.delegated_exchange_failed",
                  f"No page token returned for page {page_id} (status {r.status_code})")
        return None, None

    _delegated_cache.update(page_id=page_id, token=token)
    log_event("info", "integrations.meta.delegated_active",
              f"Using delegated credentials for page {page_id}")
    return page_id, token


def _get_meta_credentials():
    """
    Returns (page_id, page_access_token) — preferring delegated credentials
    when enabled, then an active MetaConnection row in the DB (issued via
    OAuth), falling back to the legacy env vars (FB_PAGE_ID + FB_ACCESS_TOKEN)
    so existing setups keep working.

    Both can be None if no source has them. Callers must handle that.
    """
    # 0. Delegated token from an Advanced-Access app, while our review pends.
    d_page, d_token = _get_delegated_credentials()
    if d_page and d_token:
        return d_page, d_token

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


# ─────────────────────────────────────────────
# Webhook subscription management
# ─────────────────────────────────────────────
# Subscribing in the App Dashboard only declares which fields the APP wants.
# Each Page must ALSO be subscribed via POST /{page-id}/subscribed_apps or Meta
# delivers nothing — while the dashboard "Test" button still works, because it
# posts a canned payload straight to the callback URL and consults none of this.
SUBSCRIBED_FIELDS_DEFAULT = (
    "messages,message_echoes,messaging_postbacks,"
    "message_deliveries,message_reads,feed,mention"
)


def _subscribed_fields():
    return os.getenv("META_SUBSCRIBED_FIELDS", SUBSCRIBED_FIELDS_DEFAULT)


def subscribe_page_webhooks(page_id: str = None, page_token: str = None,
                            fields: str = None) -> tuple[bool, dict]:
    """
    Subscribe this app to a Page's webhook events.

    Falls back to the configured credentials when page_id/page_token are omitted.
    Returns (ok, response_body). Never raises — callers keep going on failure.
    """
    if not page_id or not page_token:
        cfg_id, cfg_token = _get_meta_credentials()
        page_id = page_id or cfg_id
        page_token = page_token or cfg_token
    if not page_id or not page_token:
        return False, {"error": "No page_id / page_access_token available"}

    try:
        r = requests.post(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/subscribed_apps",
            params={
                "subscribed_fields": fields or _subscribed_fields(),
                "access_token": page_token,
            },
            timeout=15,
        )
        try:
            body = r.json()
        except ValueError:
            body = {"raw": (r.text or "")[:500]}
    except requests.RequestException as e:
        log_event("error", "integrations.meta.subscribe_failed", str(e))
        return False, {"error": str(e)}

    ok = r.ok and bool(body.get("success"))
    # Log the raw Graph response either way — a rejected field name shows up
    # here and nowhere else.
    log_event(
        "info" if ok else "error",
        "integrations.meta.subscribe_page",
        f"page={page_id} ok={ok} status={r.status_code} body={body}",
    )
    return ok, body


def get_page_webhook_subscriptions(page_id: str = None,
                                   page_token: str = None) -> tuple[int, dict]:
    """Read back which apps are subscribed to a Page, and to which fields."""
    if not page_id or not page_token:
        cfg_id, cfg_token = _get_meta_credentials()
        page_id = page_id or cfg_id
        page_token = page_token or cfg_token
    if not page_id or not page_token:
        return 400, {"error": "No page_id / page_access_token available"}

    try:
        r = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/subscribed_apps",
            params={"access_token": page_token},
            timeout=15,
        )
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"raw": (r.text or "")[:500]}
    except requests.RequestException as e:
        return 502, {"error": str(e)}


def _send_url():
    """FB Graph send URL for the configured Page."""
    page_id, _ = _get_meta_credentials()
    if not page_id:
        return None
    return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/messages"


# ─────────────────────────────────────────────
# Instagram DM — implemented
# ─────────────────────────────────────────────
def fetch_instagram_username(igsid: str) -> dict | None:
    """
    Look up an Instagram user's profile (name / username / avatar) by their
    IGSID via the Graph API. Returns the profile dict, or None on failure.
    Works for users who've messaged the business (messaging context).
    """
    _, token = _get_meta_credentials()
    if not token or not igsid:
        return None
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{igsid}"
    try:
        r = requests.get(url, params={
            "fields": "name,username,profile_pic",
            "access_token": token,
        }, timeout=8)
        if r.status_code >= 400:
            log_event("warning", "integrations.meta.username_lookup",
                      f"Username lookup failed ({r.status_code}): {(r.text or '')[:200]}",
                      payload={"igsid": igsid})
            return None
        return r.json() or None
    except requests.RequestException as e:
        log_event("warning", "integrations.meta.username_lookup",
                  f"Username lookup exception: {e}", payload={"igsid": igsid})
        return None

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

def send_instagram_card(recipient_id: str, title: str, subtitle: str | None,
                        image_url: str, button_url: str,
                        button_title: str = "View product") -> dict | None:
    """
    Send a generic-template product card on Instagram — image + title +
    subtitle + a web_url button — as one tap-through card. Best-effort:
    the text reply has already been sent, so failures just mean no card.
    """
    _, token = _get_meta_credentials()
    url = _send_url()
    if not token or not url or not image_url or not button_url:
        return None

    element = {
        "title": (title or "View product")[:80],
        "image_url": image_url,
        "buttons": [{
            "type": "web_url",
            "url": button_url,
            "title": (button_title or "View product")[:20],   # IG button cap = 20 chars
        }],
    }
    if subtitle:
        element["subtitle"] = subtitle[:80]

    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {"template_type": "generic", "elements": [element]},
            }
        },
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code >= 400:
            log_event("warning", "integrations.meta.send_card",
                      f"IG card send failed ({r.status_code}): {(r.text or '')[:200]}",
                      payload={"recipient_id": recipient_id})
            return None
        log_event("info", "integrations.meta.send_card",
                  f"IG product card sent to {recipient_id}",
                  payload={"recipient_id": recipient_id})
        return r.json() if r.text else {}
    except requests.RequestException as e:
        log_event("warning", "integrations.meta.send_card",
                  f"IG card send exception: {e}", payload={"recipient_id": recipient_id})
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
    

def fetch_instagram_media(media_id: str) -> dict | None:
    """
    Fetch an IG post's image URL + caption by media_id, for giving the AI
    visual context on comments (the commenter is referring to the post image).
    Returns {"image_url": str|None, "caption": str|None} or None on failure.
    """
    _, token = _get_meta_credentials()
    if not token or not media_id:
        return None
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}"
    try:
        r = requests.get(url, params={
            "fields": "caption,media_url,thumbnail_url,media_type",
            "access_token": token,
        }, timeout=8)
        if r.status_code >= 400:
            log_event("warning", "integrations.meta.media_fetch",
                      f"Media fetch failed ({r.status_code}): {(r.text or '')[:200]}",
                      payload={"media_id": media_id})
            return None
        d = r.json() or {}
        # For videos/carousels media_url may be absent — thumbnail_url is the fallback.
        image_url = d.get("media_url") or d.get("thumbnail_url")
        # Only use media_url as an image if it's actually an image type.
        if d.get("media_type") == "VIDEO":
            image_url = d.get("thumbnail_url")
        return {"image_url": image_url, "caption": d.get("caption")}
    except requests.RequestException as e:
        log_event("warning", "integrations.meta.media_fetch",
                  f"Media fetch exception: {e}", payload={"media_id": media_id})
        return None