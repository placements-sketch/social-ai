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
from collections import OrderedDict
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
IG_LOGIN_API_VERSION = os.getenv("IG_LOGIN_API_VERSION", "v23.0")


# Meta's answer when a URL doesn't resolve to a real node+edge+method. It does
# NOT mean "wrong HTTP verb" — it means the path shape isn't routable at all.
_UNSUPPORTED_REQUEST = "unsupported request"


def ig_login_request(method: str, path: str, **kwargs):
    """
    Call graph.instagram.com, retrying without the version prefix.

    Two paths on this host demonstrably work unversioned — /access_token and
    /refresh_access_token — while every versioned call we make came back:

        {"message":"Unsupported request - method type: get",
         "type":"IGApiException","code":100}

    ...for GET /v23.0/me, and the same with "post" for
    /v23.0/{id}/subscribed_apps. When the version segment isn't recognised the
    router reads it as a node id and the next segment as an edge, so nothing
    resolves and the verb gets blamed. That one fault explains all three
    symptoms we saw: verification failing, webhook subscription failing, and the
    account showing a numeric id because the callback's username lookup was
    quietly failing too.

    Versioned is tried first so anything already working is untouched; the
    unversioned retry only happens on that specific error. `path` has no leading
    slash — e.g. "me" or "1784.../subscribed_apps".
    """
    attempts = [f"{IG_LOGIN_GRAPH}/{IG_LOGIN_API_VERSION}/{path}",
                f"{IG_LOGIN_GRAPH}/{path}"]
    last = None
    for i, url in enumerate(attempts):
        r = requests.request(method, url, **kwargs)
        try:
            body = r.json() if r.text else {}
        except ValueError:
            body = {}
        last = (r, body)

        if r.ok:
            if i:      # the unversioned form is the one that worked
                log_event("info", "integrations.meta.ig_unversioned",
                          f"{method.upper()} {path} succeeded without the version "
                          f"prefix — {IG_LOGIN_API_VERSION} is not routable on "
                          f"graph.instagram.com")
            return r, body

        msg = ((body.get("error") or {}).get("message") or "").lower()
        if _UNSUPPORTED_REQUEST not in msg:
            return r, body      # a real error — surface it, don't retry blindly

    return last


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

    # A DELIBERATE disconnect must actually disconnect.
    #
    # This fell through to IG_LOGIN_USER_TOKEN whenever no active connection was
    # found — including immediately after an admin disconnected an account on
    # purpose. The row went inactive, the UI said disconnected, and replies kept
    # going out under an environment token nobody had looked at in weeks. That
    # is the worst failure this system can have: messaging real customers from
    # an account the operator believes is switched off.
    #
    # So the fallback now applies only where it was actually meant to — a
    # deployment that predates the OAuth flow and has NO connection rows at all.
    # Once a connection has ever existed, those rows are the source of truth and
    # "none active" means none, not "look elsewhere".
    try:
        from app.models import MetaConnection
        any_connection_ever = MetaConnection.query.first() is not None
    except Exception:
        # Can't tell — assume a connection exists, because the safe failure is
        # "don't send" rather than "send as whoever the env says".
        any_connection_ever = True

    if any_connection_ever:
        log_event("warning", "integrations.meta.no_active_connection",
                  "No active Instagram connection — refusing to fall back to "
                  "IG_LOGIN_USER_TOKEN. Connect an account to resume sending.",
                  payload={"requested_account": account_id})
        return None, None

    token = os.getenv("IG_LOGIN_USER_TOKEN")
    if not token:
        return None, None
    log_event("warning", "integrations.meta.env_credentials_used",
              "Sending with IG_LOGIN_USER_TOKEN from the environment — no "
              "connection rows exist. This is the pre-OAuth fallback.",
              payload={"env_user_id": os.getenv("IG_LOGIN_USER_ID")})
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
MEDIA_FIELDS = 'id,caption,media_url,thumbnail_url,permalink,media_type,timestamp'


