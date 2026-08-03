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
from datetime import datetime, timedelta

import requests
from sqlalchemy import or_ as db_or

from app.utils.logger import log_event

GRAPH_API_VERSION = "v25.0"

# ─────────────────────────────────────────────
# Instagram API with Instagram Login
# ─────────────────────────────────────────────
# A second, separate surface. Facebook Login talks to graph.facebook.com with a
# PAGE token; Instagram Login talks to graph.instagram.com with an IG USER
# token, and only the latter can message a customer who holds no role on the
# app. Without it every reply to a real customer dies with:
#   (#200) App does not have Advanced Access to instagram_manage_messages
#          permission and recipient user does not have role on app
#
# The token is issued by the Instagram business login OAuth flow and lasts 60
# days — unlike page tokens, it MUST be refreshed. See IG_LOGIN_USER_TOKEN.
IG_LOGIN_GRAPH = "https://graph.instagram.com"
IG_LOGIN_API_VERSION = "v23.0"


def _connection_for(account_id: str | None):
    """
    The MetaConnection that owns `account_id` — an IG business account id or a
    Page id, whichever the webhook reported as the recipient.

    Falls back to the most recent active connection when the id is unknown or
    absent, which keeps single-account setups working unchanged. Returns None
    if the DB is unreachable, so callers drop through to env vars.
    """
    try:
        from app.models import MetaConnection
        q = MetaConnection.query.filter_by(is_active=True)
        if account_id:
            match = q.filter(
                db_or(MetaConnection.ig_business_account_id == str(account_id),
                      MetaConnection.page_id == str(account_id))
            ).first()
            if match:
                return match
        return q.order_by(MetaConnection.connected_at.desc()).first()
    except Exception as e:
        log_event("warn", "integrations.meta.connection_lookup_failed", str(e))
        return None


def _ig_login_credentials(account_id: str | None = None):
    """
    Returns (ig_user_id, ig_user_token) for the Instagram Login surface of the
    account that received the message, or (None, None) when not configured —
    in which case callers fall back to the Facebook Login page token.

    Per-connection first so several accounts can be live at once; the env vars
    remain as a single-account fallback.
    """
    conn = _connection_for(account_id)
    if conn is not None and conn.ig_login_token:
        return (conn.ig_login_user_id or "me"), conn.ig_login_token

    token = os.getenv("IG_LOGIN_USER_TOKEN")
    if not token:
        return None, None
    return (os.getenv("IG_LOGIN_USER_ID") or "me"), token


def _get_meta_credentials(account_id: str | None = None):
    """
    Returns (page_id, page_access_token) for the account that received the
    message — preferring its MetaConnection row (issued via OAuth), falling
    back to the legacy env vars (FB_PAGE_ID + FB_ACCESS_TOKEN) so existing
    setups keep working.

    Both can be None if neither source has them. Callers must handle that.
    """
    # 1. Try DB (the OAuth-issued token, what App Review needs us to use)
    conn = _connection_for(account_id)
    if conn is not None and conn.page_id and conn.page_access_token:
        return conn.page_id, conn.page_access_token

    # 2. Fall back to env vars (legacy Explorer-token setup).
    #
    # Loudly. This fallback is a different Instagram account from whichever one
    # is connected through OAuth — so reaching it means a reply is about to go
    # out under the wrong brand, and it happens precisely when something else
    # has already gone wrong (token expired, account disconnected, no row for
    # this business_account_id). Silently posting as another account is worse
    # than failing to post, so this is recorded as an error rather than taken
    # as a normal path.
    legacy_page, legacy_token = os.getenv("FB_PAGE_ID"), os.getenv("FB_ACCESS_TOKEN")
    if legacy_token:
        log_event("error", "integrations.meta.legacy_credentials_used",
                  "Falling back to the FB_PAGE_ID / FB_ACCESS_TOKEN environment "
                  "credentials — this is NOT the connected account. Clear those "
                  "variables once every account is connected through OAuth.",
                  payload={"requested_account": account_id, "legacy_page_id": legacy_page})
    return legacy_page, legacy_token


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
def fetch_instagram_username(igsid: str, account_id: str | None = None) -> dict | None:
    """
    Look up an Instagram user's profile (name / username / avatar) by their
    IGSID via the Graph API. Returns the profile dict, or None on failure.
    Works for users who've messaged the business (messaging context).
    """
    # Prefer Instagram Login — the Facebook-Login page token 403s on any
    # customer without a role on the app.
    _ig_id, ig_token = _ig_login_credentials(account_id)
    if ig_token:
        url = f"{IG_LOGIN_GRAPH}/{IG_LOGIN_API_VERSION}/{igsid}"
        token = ig_token
    else:
        _, token = _get_meta_credentials(account_id)
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{igsid}"
    if not token or not igsid:
        return None
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