def fetch_instagram_media(media_id: str, account_id: str | None = None):
    """
    Post metadata for a comment's parent media. Returns (data, error_message).

    Prefers Instagram Login, exactly like fetch_instagram_username below and
    for the same reason: this used to call graph.facebook.com with
    `page_access_token`, which an Instagram-Login connection never populates.
    The token came back None, the endpoint 500'd on every request, and the
    frontend — which swallowed the failure — sat on a loading skeleton forever.
    An agent saw an empty grey box and no way to tell it had failed.
    """
    _ig_id, ig_token = _ig_login_credentials(account_id)

    if ig_token:
        # Through ig_login_request so the unversioned retry applies. The version
        # prefix is not routable on graph.instagram.com for every node, and that
        # single fault is what previously broke verification, webhook
        # subscription and the username lookup all at once.
        try:
            r, body = ig_login_request(
                'GET', str(media_id),
                params={'fields': MEDIA_FIELDS, 'access_token': ig_token},
                timeout=10,
            )
        except requests.RequestException as e:
            return None, f'Instagram unreachable: {str(e)[:120]}'
        if not r.ok:
            err = (body.get('error') or {}).get('message') or f'HTTP {r.status_code}'
            log_event('warning', 'integrations.meta.media_lookup',
                      f'Instagram Login media {media_id}: {err[:160]}')
            return None, err[:160]
        return body, None

    _, token = _get_meta_credentials(account_id)
    if not token:
        return None, 'No active Instagram connection'

    try:
        r = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media_id}",
            params={'fields': MEDIA_FIELDS, 'access_token': token},
            timeout=10,
        )
        body = r.json() if r.text else {}
    except (requests.RequestException, ValueError) as e:
        return None, f'Meta unreachable: {str(e)[:120]}'

    if not r.ok:
        err = (body.get('error') or {}).get('message') or f'HTTP {r.status_code}'
        log_event('warning', 'integrations.meta.media_lookup',
                  f'Graph media {media_id}: {err[:160]}')
        return None, err[:160]
    return body, None


# IGSIDs Meta has already told us it cannot resolve.
#
# The lookup runs on inbound messages, so the same six unresolvable customers
# were producing a doomed Graph call every time they wrote to us — burning rate
# limit and filling the log with the same line forever. The answer for these
# never changes: the id belongs to a previously connected Instagram account, so
# asking again tomorrow gets the identical refusal.
#
# In memory, not a database column: a process restart re-asking once per id is
# harmless, and it keeps this out of the schema. Bounded so a flood of bad ids
# cannot grow it without limit.
_UNRESOLVABLE_IGSIDS: "OrderedDict[str, bool]" = OrderedDict()
_UNRESOLVABLE_MAX = 500


def _mark_unresolvable(igsid: str):
    _UNRESOLVABLE_IGSIDS[str(igsid)] = True
    while len(_UNRESOLVABLE_IGSIDS) > _UNRESOLVABLE_MAX:
        _UNRESOLVABLE_IGSIDS.popitem(last=False)