def send_instagram_reply(recipient_id: str, text: str,
                         account_id: str | None = None) -> dict | None:
    """
    Send a DM reply on Instagram via Meta Graph API.

    Args:
        recipient_id: The IG user's Page-Scoped ID (the `sender.id` from the
                      inbound webhook payload).
        text:         The reply text. Max 1000 chars per Meta docs.

    Returns:
        Meta's response dict on success, or None on failure.
    """
    # Instagram Login first. The Facebook-Login page token can only message
    # users holding a role on the app until App Review grants Advanced Access,
    # so for real customers it is the difference between a delivered reply and
    # a 403.
    ig_user_id, ig_token = _ig_login_credentials(account_id)
    if ig_token:
        token = ig_token
        url = f"{IG_LOGIN_GRAPH}/{IG_LOGIN_API_VERSION}/{ig_user_id}/messages"
    else:
        page_id, token = _get_meta_credentials(account_id)
        url = (f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/messages"
               if page_id else None)

    if not token or not url:
        log_event("error", "integrations.meta.send",
                  "No Instagram credentials configured — cannot send reply",
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

# ─────────────────────────────────────────────
# Instagram Login token refresh
# ─────────────────────────────────────────────
# Page tokens never expire; Instagram Login user tokens last 60 days and can
# only be refreshed WHILE STILL VALID. Let one lapse and the only way back is
# re-running the OAuth flow by hand, which means an outage until someone
# notices. Run this from cron well inside the window.
IG_REFRESH_WHEN_DAYS_LEFT = int(os.getenv("IG_REFRESH_WHEN_DAYS_LEFT", "14"))


def refresh_ig_login_tokens(force: bool = False) -> dict:
    """
    Refresh Instagram Login tokens that are nearing expiry.

    Returns a summary dict. Never raises — a failure here must not take down
    whatever scheduled job called it.
    """
    summary = {"checked": 0, "refreshed": 0, "skipped": 0, "failed": 0, "details": []}
    try:
        from app import db
        from app.models import MetaConnection
        conns = (MetaConnection.query
                 .filter(MetaConnection.is_active.is_(True))
                 .filter(MetaConnection.ig_login_token.isnot(None))
                 .all())
    except Exception as e:
        log_event("error", "integrations.meta.ig_refresh_lookup_failed", str(e))
        summary["failed"] = 1
        return summary

    cutoff = datetime.utcnow() + timedelta(days=IG_REFRESH_WHEN_DAYS_LEFT)
    for conn in conns:
        summary["checked"] += 1
        label = conn.ig_username or conn.ig_login_user_id or conn.page_id

        if not force and conn.ig_login_expires_at and conn.ig_login_expires_at > cutoff:
            summary["skipped"] += 1
            continue

        try:
            r = requests.get(f"{IG_LOGIN_GRAPH}/refresh_access_token", params={
                "grant_type": "ig_refresh_token",
                "access_token": conn.ig_login_token,
            }, timeout=15)
            body = r.json() if r.content else {}
        except requests.RequestException as e:
            summary["failed"] += 1
            summary["details"].append(f"{label}: network error {e}")
            log_event("error", "integrations.meta.ig_refresh_failed", f"{label}: {e}")
            continue

        new_token = body.get("access_token")
        if r.status_code >= 400 or not new_token:
            summary["failed"] += 1
            summary["details"].append(f"{label}: HTTP {r.status_code} {str(body)[:150]}")
            log_event("error", "integrations.meta.ig_refresh_failed",
                      f"{label}: HTTP {r.status_code} {str(body)[:200]}")
            continue

        conn.ig_login_token = new_token
        expires_in = body.get("expires_in")
        if expires_in:
            conn.ig_login_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            summary["failed"] += 1
            summary["details"].append(f"{label}: commit failed {e}")
            continue

        summary["refreshed"] += 1
        summary["details"].append(f"{label}: refreshed, expires {conn.ig_login_expires_at}")
        log_event("info", "integrations.meta.ig_refresh",
                  f"{label}: token refreshed, expires {conn.ig_login_expires_at}")

    return summary