def fetch_instagram_username(igsid: str, account_id: str | None = None) -> dict | None:
    """
    Look up an Instagram user's profile (name / username / avatar) by their
    IGSID via the Graph API. Returns the profile dict, or None on failure.
    Works for users who've messaged the business (messaging context).
    """
    if str(igsid) in _UNRESOLVABLE_IGSIDS:
        return None

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

    # Narrowing field sets, not one all-or-nothing request.
    #
    # Asking for name,username,profile_pic came back 500 / OAuthException
    # code 1 ("An unknown error has occurred") — Meta's catch-all, which says
    # nothing about WHICH field it objected to. Losing the whole profile
    # because one optional field is unavailable is the wrong trade: `username`
    # is the only one anything actually renders, and without it the customer
    # shows in the inbox and the activity feed as a bare 17-digit IGSID.
    #
    # So: ask for everything, and on failure fall back to the field we need.
    for fields in ("name,username,profile_pic", "username"):
        try:
            r = requests.get(url, params={
                "fields": fields,
                "access_token": token,
            }, timeout=8)
        except requests.RequestException as e:
            log_event("warning", "integrations.meta.username_lookup",
                      f"Username lookup exception: {e}", payload={"igsid": igsid})
            return None

        if r.status_code < 400:
            data = r.json() or None
            if data and fields == "username":
                log_event("info", "integrations.meta.username_lookup_narrowed",
                          "Full profile lookup failed but username resolved — "
                          "one of name/profile_pic is unavailable for this token",
                          payload={"igsid": igsid})
            return data

        # "does not exist / missing permissions" means this id is not addressable
        # by the token we hold — an IGSID is scoped to the account it was issued
        # for, so conversations from a previously connected account can never be
        # resolved by the current one. Narrowing the fields cannot help and the
        # customer's name is simply unknowable, so stop here and record it as a
        # fact rather than an error that invites investigation each time.
        body_l = (r.text or "").lower()
        if "does not exist" in body_l or "missing permissions" in body_l:
            log_event("info", "integrations.meta.username_unresolvable",
                      f"IGSID {igsid} is not addressable by the connected "
                      f"account — most likely a thread from a previously "
                      f"connected Instagram account.",
                      payload={"igsid": igsid})
            _mark_unresolvable(igsid)
            return None

        # Only worth retrying if there is a narrower attempt left.
        level = "warning" if fields == "username" else "info"
        log_event(level, "integrations.meta.username_lookup",
                  f"Username lookup failed ({r.status_code}) for fields=[{fields}]: "
                  f"{(r.text or '')[:200]}",
                  payload={"igsid": igsid, "fields": fields})

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
    # Instagram Login FIRST, exactly like every other send in this file.
    #
    # This function was the last one still demanding the Facebook page token,
    # and those env vars do not exist in production — they were removed when we
    # migrated to Instagram Login. So every public comment reply failed on the
    # very first line, while DMs went out fine. The customer saw silence under
    # their comment, and the app showed the reply as sent because the failure
    # only reached the log.
    ig_user_id, ig_token = _ig_login_credentials()
    use_ig_login = bool(ig_token)
    token = ig_token
    if not token:
        _, token = _get_meta_credentials()
    if not token:
        log_event("error", "integrations.meta.comment_send",
                  "No Instagram connection — cannot reply to comment",
                  payload={"comment_id": comment_id})
        return None

    if not text:
        log_event("warning", "integrations.meta.comment_send",
                  "Empty reply text — skipping",
                  payload={"comment_id": comment_id})
        return None

    safe_text = text[:1000]
    payload = {"message": safe_text}

    try:
        if use_ig_login:
            # Through ig_login_request so the unversioned retry applies — the
            # version prefix is not routable for every node on
            # graph.instagram.com, the same fault that broke verification and
            # webhook subscription.
            r, _body = ig_login_request(
                'POST', f'{comment_id}/replies',
                params={'access_token': token},
                json=payload,
                timeout=10,
            )
        else:
            r = requests.post(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/{comment_id}/replies",
                json=payload,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                timeout=10,
            )
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

def send_instagram_private_reply(comment_id: str, text: str,
                                 account_id: str | None = None) -> dict | None:
    """
    Open a DM with someone who commented, via Meta's private-replies endpoint.

    This is the only sanctioned way to move a public comment into a DM: you
    cannot message a commenter through the normal send API because you have
    their comment-author ID, not their IGSID. Meta resolves that for us.

    Two constraints worth knowing, because they explain most failures:
      - It works once per comment, and only within 7 days of the comment.
      - The person must not have blocked messages from the account.

    Same contract as every other sender here: returns Meta's response on
    success, None on failure, never raises. Callers treat None as "the public
    reply still went out, the DM didn't".
    """
    # The two logins do NOT share an endpoint here, unlike every other sender
    # in this file — so this is not a copy of the comment-reply migration.
    #
    #   Instagram Login:  POST {ig_user_id}/messages
    #                     {"recipient": {"comment_id": ...}}
    #   Facebook Login:   POST {comment_id}/private_replies
    #                     {"message": "..."}
    #
    # Same idea, different node. Under Instagram Login a private reply is just
    # a message whose recipient is named by comment instead of by IGSID, which
    # is why it goes through the messages endpoint and returns `message_id`
    # rather than `id`.
    ig_user_id, ig_token = _ig_login_credentials(account_id)
    if ig_token:
        token = ig_token
        url = f"{IG_LOGIN_GRAPH}/{IG_LOGIN_API_VERSION}/{ig_user_id}/messages"
        payload = {
            "recipient": {"comment_id": comment_id},
            "message":   {"text": (text or "")[:1000]},
        }
    else:
        _, token = _get_meta_credentials(account_id)
        url = (f"https://graph.facebook.com/{GRAPH_API_VERSION}"
               f"/{comment_id}/private_replies")
        payload = {"message": (text or "")[:1000]}

    if not token:
        log_event("error", "integrations.meta.private_reply",
                  "No Instagram connection — cannot open a DM from this comment",
                  payload={"comment_id": comment_id})
        return None

    if not text:
        log_event("warning", "integrations.meta.private_reply",
                  "Empty private reply text — skipping",
                  payload={"comment_id": comment_id})
        return None

    safe_text = text[:1000]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        body_preview = (r.text or "")[:400]

        if r.status_code >= 400:
            log_event("error", "integrations.meta.private_reply",
                      f"Private reply failed ({r.status_code}): {body_preview[:200]}",
                      payload={
                          "comment_id": comment_id,
                          "status": r.status_code,
                          "response": body_preview,
                          "text_preview": safe_text[:120],
                      })
            return None

        data = r.json() if r.text else {}
        # The messages node answers with `message_id`, private_replies with
        # `id`. The caller stores whatever lands in `id` as the message's
        # external_id, so normalise here rather than making it guess — an
        # outbound row with a NULL external_id reads as "never delivered".
        if not data.get("id") and data.get("message_id"):
            data["id"] = data["message_id"]
        log_event("info", "integrations.meta.private_reply",
                  f"DM opened from comment {comment_id}",
                  payload={
                      "comment_id": comment_id,
                      "message_id": data.get("id"),
                      "channel": "instagram_dm",
                      "text_preview": safe_text[:120],
                  })
        return data

    except requests.RequestException as e:
        log_event("error", "integrations.meta.private_reply",
                  f"Private reply exception: {e}",
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
    

def instagram_media_for_ai(media_id: str, account_id: str | None = None) -> dict | None:
    """
    {"image_url": str|None, "caption": str|None} or None — the shape the AI
    vision path wants, over the single fetch_instagram_media above.

    This used to be a SECOND function with the same name as that one, defined
    later in the file, so it silently replaced it. Both then called
    graph.facebook.com with the Facebook page token — which an Instagram-Login
    connection never populates — so the AI was getting no image for comments on
    our own posts and falling back to reasoning from the caption alone.
    """
    data, _error = fetch_instagram_media(media_id, account_id)
    if not data:
        return None
    # For videos and carousels media_url is absent or is not a still image;
    # thumbnail_url is the only usable one.
    image_url = data.get("media_url") or data.get("thumbnail_url")
    if data.get("media_type") == "VIDEO":
        image_url = data.get("thumbnail_url")
    return {"image_url": image_url, "caption": data.get("caption")}

# ─────────────────────────────────────────────
# Instagram Login token refresh
# ─────────────────────────────────────────────
# Page tokens never expire; Instagram Login user tokens last 60 days and can
# only be refreshed WHILE STILL VALID. Let one lapse and the only way back is
# re-running the OAuth flow by hand, which means an outage until someone
# notices. Run this from cron well inside the window.
IG_REFRESH_WHEN_DAYS_LEFT = int(os.getenv("IG_REFRESH_WHEN_DAYS_LEFT", "14"))


# Webhook fields an Instagram Login account must be subscribed to for anything
# to reach us. One definition, imported by the OAuth callback and the health
# check, so a change here cannot apply to only one of them.
IG_SUBSCRIBED_FIELDS = "messages,comments"


def subscribe_ig_login_webhooks(ig_user_id: str, token: str,
                                fields: str = None) -> tuple[bool, dict]:
    """
    Subscribe an Instagram Login account to webhook events.

    Addressed by NUMERIC ACCOUNT ID, not by `me`.

    The OAuth callback used to POST to `/me/subscribed_apps` and Instagram
    answered:

        400 {"error":{"message":"Unsupported request - method type: post",
                      "type":"IGApiException","code":100}}

    `me` resolves on GET but is not a routable target for a POST on this edge,
    so the subscription silently never happened — and an account with a
    perfectly valid token receives no messages or comments at all, which looks
    exactly like a broken integration for a reason nothing on the page reports.

    Falls back to `me` only if the numeric form fails, so a future API change in
    the other direction does not break it again.

    Returns (ok, response_body). Never raises.
    """
    fields = fields or IG_SUBSCRIBED_FIELDS
    attempts = [str(ig_user_id)] if ig_user_id else []
    attempts.append('me')

    last_body = {}
    for target in attempts:
        try:
            r, body = ig_login_request(
                'POST', f'{target}/subscribed_apps',
                params={'subscribed_fields': fields, 'access_token': token},
                timeout=20,
            )
        except requests.RequestException as e:
            last_body = {'error': str(e)}
            continue

        ok = r.ok and bool(body.get('success'))
        log_event('info' if ok else 'warning', 'integrations.meta.ig_subscribe',
                  f"target={target} ok={ok} status={r.status_code} body={str(body)[:200]}")
        if ok:
            return True, body
        last_body = body

    return False, last_body


def get_ig_login_subscriptions(ig_user_id: str, token: str) -> tuple[bool, dict]:
    """
    What this Instagram account is actually subscribed to, straight from Meta.

    A valid token with no subscription receives nothing, and that combination
    is indistinguishable from a healthy connection unless you ask. Returns
    (ok, body) where body['data'] lists the subscribed fields.
    """
    target = str(ig_user_id) if ig_user_id else 'me'
    try:
        r, body = ig_login_request('GET', f'{target}/subscribed_apps',
                                   params={'access_token': token}, timeout=10)
    except requests.RequestException as e:
        return False, {'error': str(e)}
    return r.ok, body


def verify_ig_login_token(token: str, ig_user_id: str = None) -> dict:
    """
    Ask Instagram whether this token actually works, right now.

    Everything else in the connection card is inference from our own database:
    a row marked active with no expiry recorded reads as "Connected" without
    anything ever having spoken to Instagram. This is the one call that turns
    that claim into a fact — and it returns the username too, which is why the
    card was showing a bare numeric account id.

    Returns {'ok': bool, 'user_id': str|None, 'username': str|None,
             'error': str|None}. Never raises.
    """
    if not token:
        return {'ok': False, 'user_id': None, 'business_id': None, 'username': None,
                'error': 'No Instagram Login token stored for this connection.'}

    # Addressed by NUMERIC ACCOUNT ID, with `me` only as a last resort.
    #
    # `me` is not a routable node on graph.instagram.com for Instagram Login.
    # Every call that failed here contained it — GET /me, GET /v23.0/me,
    # POST /v23.0/me/subscribed_apps — and every call that worked
    # (/access_token, /refresh_access_token) avoids node paths entirely. Meta
    # reports the mismatch as "Unsupported request - method type: get", which
    # reads like a wrong verb and is really "that path does not exist".
    #
    # `fields` differs per form: on a numeric node the id field is `id`; asking
    # `me` for `user_id` is the documented shape. Requesting both is harmless.
    targets = [t for t in (str(ig_user_id) if ig_user_id else None, 'me') if t]
    last_err = 'Instagram rejected this token.'

    for target in targets:
        try:
            # `user_id` is requested as well as `id` because they are DIFFERENT
            # numbers and we need both:
            #   id      37355381327440609  — app-scoped, what OAuth hands back
            #   user_id 17841412308701394  — the IG Business Account id
            # Webhooks are keyed on the business id, and _connection_for()
            # matches on ig_business_account_id — which this flow never stored,
            # so routing always fell through to "most recent active
            # connection". Fine with one account, wrong with two.
            r, body = ig_login_request(
                'GET', target,
                params={'fields': 'id,user_id,username', 'access_token': token},
                timeout=10)
        except requests.RequestException as e:
            log_event("warning", "integrations.meta.verify_failed",
                      f"Could not reach Instagram to verify the token: {e}")
            return {'ok': False, 'user_id': None, 'business_id': None, 'username': None,
                    'error': f'Could not reach Instagram: {e}'}

        if r.status_code < 400:
            break

        last_err = ((body.get('error') or {}).get('message')
                    or f'Instagram returned {r.status_code}')
        log_event("warning", "integrations.meta.verify_attempt",
                  f"Verify against '{target}' failed: {last_err}",
                  payload={'target': target, 'status': r.status_code})
    else:
        log_event("error", "integrations.meta.verify_failed",
                  f"Token rejected by Instagram: {last_err}")
        return {'ok': False, 'user_id': None, 'business_id': None, 'username': None, 'error': last_err}

    return {
        'ok': True,
        # The app-scoped id — what we key the connection row on.
        'user_id': str(body.get('id') or '') or None,
        # The IG Business Account id — what webhooks report as the recipient.
        'business_id': str(body.get('user_id') or '') or None,
        'username': body.get('username'),
        'error': None,
    }


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
